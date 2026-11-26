"""Quasi-identifier handling: age, location, diagnosis.

Policy (privacy-vs-utility, in this order: give up location precision first, age precision last)
  1. Start from the most useful form: exact age, PIN reduced to its first 3 digits, diagnosis kept.
  2. Patients (all records sharing a pseudonym, pooled: an attacker joins them the same way) whose
     (age, birth year, sex, PIN-prefix, district, tehsil, diagnosis) combination is shared by fewer than k patients
     are generalized one step at a time, only those patients and in every one of their records, until the class
     is large enough:
        level 0  exact age,            PIN prefix 3
        level 1  exact age,            PIN prefix 2
        level 2  exact age,            PIN removed
        level 3  5-year band,          PIN removed
        level 4  10-year band,         PIN removed
        level 5  10-year band,         PIN removed, rare diagnosis suppressed
        level 6  coarse age groups (<18, 18-59, 60+), PIN removed, rare diagnosis suppressed
     From level 3 on (the age is a band) a date of birth becomes a birth-year band of the same width class
     ("1975-1979"; a FHIR birthDate, which must stay a valid date, becomes the band's first year) and a tehsil
     becomes "[TEHSIL]" (the district stays). A day-shifted DOB still states the birth year, which would undo the
     age band, and tehsil + district + sex + age narrow a voter registry to one person.
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
from ..detect.diagnosis import dx_entry_end, dx_key
from ..detect.headers import hint_for
from ..normalize.text import normalize

MAX_LEVEL = 6
_DX_LABEL = re.compile(
    r"(?:principal\s+diagnosis|final\s+diagnosis|diagnosis|dx|निदान|bimari|rog|रोग|शिकायत/निदान)\s*[:\-]\s*(?=[^\s;|])", re.I)
_DX_HEADER = re.compile(r"diagnos|\bdx\b|निदान|bimari|\brog\b|रोग|disease|illness", re.I)
_NUM = re.compile(r"\d{1,3}")
_DOB_BEFORE = re.compile(r"(?:\bdob\b|d\.o\.b\.?|date\s+of\s+birth|birth\s*date|जन्म\s*तिथि|janm\s*tithi|janam\s*tithi)\W{0,6}$", re.I)
_DOB_HDR = re.compile(r"\bdob\b|birth|d\.o\.b|janm|janam|जन्म", re.I)
_TEHSIL_HDR = re.compile(r"tehsil|tahsil|taluk|तहसील", re.I)
_DISTRICT_HDR = re.compile(r"district|distt|\bjila\b|\bzila\b|जिला|जनपद", re.I)
_TEHSIL_TEXT = re.compile(r"(?<![\p{L}])(?:tehsil|tahsil|teh\.)\s*[:\-]?\s*([\p{L}\p{M}]+(?:\s[\p{L}\p{M}]+)?)|"
                          r"तहसील\s*[:\-]?\s*([\p{L}\p{M}]+(?:\s[\p{L}\p{M}]+)?)", re.I)
_DISTRICT_TEXT = re.compile(r"(?<![\p{L}])(?:distt?\.?|district|jila|zila)\s*[:\-]?\s*([\p{L}\p{M}]+(?:\s[\p{L}\p{M}]+)?)|"
                            r"जिला\s*[:\-]?\s*([\p{L}\p{M}]+)", re.I)
_STOP_WORDS = re.compile(r"\s+(?:distt?|district|jila|zila|pin|state|जिला|पिन)\b.*$", re.I)


def _low(s: str) -> str:
    return " ".join(normalize(s).text.lower().split())


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
    birth_year: Optional[int] = None
    district: Optional[str] = None
    tehsil: Optional[str] = None
    dob_spans: list = field(default_factory=list)  # (field, start, end, is_fhir_date)
    tehsil_spans: list = field(default_factory=list)  # (field, start, end)


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
                f.dx = dx_key(text)
                f.dx_spans.append((u.field, 0, len(text)))
        else:
            for m in _DX_LABEL.finditer(u.norm.text):
                # the WHOLE first entry, ICD code included ("Gout, unspecified (M10.9)"): suppressing a fragment
                # left the code, which names the disease, in the clear
                a0 = m.end()
                b0 = dx_entry_end(u.norm.text, a0)
                if b0 - a0 >= 3 and f.dx is None:
                    a, b = u.norm.to_orig(a0, b0)
                    f.dx = dx_key(u.norm.text[a0:b0])
                    f.dx_spans.append((u.field, a, b))
        _place_and_dob(f, u, hint, spans[u.field])
    # dedupe overlapping age spans (a labelled "26 yrs / Male" can match twice)
    seen, uniq = set(), []
    for a in sorted(f.age_spans, key=lambda x: (str(x[0]), x[1], x[2])):
        if (a[0], a[1]) not in seen:
            seen.add((a[0], a[1]))
            uniq.append(a)
    f.age_spans = uniq
    if f.age is None:
        # the linker found no age (e.g. a lab record), but the record states one: generalize it like any other,
        # an exact age left in one record undoes the band in all the others once records are pooled
        for fld, a, b in f.age_spans:
            m = _NUM.search(normalize(_text_of(units, fld)[a:b]).text)
            if m and 0 < int(m.group()) <= 120:
                f.age = int(m.group())
                break
    return f


def _text_of(units, fld) -> str:
    for u in units:
        if u.field == fld:
            return u.original
    return ""


def _place_and_dob(f: Facts, u, hint, uspans) -> None:
    """Date of birth (a DATE span in a DOB field or after a DOB label), tehsil and district (columns or labels)."""
    from ..normalize.dates import find_dates
    text = u.original
    for s in uspans:
        if s.type != PIIType.DATE:
            continue
        is_dob = hint.kind == "dob" or (u.field and _DOB_HDR.search(u.header)) or _DOB_BEFORE.search(text[:s.start])
        if not is_dob:
            continue
        ms = find_dates(normalize(text[s.start:s.end]).text)
        if ms:
            f.birth_year = f.birth_year or ms[0].y
            f.dob_spans.append((u.field, s.start, s.end, bool(u.field and u.field.endswith("birthDate"))))
    covered = lambda a, b: any(x.start < b and a < x.end for x in uspans)
    stripped = text.strip()
    if u.field is not None and stripped and _TEHSIL_HDR.search(u.header):
        a = text.index(stripped[0])
        if not covered(a, a + len(stripped)):
            f.tehsil = f.tehsil or _low(stripped)
            f.tehsil_spans.append((u.field, a, a + len(stripped)))
        return
    if u.field is not None and stripped and _DISTRICT_HDR.search(u.header):
        f.district = f.district or _low(stripped)
        return
    for m in _TEHSIL_TEXT.finditer(text):
        g = 1 if m.group(1) else 2
        val = _STOP_WORDS.sub("", m.group(g))
        a, b = m.start(g), m.start(g) + len(val)
        if val.strip() and not covered(a, b):
            f.tehsil = f.tehsil or _low(val)
            f.tehsil_spans.append((u.field, a, b))
    if f.district is None:
        for m in _DISTRICT_TEXT.finditer(text):
            g = 1 if m.group(1) else 2
            val = _STOP_WORDS.sub("", m.group(g))
            if val.strip() and not covered(m.start(g), m.start(g) + len(val)):
                f.district = _low(val)
                break


def _by_width(level: int) -> int:
    return 5 if level == 3 else (10 if level in (4, 5) else 20)


def dob_text(birth_year: int, level: int, fhir: bool) -> Optional[str]:
    """A date of birth at this level: None keeps the (day-shifted) date; else a truthful birth-year band."""
    if level <= 2:
        return None
    w = _by_width(level)
    lo = (birth_year // w) * w
    return str(lo) if fhir else f"{lo}-{lo + w - 1}"


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
    by = None
    if f.birth_year is not None:
        by = f.birth_year if level <= 2 else dob_text(f.birth_year, level, False)
    tehsil = f.tehsil if level <= 2 else None
    return (age, f.sex, pin, dx, by, f.district, tehsil)


def _pooled(docs: list[str], facts: dict[str, Facts]) -> Facts:
    """One patient's quasi-identifiers across their records (what an attacker pooling by pseudonym sees)."""
    p = Facts(docs[0])
    for d in docs:
        f = facts[d]
        for attr in ("age", "sex", "pin", "dx", "birth_year", "district", "tehsil"):
            if getattr(p, attr) is None and getattr(f, attr) is not None:
                setattr(p, attr, getattr(f, attr))
    return p


