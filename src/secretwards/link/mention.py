"""Extract linkage evidence (a Mention) from one processed document.

The Mention holds raw values and lives in memory only. Evidence comes from detected spans
(names, phones, ids, dates, pin) and from the medical guard / header hints (age, sex).
"""
from __future__ import annotations

import regex as re

from ..contracts import Document, MedKind, Mention, PIIType
from ..detect.headers import hint_for
from ..normalize.dates import find_dates
from ..normalize.text import normalize, ocr_digit_view
from ..normalize.translit import skeleton

_DOB_CUE = re.compile(r"(?:dob|d\.o\.b|date\s+of\s+birth|born|birth|जन्म|janm)", re.I)
_SEX_LABEL = re.compile(r"(?:\bsex|\bgender|लिंग)\s*[:\-]?\s*(male|female|m|f|पुरुष|महिला)(?![\p{L}])", re.I)
_SEX_AGE = re.compile(r"\d{1,3}\s*(?:y|yrs?|years?|saal|वर्ष)?\s*/\s*(M|F|male|female)(?![\p{L}])", re.I)
_SEX_WORD = re.compile(r"(?<![\p{L}])(male|female|पुरुष|महिला)(?![\p{L}])", re.I)
_MALE_HON = re.compile(r"(?<![\p{L}])(?:mr|shri|sh|sri|श्री|श्रीमान)(?![\p{L}])\.?", re.I)
_FEMALE_HON = re.compile(r"(?<![\p{L}])(?:mrs|ms|smt|kumari|श्रीमती|कुमारी)(?![\p{L}])\.?", re.I)
_SON = re.compile(r"(?<![\p{L}\d])(?:s\s*/\s*o|son\s+of|सुपुत्र|पुत्र)(?![\p{L}])", re.I)
_DAUGHTER = re.compile(r"(?<![\p{L}\d])(?:d\s*/\s*o|w\s*/\s*o|daughter\s+of|wife\s+of|सुपुत्री|पुत्री|पत्नी)(?![\p{L}])", re.I)
_PIN = re.compile(r"(?<!\d)([1-9]\d{5})(?!\d)")
_WORD = re.compile(r"[\p{L}\p{M}]+")


def _sex_from(tok: str) -> str | None:
    t = tok.strip().lower()
    if t in ("m", "male", "पुरुष"):
        return "M"
    if t in ("f", "female", "महिला"):
        return "F"
    return None


