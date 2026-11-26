"""Validator-backed rules: phones, emails, ABHA / insurance / MRN ids, dates, PIN codes.

Works on the normalized text; OCR digit confusions (O/l/S in digit-heavy tokens) are
repaired in a same-length view so offsets stay valid.
"""
from __future__ import annotations

import regex as re

from ..contracts import PIIType, Span, Unit
from ..normalize.dates import find_dates
from ..normalize.text import ocr_digit_view
from .base import Collector
from .headers import hint_for

_RUN = re.compile(r"[+(]?\d[\d\s\-.()]*\d")
_EMAIL = re.compile(r"[\p{L}\d._%+\-]+@[\p{L}\d\-]+(?:\.[\p{L}\d\-]+)+")
_ABHA = re.compile(r"(?<![\d])(?:\d{2}[-\s]\d{4}[-\s]\d{4}[-\s]\d{4}|\d{4}\s\d{4}\s\d{4}\s\d{2}|\d{14})(?![\d])")
_PIN_CUE = re.compile(
    r"(?:pin\s*code|pincode|pin|zip(?:\s*code)?|postal\s*code|पिन\s*कोड|पिन)\s*[:\-#.]*\s*([1-9]\d{2}\s?\d{3})(?!\d)", re.I)
_INS_PREFIX = re.compile(
    r"\b(?:POL|CGHS|ECHS|ESIC|PMJAY|RSBY|HDFC|ICICI|STAR|NIVA|BAJAJ|CARE|LIC|TATA|UIIC|NIA|OICL|MAXBUPA)[A-Z]*"
    r"(?:[-/ ]?\d[\d/\-]{4,})")
_INS_CUE = re.compile(
    r"\b(?:policy|insurance|claim|tpa|ayushman|pmjay|cghs|member\s*id)\b[^\n:]{0,24}?[:\-#]\s*([A-Za-z0-9][A-Za-z0-9/\-]{5,})", re.I)
_MRN_PATTERNS = re.compile(
    r"\b(?:UHID\s?\d{5,}|MRN[/\-]\d{2,4}[/\-]\d{3,}|REG[-/]\d{4,}|H\d-\d{2}-\d{4,}|PT\d{6,}|OPD[-/]?\d{5,}|IPD[-/]?\d{5,})\b")
_MRN_CUE = re.compile(
    r"\b(?:mrn|uhid|reg(?:istration)?\.?\s*(?:no\.?|number)?|hosp(?:ital)?\.?\s*(?:no\.?|number)|patient\s*id|pt\.?\s*id|"
    r"ip\s*(?:no|number)|op\s*(?:no|number)|case\s*no|uid|file\s*no)\s*[:\-#.]*\s*([A-Za-z0-9][A-Za-z0-9/\-]{3,})", re.I)
_ID_GENERIC = re.compile(r"\b[A-Z]{2,6}[-/]?\d{5,}\b|\b\d{4}/\d{4,}\b")


def valid_phone_digits(d: str) -> bool:
    n = len(d)
    if n == 10:
        return d[0] in "6789"
    if n == 11 and d[0] == "0":
        return d[1] in "123456789"
    if n == 12 and d.startswith("91"):
        return d[2] in "6789"
    if n == 13 and d.startswith("091"):
        return d[3] in "6789"
    if n == 14 and d.startswith("0091"):
        return d[4] in "6789"
    return False


def find_phones(view: str) -> list[tuple[int, int]]:
    out = []
    for m in _RUN.finditer(view):
        run = m.group()
        base = m.start()
        groups = [(base + g.start(), base + g.end()) for g in re.finditer(r"\d+", run)]
        i = 0
        while i < len(groups):
            digits = ""
            found = -1
            for j in range(i, len(groups)):
                digits += view[groups[j][0]:groups[j][1]]
                if len(digits) > 14:
                    break
                if valid_phone_digits(digits):
                    found = j
            if found >= 0:
                s = groups[i][0]
                if s > 0 and view[s - 1] in "+(":
                    s -= 1
                out.append((s, groups[found][1]))
                i = found + 1
            else:
                i += 1
    return out


class RuleDetector:
    name = "rules"

    def detect(self, unit: Unit) -> list[Span]:
        col = Collector(unit, self.name)
        text = unit.norm.text
        view = ocr_digit_view(text)
        hint = hint_for(unit.header)

        for m in _EMAIL.finditer(text):
            col.add(m.start(), m.end(), PIIType.EMAIL, 0.99)
        for s, e in find_phones(view):
            col.add(s, e, PIIType.PHONE, 0.95)
        for m in _ABHA.finditer(view):
            col.add(m.start(), m.end(), PIIType.ABHA, 0.9)
        for m in _INS_PREFIX.finditer(text):
            col.add(m.start(), m.end(), PIIType.INSURANCE, 0.9)
        for m in _INS_CUE.finditer(text):
            if any(c.isdigit() for c in m.group(1)):
                col.add(m.start(1), m.end(1), PIIType.INSURANCE, 0.85)
        for m in _MRN_PATTERNS.finditer(text):
            col.add(m.start(), m.end(), PIIType.MRN, 0.9)
        for m in _MRN_CUE.finditer(text):
            if any(c.isdigit() for c in m.group(1)):
                col.add(m.start(1), m.end(1), PIIType.MRN, 0.85)
        for m in _ID_GENERIC.finditer(text):
            col.add(m.start(), m.end(), PIIType.ID, 0.6)
        for m in _PIN_CUE.finditer(view):
            col.add(m.start(1), m.end(1), PIIType.PINCODE, 0.9)
        for dm in find_dates(view):
            col.add(dm.start, dm.end, PIIType.DATE, 0.9)

        # header-driven whole-cell rules (fail closed on malformed values in typed columns)
        stripped = text.strip()
        if stripped:
            s0 = text.index(stripped[0])
            e0 = s0 + len(stripped)
            nd = sum(c.isdigit() for c in view)
            nonspace = sum(not c.isspace() for c in stripped)
            if hint.kind in ("address", "city") and re.fullmatch(r"[1-9]\d{2}\s?\d{3}", view.strip()):
                col.add(s0, e0, PIIType.PINCODE, 0.8)
            elif hint.kind == "phone" and nd >= 6 and nd >= 0.6 * nonspace and not any(x.type == PIIType.PHONE for x in col.spans):
                col.add(s0, e0, PIIType.PHONE, 0.6)
            elif hint.kind == "email" and "@" in stripped:
                col.add(s0, e0, PIIType.EMAIL, 0.6)
            elif hint.kind == "pin" and re.fullmatch(r"[1-9]\d{2}\s?\d{3}", view.strip()):
                col.add(s0, e0, PIIType.PINCODE, 0.9)
            elif hint.kind == "id" and any(c.isdigit() for c in stripped) and len(stripped) >= 4 and len(stripped) <= 40 \
                    and not any(x.type in (PIIType.MRN, PIIType.ABHA, PIIType.INSURANCE, PIIType.ID) for x in col.spans):
                col.add(s0, e0, PIIType.MRN, 0.7)
            elif hint.kind in ("date", "dob") and not any(x.type == PIIType.DATE for x in col.spans) \
                    and nd >= 4 and len(stripped) <= 30:
                col.add(s0, e0, PIIType.DATE, 0.6)
        return col.spans