def plan_levels(facts: dict[str, Facts], pseud_of: dict[str, str], cfg: Config) -> tuple[dict[str, int], set[str], frozenset]:
    """Give each PATIENT (records sharing a pseudonym) the smallest generalization level whose class has >= k distinct
    patients, and use that level in every one of their records: a record-by-record level let the most precise record
    of a patient decide what an attacker pooling the records sees.
    Returns (level per doc_id, set of doc_ids whose diagnosis is suppressed, rare diagnoses)."""
    k = cfg.k_target
    docs_of: dict[str, list[str]] = defaultdict(list)
    for d in sorted(facts):
        docs_of[pseud_of[d]].append(d)
    pooled = {p: _pooled(ds, facts) for p, ds in docs_of.items()}
    dx_patients: dict[str, set[str]] = defaultdict(set)
    for d, f in facts.items():
        if f.dx:
            dx_patients[f.dx].add(pseud_of[d])
    rare_dx = frozenset(x for x, p in dx_patients.items() if len(p) <= cfg.rare_dx_max_patients)
    plevel = {p: 0 for p in pooled}
    # patients with no quasi-identifiers at all cannot be singled out by them
    active = {p for p, f in pooled.items() if f.age is not None or f.pin or f.dx or f.birth_year is not None or f.tehsil}
    for _ in range(MAX_LEVEL + 1):
        classes: dict[tuple, set[str]] = defaultdict(set)
        for p, f in pooled.items():
            classes[qi_key(f, plevel[p], cfg, rare_dx)].add(p)
        changed = False
        for p in sorted(active):
            if plevel[p] < MAX_LEVEL and len(classes[qi_key(pooled[p], plevel[p], cfg, rare_dx)]) < k:
                nxt = plevel[p] + 1
                if nxt == 5 and pooled[p].dx not in rare_dx:
                    nxt = 6  # suppressing a common diagnosis would not help; coarsen the age instead
                plevel[p] = nxt
                changed = True
        if not changed:
            break
    level = {d: plevel[pseud_of[d]] for d in facts}
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
    if level >= 3:
        if f.birth_year is not None:
            for fld, a, b, fhir in f.dob_spans:
                new = dob_text(f.birth_year, level, fhir)
                if new is not None:
                    out[fld].append((a, b, new))
        for fld, a, b in f.tehsil_spans:
            out[fld].append((a, b, "[TEHSIL]"))
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
