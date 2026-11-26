"""Quasi-identifier handling: age, location, diagnosis.

Policy (privacy-vs-utility, in this order: give up location precision first, age precision last)
  1. Start from the most useful form: exact age, PIN reduced to its first 3 digits, diagnosis kept.
  2. Records whose (age, sex, PIN-prefix, diagnosis) combination is shared by fewer than k patients
     are generalized one step at a time, only those records, until the class is large enough:
        level 0  exact age,            PIN prefix 3
        level 1  exact age,            PIN prefix 2
        level 2  exact age,            PIN removed
        level 3  5-year band,          PIN removed
        level 4  10-year band,         PIN removed
        level 5  10-year band,         PIN removed, rare diagnosis suppressed
        level 6  coarse age groups (<18, 18-59, 60+), PIN removed, rare diagnosis suppressed
  3. Ages >= age_top_code are always reported as "N+" (a tiny group is identifying by itself).
Street-level address, names, phones and ids are removed everywhere, regardless of level.
Medical values (vitals, labs, drugs, doses, length of stay) are never touched.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Optional

import regex as re

from ..config import Config
from ..contracts import Document, MedKind, Mention, PIIType
from ..detect.headers import hint_for
from ..normalize.text import normalize

MAX_LEVEL = 6
_DX_LABEL = re.compile(
    r"(?:principal\s+diagnosis|final\s+diagnosis|diagnosis|dx|निदान|bimari|rog|रोग|शिकायत/निदान)\s*[:\-]\s*([^\n.;|,]{3,80})", re.I)
_DX_HEADER = re.compile(r"diagnos|\bdx\b|निदान|bimari|\brog\b|रोग|disease|illness", re.I)
_NUM = re.compile(r"\d{1,3}")


@dataclass
class Facts:
    doc_id: str
    age: Optional[int] = None
    sex: Optional[str] = None
    pin: Optional[str] = None
    dx: Optional[str] = None
    los: Optional[int] = None
    age_spans: list = field(default_factory=list)  # (field, start, end) in original coordinates
    dx_spans: list = field(default_factory=list)


def _dx_norm(s: str) -> str:
    s = normalize(s).text.lower()
    s = re.sub(r"[^\p{L}\p{M}\d ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def extract_facts(doc: Document, units, spans, meds, mention: Mention) -> Facts:
    f = Facts(doc.doc_id, mention.age, mention.sex, mention.pin)
    for u in units:
        hint = hint_for(u.header)
        text = u.original
        for m in meds[u.field]:
            if m.kind == MedKind.AGE:
                f.age_spans.append((u.field, m.start, m.end))
        for m in meds[u.field]:
            if m.kind == MedKind.LOS and f.los is None:
                mm = re.search(r"\d+", text[m.start:m.end])
                if mm:
                    f.los = int(mm.group())
        if u.field is not None and re.search(r"\blos\b|length of stay|\bstay\b|दिन", u.header) and f.los is None \
                and re.fullmatch(r"\s*\d{1,3}\s*", text):
            f.los = int(text)
        if hint.kind == "age" and re.fullmatch(r"\s*\d{1,3}\s*", text):
            f.age_spans.append((u.field, 0, len(text)))
        # diagnosis: a diagnosis column or a labelled line
        if u.field is not None and _DX_HEADER.search(u.header) and text.strip() and f.dx is None:
            if not any(s.start < len(text) and s.end > 0 for s in spans[u.field] if s.type != PIIType.DATE):
                f.dx = _dx_norm(text)
                f.dx_spans.append((u.field, 0, len(text)))
        else:
            for m in _DX_LABEL.finditer(u.norm.text):
                val = m.group(1).strip()
                if val and f.dx is None:
                    a, b = u.norm.to_orig(m.start(1), m.start(1) + len(m.group(1).rstrip()))
                    f.dx = _dx_norm(val)
                    f.dx_spans.append((u.field, a, b))
    # dedupe overlapping age spans (a labelled "26 yrs / Male" can match twice)
    seen, uniq = set(), []
    for a in sorted(f.age_spans, key=lambda x: (str(x[0]), x[1], x[2])):
        if (a[0], a[1]) not in seen:
            seen.add((a[0], a[1]))
            uniq.append(a)
    f.age_spans = uniq
    return f


def age_text(age: int, level: int, cfg: Config) -> str:
    if age >= cfg.age_top_code:
        return f"{cfg.age_top_code}+"
    if level <= 2:
        return str(age)
    if level >= 6:
        return "<18" if age < 18 else ("18-59" if age < 60 else f"60-{cfg.age_top_code - 1}")
    w = cfg.age_band_width if level == 3 else cfg.age_band_width * 2
    lo = (age // w) * w
    hi = min(lo + w - 1, cfg.age_top_code - 1)
    return f"{lo}-{hi}"


def pin_text(pin: Optional[str], level: int, cfg: Config) -> str:
    if not pin or level >= 2:
        return "[PIN]"
    keep = cfg.pin_keep_digits if level == 0 else max(1, cfg.pin_keep_digits - 1)
    return pin[:keep] + "X" * (6 - keep)


def qi_key(f: Facts, level: int, cfg: Config, rare: frozenset = frozenset()) -> tuple:
    """The released quasi-identifier tuple of a record at a given level."""
    age = None if f.age is None else age_text(f.age, level, cfg)
    pin = None if not f.pin else pin_text(f.pin, level, cfg)
    dx = "[suppressed]" if (level >= 5 and f.dx in rare) else f.dx
    if not cfg.qi_include_dx:
        dx = None
    return (age, f.sex, pin, dx)


def plan_levels(facts: dict[str, Facts], pseud_of: dict[str, str], cfg: Config) -> tuple[dict[str, int], set[str], frozenset]:
    """Assign each record the smallest generalization level whose class has >= k distinct patients.
    Returns (level per doc_id, set of doc_ids whose diagnosis is suppressed)."""
    k = cfg.k_target
    dx_patients: dict[str, set[str]] = defaultdict(set)
    for d, f in facts.items():
        if f.dx:
            dx_patients[f.dx].add(pseud_of[d])
    rare_dx = frozenset(x for x, p in dx_patients.items() if len(p) <= cfg.rare_dx_max_patients)
    level = {d: 0 for d in facts}
    # records with no quasi-identifiers at all cannot be singled out by them
    active = {d for d, f in facts.items() if f.age is not None or f.pin or f.dx}
    for _ in range(MAX_LEVEL + 1):
        classes: dict[tuple, set[str]] = defaultdict(set)
        for d in facts:
            classes[qi_key(facts[d], level[d], cfg, rare_dx)].add(pseud_of[d])
        changed = False
        for d in sorted(active):
            if level[d] < MAX_LEVEL and len(classes[qi_key(facts[d], level[d], cfg, rare_dx)]) < k:
                nxt = level[d] + 1
                if nxt == 5 and facts[d].dx not in rare_dx:
                    nxt = 6  # suppressing a common diagnosis would not help; coarsen the age instead
                level[d] = nxt
                changed = True
        if not changed:
            break
    suppress = {d for d, f in facts.items() if f.dx in rare_dx and level[d] >= 5}
    return level, suppress, rare_dx


def overrides(f: Facts, texts: dict, level: int, suppress_dx: bool, cfg: Config) -> dict:
    """Text replacements for one record: {field: [(start, end, new_text)]} (original coordinates)."""
    out: dict = defaultdict(list)
    if f.age is not None:
        for fld, a, b in f.age_spans:
            seg = texts[fld][a:b]
            new = apply_age(seg, f.age, level, cfg)
            if new != seg:
                out[fld].append((a, b, new))
    if suppress_dx:
        for fld, a, b in f.dx_spans:
            out[fld].append((a, b, "[RARE DIAGNOSIS]"))
    return out


def apply_age(original_span_text: str, age: int, level: int, cfg: Config) -> str:
    """Replace the number inside an age span ('47 years' -> '45-49 years')."""
    new = age_text(age, level, cfg)
    if new == str(age):
        return original_span_text
    m = _NUM.search(normalize(original_span_text).text)
    if not m:
        return original_span_text
    # map back to original characters of the first number
    n = normalize(original_span_text)
    s, e = n.to_orig(m.start(), m.end())
    return original_span_text[:s] + new + original_span_text[e:]
