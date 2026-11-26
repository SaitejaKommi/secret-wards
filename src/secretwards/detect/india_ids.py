"""Indian identifiers by shape + context: Aadhaar (full and masked), PAN, hospital record numbers.

Why a separate detector: `rules.py` covers phones, ABHA, insurance and a few MRN styles; this adds the
India-specific ids the practice data showed leaking (Aadhaar without a recognised column, PAN, IPD/UHID numbers
whose digits are split by separators) without editing the lead's files.

Design (no value lists, only shapes and labels):
- Aadhaar: 12 digits, first digit 2-9, optionally grouped 4-4-4 with one separator style. The Verhoeff checksum
  is NOT used as a gate (synthetic generators often ignore it); a label or column meaning raises the score.
  Masked Aadhaar (XXXX XXXX 1234): the visible last 4 digits match the attacker's registry, so the whole thing goes.
- PAN: AAAAA9999A with a valid 4th-letter holder code. A "pan" label only boosts a PAN-shaped token: the word
  "pan" alone (pan masala, paan chewing) never redacts anything.
- Hospital numbers: UPPERCASE prefix + digit groups joined by - or / (IPD-2026-00123, IP/26/00045) with >=5 digits,
  or any token after an id label ("Reg No:", "UHID", "पंजीकरण सं."). Digit groups that read as a date, and tokens
  followed by a unit (mg, /min, %), are rejected so vitals, labs and dates are never taken.
Types: hospital numbers -> MRN (they feed same-hospital linking); Aadhaar / PAN -> ID (redacted, not used to link).
"""
from __future__ import annotations

import regex as re

from ..contracts import PIIType, Span, Unit
from ..normalize.text import ocr_digit_view
from .base import Collector

# ---- column meanings (header is the lowercased column name / last JSON key, '_' -> ' ')
_AADHAAR_HDR = re.compile(r"aadh?aa?r|adhaa?r|\buid(?:ai)?\b|आधार|uidai", re.I)
_PAN_HDR = re.compile(r"(?<![a-z])pan(?:\s*(?:no|num|number|card|id))?(?![a-z])|permanent\s*account|पैन", re.I)
_HOSP_ID_HDR = re.compile(
    r"\b(?:uhid|mrn|crn|panjikaran|panjiyan)\b|"
    r"\b(?:cr|ipd?|opd?|adm(?:ission)?|case|file|bed\s*head|hospital|patient|record|reg(?:n|d|istration)?)\s*(?:no|num|number|id)\b|"
    r"पंजीकरण|पंजीयन|भर्ती\s*सं|आईपीडी|ओपीडी|क्रमांक", re.I)
_DATE_HDR = re.compile(r"date|\bdt\b|tithi|tareekh|तारीख|तिथि|दिनांक|time|\bdob\b|birth|जन्म", re.I)

# ---- in-text labels
_AADHAAR_CUE = re.compile(r"(?:aadh?aa?r|adhaa?r|\buid(?:ai)?\b|आधार|यूआईडी)[^\n\d]{0,20}$", re.I)
_PAN_CUE = re.compile(r"(?:\bpan\b|permanent\s*account|पैन)[^\n\d]{0,20}$", re.I)

_AADHAAR = re.compile(r"(?<![\d\-/.])([2-9]\d{3})([ \-.]?)(\d{4})\2(\d{4})(?![\d\-/]|\.\d)")
_AADHAAR_MASKED = re.compile(
    r"(?<![\p{L}\d])(?:[xX*•●]{4}[ \-]?){2}\d{4}(?!\d)|(?<![\p{L}\d])[xX*]{8}\d{4}(?!\d)")
_PAN = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]{3}[ABCFGHJLPTEKabcfghjlptek][A-Za-z]\d{4}[A-Za-z](?![A-Za-z0-9])")

# UPPERCASE prefix (optionally with digits, e.g. a year-coded "DHH2026") then >=1 separated digit groups.
_HOSP_STRUCT = re.compile(
    r"(?<![\p{L}\d/\-])([A-Z]{2,6}\d{0,4}(?:[-/][A-Z]{1,6})?)((?:[-/]\d{2,8}){1,3})(?![\p{L}\d]|[-/]\d)")
# "<something> No / No. / ID / Number / सं. / संख्या / क्रमांक" then ':' or '#' then the id token
_ID_LABEL = re.compile(
    r"(?<![\p{L}\p{M}])((?:[\p{L}\p{M}.]+\s){0,2}?(?:no\.?|num(?:ber)?|id|#|सं\.?|संख्या|क्रमांक|नंबर|nambar))\s*[:#\-=]\s*"
    r"([A-Za-z\p{Devanagari}]{0,6}[A-Za-z0-9]*[/\-]?[A-Za-z0-9/\-]*\d[A-Za-z0-9/\-]*)", re.I)
_NOT_ID_LABEL = re.compile(
    r"mobile|\bmob\b|phone|\bph\b|contact|\btel\b|\bcell\b|whats|\bfone\b|मोबाइल|फोन|फ़ोन|\bbed\b|ward|room|floor|"
    r"\bage\b|batch|\blot\b|\btab\b|dose|\bbp\b|pulse|वार्ड|बेड|आयु|\bpin\b|\bzip\b|पिन|house|h\.?no|flat|plot|makan|मकान|"
    r"aadh|adha|आधार|\buid|\bpan\b|पैन|abha|policy|claim|\bbill\b|invoice|package|amount|token", re.I)
