"""Column-header hints. Hints only raise priors; content validators always run too,
because exported tables often have shifted columns."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import regex as re


@dataclass(frozen=True)
class Hint:
    kind: str  # name phone email address city pin dob date id age sex ""
    role: str = ""


_REL = re.compile(r"guardian|rishtedar|sambandhi|father|husband|relative|attendant|kin|spouse|wife|mother|पिता|पति|पत्नी|अभिभावक|नाम\s*\(?\s*पिता", re.I)
_DOC = re.compile(r"doctor|\bdr\b|consultant|referred|physician|डॉ", re.I)
_NAME = re.compile(r"\bname\b|\bnaam\b|\bnm\b|नाम|^pt\b|\bpatient\b|\bpt\b|\bmember\b|रोगी|मरीज", re.I)
_PHONE = re.compile(r"phone|mobile|contact|\btel\b|\bcell\b|\bmob\b|\bmobno\b|\bph\.?\s*(?:no|num|number)\b|\bph\.$|\bsampark\b|whatsapp|मोबाइल|फोन|फ़ोन|संपर्क", re.I)
_EMAIL = re.compile(r"e-?mail|ईमेल", re.I)
_ADDR = re.compile(r"address|\baddr\b|residence|\bpata\b|पता|ghar|locality|village|mohalla|मोहल्ला", re.I)
_CITY = re.compile(r"\bcity\b|\btown\b|district|\bdistt\b|\bzila\b|\bjila\b|शहर|जिला", re.I)
_PIN = re.compile(r"\bpin\b|pincode|\bzip\b|postal|पिन", re.I)
_DOB = re.compile(r"\bdob\b|birth|d\.o\.b|\bjanm\b|\bjnm\b|जन्म", re.I)
_DATE = re.compile(r"\bdate\b|\bdt\b|admit|admission|discharge|\bdoa\b|\bdod\b|तिथि|तारीख|भर्ती|छुट्टी|tareekh|\btithi\b", re.I)
_ID = re.compile(r"\bmrn\b|uhid|\breg\b|registration|\buid\b|\bid\b|\bno\.?$|number|संख्या|क्रम|abha|insurance|policy|\bhospital no", re.I)
_AGE = re.compile(r"\bage\b|\byears?\b|\bumar\b|आयु|उम्र|\bage/sex\b|\bage/gender\b", re.I)
_NONPERSON = re.compile(
    r"test|drug|medic|diagnos|hospital|department|dept|\bward|facility|organi[sz]ation|panel|\bitem|service|procedure|specimen|"
    r"sample|insurer|company|clinic|ticket|title|\bform\b|\bfile\b|report|\blab\b|vaccine|symptom|complaint|disease|speciality|specialty", re.I)
_SEX = re.compile(r"\bsex\b|gender|\bling\b|\bsx\b|लिंग|\bm/f\b", re.I)


@lru_cache(maxsize=8192)  # pure and called once per detector per cell with the same few dozen headers
def hint_for(header: str) -> Hint:
    h = header.strip().lower()
    if not h:
        return Hint("")
    if _EMAIL.search(h):
        return Hint("email")
    if _PHONE.search(h):
        return Hint("phone")
    if _DOB.search(h):
        return Hint("dob")
    if _PIN.search(h):
        return Hint("pin")
    if _REL.search(h) and (_NAME.search(h) or "father" in h or "husband" in h or "guardian" in h or "rishtedar" in h or "relative" in h or "पिता" in h or "पति" in h):
        return Hint("name", "relative")
    if _DOC.search(h):
        return Hint("name", "doctor")
    if _ADDR.search(h):
        return Hint("address")
    if _CITY.search(h):
        return Hint("city")
    if _ID.search(h) and not _DATE.search(h):  # "registration date" / "admission date" are dates, not ids
        return Hint("id")
    if _AGE.search(h) and not _SEX.search(h.replace("age/sex", "")):
        return Hint("age")
    if _SEX.search(h):
        return Hint("sex")
    if _DATE.search(h):
        return Hint("date")
    if _NAME.search(h) and not _NONPERSON.search(h):
        return Hint("name", "patient")
    if _NONPERSON.search(h):
        return Hint("nonperson")  # a test / drug / hospital / department column: capitalised words there are not people
    return Hint("")
