"""Medical guard: finds drugs, doses, frequencies, durations, vitals, lab values, ages, length of stay.

Two uses:
  1. veto: PII hits that sit inside these spans are dropped (a dose is not a phone, a drug is not a person)
  2. facts: ages etc. are read from here for linkage and generalization
"""
from __future__ import annotations

import regex as re

from ..contracts import MedKind, MedSpan, Unit
from . import lexicon as L

_UNIT = r"(?:mg|mcg|µg|g|gm|ml|iu|units?|u|%|meq|mmol)"
_PATTERNS: list[tuple[MedKind, re.Pattern]] = [
    (MedKind.DRUG, re.compile(
        r"(?<![\p{L}])(?i:tab|cap|inj|syp|syr|oint|susp|sachet|tablet|capsule|injection|syrup)\.?\s+[\p{L}][\p{L}\-]*"
        r"(?:\s+(?:\d+(?:\.\d+)?(?:\s?" + _UNIT + r")?(?:/\d+)?|[A-Z][\p{L}]*)){0,3}")),
    (MedKind.FREQ, re.compile(r"(?<![\p{L}\d])(?:OD|BD|BID|TDS|TID|QID|HS|SOS|PRN|STAT|[01]-[01]-[01](?:-[01])?)(?![\p{L}\d])")),
    (MedKind.DURATION, re.compile(r"(?<![\p{L}\d])(?:x|for)\s*\d+\s*(?:days?|d|weeks?|wks?|months?|दिन|हफ्ते|महीने)(?![\p{L}])|\d+\s*(?:दिन|हफ्ते|महीने)", re.I)),
    (MedKind.DOSE, re.compile(r"(?<![\p{L}\d.])\d+(?:\.\d+)?\s?" + _UNIT + r"(?![\p{L}\d])", re.I)),
    (MedKind.VITAL, re.compile(
        r"(?<![\p{L}])(?:BP\s*:?\s*\d{2,3}\s*/\s*\d{2,3}(?:\s*mm\s?Hg)?|(?:HR|pulse|PR|RR)\s*:?\s*\d{2,3}(?:\s*(?:/min|bpm|per min))?|"
        r"Temp(?:erature)?\s*:?\s*\d{2,3}(?:\.\d)?\s*(?:°\s?)?[FC]?|SpO2\s*:?\s*\d{2,3}\s*%?)", re.I)),
    (MedKind.LAB, re.compile(
        r"(?<![\p{L}])(?:Hb|WBC|TLC|Platelets?|PLT|Creatinine|Urea|RBS|FBS|PPBS|Na|K|CRP|ALT|AST|SGPT|SGOT|HbA1c|ESR|TSH|Bilirubin)"
        r"\s*[:=\-]?\s*\d+(?:\.\d+)?\s*(?:g/dL|mg/dL|mEq/L|/cumm|/mm3|%|U/L|mg/L|IU/L|ng/mL)?")),
    (MedKind.AGE, re.compile(
        r"(?<![\p{L}\d./-])\d{1,3}\s*(?:years?|yrs?|y/o|yo|saal|वर्ष|साल|y)(?:\s*old)?(?![\p{L}\d])|(?<![\d])\d{1,3}\s*/\s*[MF](?![\p{L}])", re.I)),
    (MedKind.LOS, re.compile(r"(?:length\s*of\s*stay|los|stay)\s*(?:\(days\))?\s*[:\-]?\s*\d+\s*(?:days?|दिन)?", re.I)),
]


def find_medical(unit_or_text) -> list[tuple[int, int, MedKind]]:
    """(start, end, kind) in NORMALIZED coordinates."""
    text = unit_or_text.norm.text if isinstance(unit_or_text, Unit) else unit_or_text
    out: list[tuple[int, int, MedKind]] = []
    for kind, rx in _PATTERNS:
        for m in rx.finditer(text):
            out.append((m.start(), m.end(), kind))
    # known drug words with optional strength
    for m in re.finditer(r"(?<![\p{L}])([\p{L}][\p{L}\-]+)(?:\s+\d+(?:\.\d+)?(?:\s?" + _UNIT + r")?)?", text):
        if m.group(1).lower() in L.DRUG_WORDS:
            out.append((m.start(), m.end(), MedKind.DRUG))
    return out


def med_spans(unit: Unit) -> list[MedSpan]:
    res = []
    for s, e, k in find_medical(unit):
        a, b = unit.norm.to_orig(s, e)
        res.append(MedSpan(unit.doc_id, unit.field, a, b, k))
    return res