def build_mention(doc: Document, units, spans, meds) -> Mention:
    names_pat: list[tuple[str, ...]] = []
    names_any: list[tuple[str, ...]] = []
    rels: list[tuple[str, ...]] = []
    phones, emails, abha, ins, mrn = [], [], [], [], []
    dob = None
    years: list[int] = []
    age = None
    sex = None
    pin = None
    place: list[str] = []
    sex_votes: list[str] = []

    for u in units:
        text = u.original
        ntext = u.norm.text
        view = ocr_digit_view(ntext)
        hint = hint_for(u.header)
        for s in spans[u.field]:
            raw = text[s.start:s.end]
            t = s.type
            if t == PIIType.NAME:
                words = tuple(_WORD.findall(raw))
                if not words:
                    continue
                if s.role == "relative":
                    rels.append(words)
                elif s.role == "doctor":
                    pass
                elif s.role == "patient":
                    names_pat.append(words)
                else:
                    names_any.append(words)
            elif t == PIIType.PHONE:
                d = "".join(c for c in normalize(raw).text if c.isdigit())
                d = "".join(c for c in ocr_digit_view(normalize(raw).text) if c.isdigit()) or d
                if len(d) >= 10:
                    phones.append(d[-10:])
            elif t == PIIType.EMAIL:
                emails.append(raw.strip().lower())
            elif t == PIIType.ABHA:
                d = "".join(c for c in ocr_digit_view(normalize(raw).text) if c.isdigit())
                if len(d) == 14:
                    abha.append(d)
            elif t == PIIType.INSURANCE:
                ins.append(re.sub(r"[^A-Za-z0-9]", "", raw).upper())
            elif t == PIIType.MRN:
                mrn.append(re.sub(r"[^A-Za-z0-9]", "", raw).upper())
            elif t == PIIType.ID:
                digits = "".join(c for c in ocr_digit_view(normalize(raw).text) if c.isdigit())
                alnum = re.sub(r"[^A-Za-z0-9]", "", raw).upper()
                if len(digits) == 12 and len(alnum) == 12:
                    mrn.append("AADHAAR" + digits)  # a national id belongs to one person
                elif re.fullmatch(r"[A-Z]{5}\d{4}[A-Z]", alnum):
                    mrn.append("PAN" + alnum)
            elif t == PIIType.PINCODE:
                d = "".join(c for c in ocr_digit_view(normalize(raw).text) if c.isdigit())
                if len(d) == 6:
                    pin = pin or d
            elif t == PIIType.ADDRESS:
                m = _PIN.search(ocr_digit_view(normalize(raw).text))
                if m:
                    pin = pin or m.group(1)
                for w in _WORD.findall(raw):
                    k = skeleton(w)
                    if len(k) >= 3:
                        place.append(k)
            elif t == PIIType.DATE:
                nd = ocr_digit_view(normalize(raw).text)
                dm = find_dates(nd)
                if not dm:
                    continue
                d0 = dm[0]
                ctx = text[max(0, s.start - 28):s.start]
                if hint.kind == "dob" or _DOB_CUE.search(ctx):
                    if d0.d is not None and dob is None:
                        dob = f"{d0.y:04d}-{d0.m:02d}-{d0.d:02d}"
                else:
                    years.append(d0.y)
        # age / sex from structured hints and from the medical guard
        stripped = text.strip()
        if hint.kind == "age" and re.fullmatch(r"\d{1,3}", stripped) and age is None:
            age = int(stripped)
        if hint.kind == "sex" or (hint.kind == "age" and "sex" in u.header):
            sx = _sex_from(stripped)
            if sx:
                sex_votes.append(sx)
        for m in meds[u.field]:
            if m.kind == MedKind.AGE and age is None:
                mm = re.match(r"\s*(\d{1,3})", text[m.start:m.end])
                if mm and 0 <= int(mm.group(1)) <= 120:
                    age = int(mm.group(1))
        if hint.kind in ("age", "sex", "") or u.field is None:
            m = _SEX_LABEL.search(ntext)
            if m:
                sx = _sex_from(m.group(1))
                if sx:
                    sex_votes.append(sx)
            m = _SEX_AGE.search(ntext)
            if m:
                sx = _sex_from(m.group(1))
                if sx:
                    sex_votes.append(sx)
            if u.field is None:
                m = _SEX_WORD.search(ntext)
                if m:
                    sx = _sex_from(m.group(1))
                    if sx:
                        sex_votes.append(sx)
        if hint.kind == "name" or u.field is None:
            if _MALE_HON.search(ntext) or _SON.search(ntext):
                sex_votes.append("m?")
            if _FEMALE_HON.search(ntext) or _DAUGHTER.search(ntext):
                sex_votes.append("f?")
    firm = [v for v in sex_votes if v in ("M", "F")]
    if firm:
        sex = max(("M", "F"), key=lambda x: (firm.count(x), x == "M"))
    else:
        soft = [v[0].upper() for v in sex_votes]
        if soft and soft.count("M") != soft.count("F"):
            sex = "M" if soft.count("M") > soft.count("F") else "F"
    if names_pat:
        name = max(names_pat, key=lambda w: (len(w), -names_pat.index(w)))
    elif names_any:
        name = names_any[0]
    else:
        name = ()
    ref_year = min(years) if years else None

    def uniq(xs):
        return tuple(dict.fromkeys(xs))

    return Mention(
        doc.doc_id, doc.hospital, name_tokens=name, rel_tokens=uniq(rels), phones=uniq(phones), emails=uniq(emails),
        abha=uniq(abha), insurance=uniq(ins), mrn=uniq(mrn), dob=dob, ref_year=ref_year, age=age, sex=sex, pin=pin,
        place_tokens=uniq(place))
