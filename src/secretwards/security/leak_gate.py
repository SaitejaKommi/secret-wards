"""Leak gate: the last check before anything is written.

Two independent checks over every output record:
  A. raw-value check: every value the detectors found anywhere in this run (name tokens, phones,
     emails, ABHA / insurance / MRN ids) must not appear in ANY output record, in any casing or
     separator style. This catches mentions that detection missed in one place but caught in another.
  B. residual-pattern scan: detector-independent regexes (mobile numbers, emails, ABHA, +91) over the
     output text, so even values detection never saw are caught when they look like identifiers.
Repair first: leaked name words / identifier-looking strings are replaced by placeholders and the
record is re-checked; a record that still leaks is quarantined (never written). Own-record dates are
checked too (a date that survived unshifted).
Honest limit: values that look like nothing (an unusual name never detected anywhere) cannot be found.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import regex as re

from ..contracts import ID_TYPES, PIIType, QReason, QuarantineEntry, RedactedRecord
from ..detect import lexicon as L
from ..normalize.dates import find_dates
from ..normalize.text import normalize, ocr_digit_view

_WORD = re.compile(r"[\p{L}\p{M}]+")
_PHONE_RES = re.compile(r"(?<!\d)(?:\+?91[\s\-.]*)?[6-9](?:[\s\-.]?\d){9}(?!\d)")
_EMAIL_RES = re.compile(r"[\p{L}\d._%+\-]+@[\p{L}\d\-]+(?:\.[\p{L}\d\-]+)+")
_DOCTOR = re.compile(
    r"(?<![\p{L}\d])(?:Dr|DR|dr|Doctor|डॉ|डॉक्टर)\.?\s*((?:[\p{Lu}][\p{L}'’\-]*\.?|[\u0900-\u097F]+)"
    r"(?:\s+(?:[\p{Lu}][\p{L}'’\-]*\.?|[\u0900-\u097F]+)){0,2})")


def _doctor_words(n: str) -> set[tuple[int, int]]:
    """(start, end) of every word inside a 'Dr. X Y' mention of the normalized text."""
    out: set[tuple[int, int]] = set()
    for m in _DOCTOR.finditer(n):
        for w in _WORD.finditer(n, m.start(1), m.end(1)):
            out.add((w.start(), w.end()))
    return out


_ABHA_RES = re.compile(r"(?<!\d)(?:\d{2}[-\s]\d{4}[-\s]\d{4}[-\s]\d{4}|\d{14})(?!\d)")


@dataclass
class RawValues:
    names: set[str] = field(default_factory=set)  # lowercased words
    phones: set[str] = field(default_factory=set)  # 10 digits
    emails: set[str] = field(default_factory=set)
    abha: set[str] = field(default_factory=set)
    alnum: dict[int, set[str]] = field(default_factory=lambda: defaultdict(set))  # insurance / mrn by length


def collect(results) -> RawValues:
    rv = RawValues()
    for r in results.values():
        for u in r.units:
            for s in r.spans[u.field]:
                raw = u.original[s.start:s.end]
                t = s.type
                if t == PIIType.NAME:
                    if s.role == "doctor":
                        continue  # "Dr. <name>" lines are medical context and stay in the release
                    for m in _WORD.finditer(raw):
                        w = m.group()
                        wl = w.lower()
                        if len(w) < 4 and not ("ऀ" <= w[0] <= "ॿ" and len(w) >= 3):
                            continue
                        if L.is_drug(w) or L.is_clinical(w) or L.is_common(w) or w in L.HI_STOP:
                            continue
                        rv.names.add(wl)
                elif t == PIIType.PHONE:
                    d = "".join(c for c in ocr_digit_view(normalize(raw).text) if c.isdigit())
                    if len(d) >= 10:
                        rv.phones.add(d[-10:])
                elif t == PIIType.EMAIL:
                    rv.emails.add(raw.strip().lower())
                elif t == PIIType.ABHA:
                    d = "".join(c for c in ocr_digit_view(normalize(raw).text) if c.isdigit())
                    if len(d) == 14:
                        rv.abha.add(d)
                elif t in ID_TYPES:
                    a = re.sub(r"[^A-Za-z0-9]", "", raw).upper()
                    nd = sum(ch.isdigit() for ch in a)
                    if len(a) >= 6 and nd >= 3 and nd >= 0.3 * len(a):  # real ids, not words that landed in an id column
                        rv.alnum[len(a)].add(a)
    return rv


def _digit_windows(s: str, n: int):
    for i in range(0, max(0, len(s) - n + 1)):
        yield s[i:i + n]


def scan(rv: RawValues, text: str) -> dict[str, int]:
    """Count leaks of each kind in one piece of output text."""
    hits = defaultdict(int)
    if not text:
        return hits
    n = normalize(text).text
    view = ocr_digit_view(n)
    doc_words = _doctor_words(n)
    for m in _WORD.finditer(n):
        if m.group().lower() in rv.names and (m.start(), m.end()) not in doc_words:
            hits["name"] += 1
    # digit streams: join digits inside each whitespace/punct-separated numeric chain
    chains = re.findall(r"\+?\d[\d\s\-.()]*\d", view)
    for ch in chains:
        ds = "".join(c for c in ch if c.isdigit())
        for w in _digit_windows(ds, 10):
            if w in rv.phones:
                hits["phone"] += 1
                break
        if rv.abha:
            for w in _digit_windows(ds, 14):
                if w in rv.abha:
                    hits["abha"] += 1
                    break
    low = n.lower()
    for e in rv.emails:
        if e in low:
            hits["email"] += 1
    if rv.alnum:
        stream = re.sub(r"[^A-Za-z0-9]", "", view).upper()
        for L_, vals in rv.alnum.items():
            for w in _digit_windows(stream, L_):
                if w in vals:
                    hits["id"] += 1
                    break
    # detector-independent residual patterns
    if _EMAIL_RES.search(n):
        hits["residual_email"] += 1
    if _PHONE_RES.search(view):
        hits["residual_phone"] += 1
    if _ABHA_RES.search(view):
        hits["residual_abha"] += 1
    return hits


def _repair(rv: RawValues, text: str, seen: set | None = None) -> str:
    """Replace leaked words / identifier-looking strings by placeholders."""
    if not text:
        return text
    n = normalize(text)
    spans: list[tuple[int, int, str]] = []
    doc_words = _doctor_words(n.text)
    for m in _WORD.finditer(n.text):
        if m.group().lower() in rv.names and (m.start(), m.end()) not in doc_words:
            a, b = n.to_orig(m.start(), m.end())
            spans.append((a, b, "[NAME]"))
            if seen is not None:
                seen.add(m.group().lower())
    view = ocr_digit_view(n.text)
    for m in _PHONE_RES.finditer(view):
        a, b = n.to_orig(m.start(), m.end())
        spans.append((a, b, "[PHONE]"))
    for m in _EMAIL_RES.finditer(n.text):
        a, b = n.to_orig(m.start(), m.end())
        spans.append((a, b, "[EMAIL]"))
    for m in _ABHA_RES.finditer(view):
        a, b = n.to_orig(m.start(), m.end())
        spans.append((a, b, "[ID]"))
    for ch in re.finditer(r"\+?\d[\d\s\-.()]*\d", view):
        ds = "".join(c for c in ch.group() if c.isdigit())
        if any(w in rv.phones for w in _digit_windows(ds, 10)) or any(w in rv.abha for w in _digit_windows(ds, 14)):
            a, b = n.to_orig(ch.start(), ch.end())
            spans.append((a, b, "[ID]"))
    spans.sort()
    out, pos = [], 0
    for a, b, rep in spans:
        if a < pos:
            continue
        out.append(text[pos:a])
        out.append(rep)
        pos = b
    out.append(text[pos:])
    return "".join(out)


def gate(records: dict[str, RedactedRecord], results, cfg, mode: str = "quarantine") -> tuple[dict[str, RedactedRecord], list[QuarantineEntry], dict]:
    """mode "quarantine" (legacy): a record that still leaks after repair is dropped.
    mode "redact" (output contract): never drop a record; blank only the field that still leaks."""
    rv = collect(results)
    stats = defaultdict(int)
    repaired_words: set[str] = set()
    kept: dict[str, RedactedRecord] = {}
    quarantined: list[QuarantineEntry] = []
    for doc_id, rec in records.items():
        res = results[doc_id]
        own_dates = set()
        for u in res.units:
            for s in res.spans[u.field]:
                if s.type == PIIType.DATE:
                    own_dates.add(normalize(u.original[s.start:s.end]).text.lower())
        for attempt in range(2):
            units = [("text", rec.text)] + [(k, v) for k, v in rec.fields.items()]
            hits: dict[str, int] = defaultdict(int)
            for _k, v in units:
                for kind, c in scan(rv, v).items():
                    hits[kind] += c
                nt = normalize(v).text
                for dm in find_dates(nt):
                    if nt[dm.start:dm.end].lower() in own_dates:
                        hits["own_date"] += 1
            if not hits:
                break
            for k, c in hits.items():
                stats[f"{'repaired' if attempt == 0 else 'unrepaired'}_{k}"] += c
            if attempt == 0:
                rec.text = _repair(rv, rec.text, repaired_words)
                for k in list(rec.fields):
                    rec.fields[k] = _repair(rv, rec.fields[k], repaired_words)
        else:
            if mode != "redact":
                quarantined.append(QuarantineEntry(doc_id, QReason.LEAK_GATE, "record"))
                continue
            if scan(rv, rec.text):
                rec.text = "[REDACTED]"
            for k in list(rec.fields):
                if scan(rv, rec.fields[k]):
                    rec.fields[k] = "[REDACTED]"
            stats["fields_blanked"] += 1
        kept[doc_id] = rec
    stats["distinct_name_words_repaired"] = len(repaired_words)  # a count only: the words are PII-adjacent
    stats["records_checked"] = len(records)
    stats["records_quarantined"] = len(quarantined)
    return kept, quarantined, dict(sorted(stats.items()))