_UNIT_AFTER = re.compile(r"\s*(?:mg|mcg|ml|g\b|gm|kg|iu|%|/min|bpm|mmhg|/cumm|/ul|/dl|mmol|meq|units?\b|x\s*\d)", re.I)
_DATE_GROUPS = re.compile(r"^[-/](?:0?[1-9]|[12]\d|3[01])[-/](?:0?[1-9]|1[0-2])[-/](?:\d{2}|\d{4})$|"
                          r"^[-/](?:0?[1-9]|1[0-2])[-/](?:0?[1-9]|[12]\d|3[01])[-/](?:\d{2}|\d{4})$|"
                          r"^[-/](?:19|20)\d{2}[-/](?:0?[1-9]|1[0-2])[-/](?:0?[1-9]|[12]\d|3[01])$")


def _before(text: str, pos: int, n: int = 40) -> str:
    """Text on the same line just before pos (labels live there)."""
    a = max(0, pos - n)
    seg = text[a:pos]
    return seg.rsplit("\n", 1)[-1]


class IndiaIdDetector:
    name = "india_ids"

    def detect(self, unit: Unit) -> list[Span]:
        col = Collector(unit, self.name)
        text = unit.norm.text
        if not text.strip():
            return col.spans
        view = ocr_digit_view(text)
        hdr = unit.header
        is_aadhaar_col = bool(hdr and _AADHAAR_HDR.search(hdr))
        is_pan_col = bool(hdr and _PAN_HDR.search(hdr))

        # Aadhaar: full 12 digits
        for m in _AADHAAR.finditer(view):
            cued = is_aadhaar_col or bool(_AADHAAR_CUE.search(_before(view, m.start())))
            grouped = bool(m.group(2))
            score = 0.95 if cued else (0.9 if grouped else 0.8)
            col.add(m.start(), m.end(), PIIType.ID, score)
        # masked Aadhaar: the visible tail is what a registry matches on
        for m in _AADHAAR_MASKED.finditer(view):
            col.add(m.start(), m.end(), PIIType.ID, 0.9)

        # PAN: uppercase canonical shape anywhere; any case when a label or the column says PAN
        for m in _PAN.finditer(text):
            tok = m.group()
            cued = is_pan_col or bool(_PAN_CUE.search(_before(text, m.start())))
            if tok.isupper() or cued:
                col.add(m.start(), m.end(), PIIType.ID, 0.95 if cued else 0.9)

        # hospital record numbers by structure
        for m in _HOSP_STRUCT.finditer(text):
            groups = m.group(2)
            digits = sum(c.isdigit() for c in m.group(0))
            last = groups.rsplit("-", 1)[-1].rsplit("/", 1)[-1]
            if digits < 5 or len(last) < 3:
                continue
            if _DATE_GROUPS.match(groups):
                continue
            if _UNIT_AFTER.match(text, m.end()):
                continue
            col.add(m.start(), m.end(), PIIType.MRN, 0.9)

        # hospital record numbers by label ("IPD No: 2026/123", "पंजीकरण सं.: 45231")
        for m in _ID_LABEL.finditer(view):
            label, tok = m.group(1), m.group(2).rstrip("/-")
            if _NOT_ID_LABEL.search(label):
                continue
            if sum(c.isdigit() for c in tok) < 4 or len(tok) > 30:
                continue
            if _UNIT_AFTER.match(view, m.start(2) + len(tok)):
                continue
            if re.fullmatch(r"\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}", tok):
                continue  # a date after "Ref No: " stays a DATE (shifted, not erased)
            a, b = m.start(2), m.start(2) + len(tok)
            if any(sp.type == PIIType.ID and sp.start < b and a < sp.end for sp in col.spans):
                continue  # already an Aadhaar / PAN: a shorter MRN would win the merge and drop it
            col.add(m.start(2), m.start(2) + len(tok), PIIType.MRN, 0.9)

        # whole-cell rules for columns whose meaning is an identifier we know
        stripped = text.strip()
        if stripped and len(stripped) <= 40:
            s0 = text.index(stripped[0])
            e0 = s0 + len(stripped)
            nd = sum(c.isdigit() for c in view)
            covered = any(sp.start <= s0 and e0 <= sp.end for sp in col.spans)
            if not covered:
                if is_aadhaar_col and nd >= 4:
                    col.add(s0, e0, PIIType.ID, 0.9)  # includes masked / malformed Aadhaar
                elif is_pan_col and nd >= 1 and re.search(r"[A-Za-z]", stripped):
                    col.add(s0, e0, PIIType.ID, 0.9)
                elif hdr and _HOSP_ID_HDR.search(hdr) and not _DATE_HDR.search(hdr) and nd >= 3 and not re.fullmatch(r"\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}", stripped):
                    col.add(s0, e0, PIIType.MRN, 0.85)
        return col.spans
