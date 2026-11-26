"""Stand-in for the organisers' privacy attacker (docs/toolkit/docs/ATTACKS.md), for development-time measurement.

It is a library: it reads a population registry, known facts and a release (any folder of records), and returns the
attacker's beliefs. It NEVER reads an answer key; scoring against truth lives in scripts/attack_eval.py. It is not
part of main.py (the sandbox has no registry), and nothing here writes values anywhere.

Implemented as specified:
- evidence extraction from (label, value) pairs and free text: ages (exact, "52/M", "52 Yrs", "52 वर्ष", bands, "85+"),
  birth years, gender, district / tehsil / village / mohalla (vocabulary taken from the registry itself, Latin and
  Devanagari via the transliteration skeleton), PINs and PIN prefixes, phones and masked phones, emails, masked
  Aadhaar last 4, house numbers, names (doctors after "Dr." skipped), relatives after S/o D/o W/o C/O, dates,
  pseudonyms present in the release, shared reference values;
- A2/A3 record linkage: filters in the published order, a filter that would empty the candidates is skipped;
  weights full name x60, given x8, surname x3, relative x8, house x2;
- A4 profiles: records joined by pseudonyms present in the data and shared reference values, evidence pooled
  (age ranges intersected), attacked again;
- A5 targeted: known visit dates, hospital (x2), condition (x8 when <= 3 profiles share it), length of stay (any
  interval inside one record), after trying to recover a single global date shift from confident profiles.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

import regex as re

from ..normalize.dates import find_dates
from ..normalize.text import normalize
from ..normalize.translit import skeleton

# ---------------------------------------------------------------- registry


@dataclass
class Person:
    rid: str
    first: str          # skeleton keys
    last: str
    rel: frozenset
    gender: str         # M | F | ""
    age: Optional[int]
    house: str
    mohalla: str        # lowercased
    village: str
    tehsil: str
    district: str
    pin: str
    phone: str
    email: str
    last4: str


def _sk(tok: str) -> str:
    return skeleton(tok) if tok else ""


def _low(s: str) -> str:
    return " ".join(normalize(s or "").text.lower().split())


def _gender(v: str) -> str:
    v = _low(v)
    if v in ("m", "male", "पुरुष", "purush", "man", "boy"):
        return "M"
    if v in ("f", "female", "महिला", "mahila", "स्त्री", "woman", "girl"):
        return "F"
    return ""


class Registry:
    def __init__(self, people: list[Person]):
        self.people = people
        self.by_rid = {p.rid: p for p in people}
        self.first = {p.first for p in people if p.first}
        self.last = {p.last for p in people if p.last}
        self.rel = {t for p in people for t in p.rel}
        self.places: dict[str, dict[str, str]] = {"district": {}, "tehsil": {}, "village": {}, "mohalla": {}}
        for p in people:
            for kind in self.places:
                v = getattr(p, kind)
                if v:
                    self.places[kind][v] = v
                    key = " ".join(_sk(w) for w in v.split())
                    if key.strip():
                        self.places[kind]["sk:" + key] = v
        self.pins = {p.pin for p in people if p.pin}
        self.phones = {p.phone for p in people if p.phone}
        self.max_words = 3

    @classmethod
    def load(cls, path: Path) -> "Registry":
        people = []
        with open(path, encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                name = (r.get("name") or "").split()
                rel = frozenset(_sk(w) for w in (r.get("relative_name") or "").split() if w)
                age = r.get("age", "").strip()
                people.append(Person(
                    rid=r["rid"], first=_sk(name[0]) if name else "", last=_sk(name[-1]) if len(name) > 1 else "",
                    rel=rel, gender=_gender(r.get("gender", "")), age=int(age) if age.isdigit() else None,
                    house=(r.get("house_no") or "").strip(), mohalla=_low(r.get("mohalla", "")), village=_low(r.get("village", "")),
                    tehsil=_low(r.get("tehsil", "")), district=_low(r.get("district", "")), pin=(r.get("pin") or "").strip(),
                    phone=re.sub(r"\D", "", r.get("phone") or "")[-10:], email=_low(r.get("email", "")),
                    last4=(r.get("aadhaar_last4") or "").strip()))
        return cls(people)


# ---------------------------------------------------------------- evidence


@dataclass
class Evidence:
    ages: list = field(default_factory=list)          # (lo, hi)
    birth_years: set = field(default_factory=set)
    genders: set = field(default_factory=set)
    districts: set = field(default_factory=set)
    tehsils: set = field(default_factory=set)
    villages: set = field(default_factory=set)
    mohallas: set = field(default_factory=set)
    pins: set = field(default_factory=set)
    pin3s: set = field(default_factory=set)
    phones: set = field(default_factory=set)
    masked_phones: set = field(default_factory=set)   # (first2, last2)
    emails: set = field(default_factory=set)
    last4s: set = field(default_factory=set)
    houses: set = field(default_factory=set)
    names: set = field(default_factory=set)           # skeleton keys of name tokens
    rels: set = field(default_factory=set)
    dates: set = field(default_factory=set)           # dt.date
    intervals: set = field(default_factory=set)       # days between dates inside one record
    text: str = ""                                    # lowercased text (conditions, hospitals)
    psn: set = field(default_factory=set)
    refs: set = field(default_factory=set)


_AGE_LABEL = re.compile(r"\bage\b|\bumar\b|\bumr\b|\baayu\b|आयु|उम्र|\byrs?\b|\byears?\b", re.I)
_SEX_LABEL = re.compile(r"\bsex\b|gender|\bling\b|लिंग", re.I)
_DOB_LABEL = re.compile(r"\bdob\b|birth|janm|janam|जन्म", re.I)
_REL_LABEL = re.compile(r"father|husband|mother|guardian|relative|spouse|\bpita\b|\bpati\b|पिता|पति|अभिभावक|attendant|kin", re.I)
# patient reference columns ("patient_ref", "uhid", ...); NOT a bare "ref" ("ref range", "ref doctor" are shared by everyone)
_REF_LABEL = re.compile(r"patient.?ref|\buhid\b|\bmrn\b|patient.?id|\breg(?:istration)?.?(?:no|id)\b|\b(?:ip|op|ipd|opd|cr)\s?no\b", re.I)
_HOUSE_LABEL = re.compile(r"house|h\.?\s?no|makan|मकान", re.I)
_PLACE_LABEL = re.compile(r"district|distt|\bjila\b|\bzila\b|tehsil|tahsil|village|\bgaon\b|\bgram\b|mohall?a|locality|"
                          r"\bcity\b|\btown\b|address|\baddr\b|\bpata\b|\bline\b|residence|जिला|तहसील|ग्राम|गाँव|गांव|पता|मोहल्ला", re.I)
# in free text a place name counts only inside an address (a hospital letterhead naming its own town is not the patient's address)
_ADDR_CUE = re.compile(r"(?<![\p{L}])(?:address|addr|pata|r\s*/\s*o|resident\s+of|c\s*/\s*o|vill(?:age)?|gram|gaon|teh(?:sil)?|"
                       r"distt?|district|jila|zila|mohall?a|h\.?\s?no|makaa?n)(?![\p{L}])|पता|ग्राम|गाँव|गांव|तहसील|जिला|मोहल्ला|मकान|निवासी", re.I)
_PIN_LABEL = re.compile(r"\bpin\b|pincode|postal|\bzip\b|पिन", re.I)

_AGE_FORMS = [
    re.compile(r"(?<![\d.\-/])(\d{1,3})\s*-\s*(\d{1,3})\s*(?:yrs?|years?|y\b|वर्ष|saal|sal)?\s*/\s*[MFmf]\b"),
    re.compile(r"(?<![\d.\-/x])(\d{1,3})\s*-\s*(\d{1,3})\s*(?:yrs?|years?|वर्ष|saal|sal)\b", re.I),
    re.compile(r"\[(\d{1,3})\s*,\s*(\d{1,3})\)"),
]
_AGE_EXACT = [
    re.compile(r"(?<![\d.\-/x])(\d{1,3})\s*(?:yrs?|years?|y)?\s*/\s*(?:[MFmf]|male|female)\b", re.I),
    re.compile(r"(?<![\d.\-/])(?<!x\s)(?<!x)(\d{1,3})\s*(?:yrs?|years?|वर्ष|साल)\b(?!\s*(?:back|ago|se|से|pehle|history))", re.I),
    re.compile(r"\b(?:age|aged|umar|umr|aayu|आयु|उम्र)\s*[:\-=]?\s*(\d{1,3})(?![\d\-])", re.I),
]
_PLUS = re.compile(r"(?<![\d])(\d{2,3})\s*\+")
_DURATION_BEFORE = re.compile(r"(?:x|since|for|from|past|last|over|duration)\s*$", re.I)
_PHONE = re.compile(r"(?<!\d)(?:\+?91[\s\-]?|0)?([6-9]\d{4}[\s\-]?\d{5})(?!\d)")
_MASKED_PHONE = re.compile(r"(?<![\dXx*])([6-9]\d)[Xx*]{6}(\d{2})(?![\dXx*])")
_EMAIL = re.compile(r"[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+")
_LAST4 = re.compile(r"(?:[Xx*]{4}[\s\-]?){2}(\d{4})(?!\d)")
_PIN6 = re.compile(r"(?<!\d)([1-9]\d{5})(?!\d)")
_PIN3 = re.compile(r"(?<!\d)([1-9]\d{2})(?:\*{3}|[Xx]{3})(?![\dXx*])")
_HOUSE = re.compile(r"(?:h\.?\s?no|house\s*no|makaa?n\s*(?:no|number|nambar)|मकान\s*(?:नं|सं)\.?)\.?\s*[:\-#]?\s*(\d{1,4})", re.I)
_REL_CUE = re.compile(r"(?<![\p{L}])(?:s|d|w|c)\s*/\s*o\b\.?\s*[:\-]?\s*((?:[\p{L}\p{M}]+\s*){1,3})|"
                      r"(?:पिता|पति|पुत्र|पुत्री|पत्नी)\s*(?:का\s*नाम)?\s*[:\-]?\s*((?:[\p{L}\p{M}]+\s*){1,3})", re.I)
_DR = re.compile(r"(?:dr|doctor|डॉ)\.?\s+((?:[\p{L}\p{M}.]+\s*){1,3})", re.I)
_WORD = re.compile(r"[\p{L}\p{M}]+")
_MALE_CUE = re.compile(r"(?<![\p{L}])(?:s\s*/\s*o|mr|shri|sri|sahab|saheb|bhai|पुत्र|श्री)(?![\p{L}])", re.I)
_FEMALE_CUE = re.compile(r"(?<![\p{L}])(?:w\s*/\s*o|d\s*/\s*o|mrs|smt|kumari|behenji|bahenji|didi|पत्नी|पुत्री|श्रीमती)(?![\p{L}])", re.I)


def _ages_in(text: str, labelled: bool) -> list[tuple[int, int]]:
    out = []
    taken = []
    for rx in _AGE_FORMS:
        for m in rx.finditer(text):
            lo, hi = int(m.group(1)), int(m.group(2))
            if 0 <= lo <= hi <= 120 and hi - lo <= 60:
                out.append((lo, hi))
                taken.append((m.start(), m.end()))
    for m in _PLUS.finditer(text):
        if labelled or re.search(r"yrs?|years?|वर्ष|/[MF]", text[m.end():m.end() + 6], re.I):
            out.append((int(m.group(1)), 120))
            taken.append((m.start(), m.end()))
    for rx in _AGE_EXACT:
        for m in rx.finditer(text):
            if any(a <= m.start(1) < b for a, b in taken):
                continue
            if _DURATION_BEFORE.search(text[max(0, m.start() - 8):m.start()]):
                continue  # "x 9 yrs", "since 3 years": a duration, not an age
            a = int(m.group(1))
            if 0 <= a <= 120:
                out.append((a, a))
    if labelled and not out:
        s = text.strip()
        m = re.fullmatch(r"(\d{1,3})", s) or re.fullmatch(r"(\d{1,3})\s*-\s*(\d{1,3})", s)
        if m:
            lo = int(m.group(1))
            hi = int(m.group(2)) if m.lastindex == 2 else lo
            if 0 <= lo <= hi <= 120:
                out.append((lo, hi))
    return list(dict.fromkeys(out))  # two age forms can match the same mention


def _places(text: str, reg: Registry, ev: Evidence) -> None:
    words = text.split()
    for n in range(reg.max_words, 0, -1):
        for i in range(len(words) - n + 1):
            gram = " ".join(w.strip(".,;:()[]\"'") for w in words[i:i + n])
            if not gram:
                continue
            key = "sk:" + " ".join(_sk(w) for w in gram.split())
            for kind, vocab in reg.places.items():
                hit = vocab.get(gram) or (vocab.get(key) if len(key) > 5 else None)
                if hit:
                    getattr(ev, kind + "s").add(hit)


def _names(text: str, reg: Registry, ev: Evidence) -> None:
    skip = set()
    for m in _DR.finditer(text):
        for w in _WORD.finditer(m.group(1)):
            skip.add(m.start(1) + w.start())
    rel_pos = set()
    for m in _REL_CUE.finditer(text):
        g = 1 if m.group(1) else 2
        for w in _WORD.finditer(m.group(g)):
            k = _sk(w.group())
            if k and (k in reg.rel or k in reg.first or k in reg.last):
                ev.rels.add(k)
            rel_pos.add(m.start(g) + w.start())
    for w in _WORD.finditer(text):
        if w.start() in skip or w.start() in rel_pos or len(w.group()) < 3:
            continue
        k = _sk(w.group())
        if k and (k in reg.first or k in reg.last):
            ev.names.add(k)


def extract(pairs: Iterable[tuple[str, str]], reg: Registry, pseudonyms: frozenset = frozenset()) -> Evidence:
    """Evidence from one record: (label, value) pairs; free text has label ''."""
    ev = Evidence()
    texts = []
    for label, value in pairs:
        if value is None:
            continue
        v = normalize(str(value)).text
        if not v.strip():
            continue
        lab = (label or "").lower()
        texts.append(v)
        low = v.lower()
        # ages / birth / gender
        is_age = bool(lab and _AGE_LABEL.search(lab))
        ev.ages.extend(_ages_in(v, is_age))
        if lab and _SEX_LABEL.search(lab):
            g = _gender(v.split("/")[-1]) or _gender(v)
            if g:
                ev.genders.add(g)
        m = re.search(r"(?<=\d)\s*/\s*([MF])\b", v)
        if m:
            ev.genders.add(m.group(1))
        if _MALE_CUE.search(v):
            ev.genders.add("M")
        if _FEMALE_CUE.search(v):
            ev.genders.add("F")
        dates = [d for d in find_dates(v) if d.d]
        dob_field = bool(lab and _DOB_LABEL.search(lab))
        for d in dates:
            if dob_field or re.search(r"(?:dob|d\.o\.b|birth|जन्म\s*तिथि)\W{0,6}$", low[:d.start]):
                ev.birth_years.add(d.y)
        rec_dates = set()
        for d in dates:
            try:
                rec_dates.add(dt.date(d.y, d.m, d.d))
            except ValueError:
                pass
        ev.dates |= rec_dates
        # places, pins
        if lab and _PLACE_LABEL.search(lab):
            _places(low, reg, ev)
        else:
            for line in low.splitlines():
                m = _ADDR_CUE.search(line)
                if m:
                    _places(line[m.start():], reg, ev)
        for m in _PIN6.finditer(v):
            if m.group(1) in reg.pins:  # a 6-digit number the registry knows as a PIN
                ev.pins.add(m.group(1))
        for m in _PIN3.finditer(v):
            ev.pin3s.add(m.group(1))
        if lab and _PIN_LABEL.search(lab):
            m = re.fullmatch(r"\s*([1-9]\d{2})\d{0,3}\D*", v)
            if m and len(re.sub(r"\D", "", v)) == 3:
                ev.pin3s.add(m.group(1))
        # contacts
        for m in _PHONE.finditer(v):
            ev.phones.add(re.sub(r"\D", "", m.group(1)))
        for m in _MASKED_PHONE.finditer(v):
            ev.masked_phones.add((m.group(1), m.group(2)))
        for m in _EMAIL.finditer(v):
            ev.emails.add(m.group().lower())
        for m in _LAST4.finditer(v):
            ev.last4s.add(m.group(1))
        for m in _HOUSE.finditer(v):
            ev.houses.add(m.group(1))
        if lab and _HOUSE_LABEL.search(lab) and re.fullmatch(r"\s*\d{1,4}\s*", v):
            ev.houses.add(v.strip())
        # names
        if lab and _REL_LABEL.search(lab):
            for w in _WORD.finditer(v):
                k = _sk(w.group())
                if k and (k in reg.rel or k in reg.first or k in reg.last):
                    ev.rels.add(k)
        else:
            _names(v, reg, ev)
        # pseudonyms present in the release, shared reference values
        for p in pseudonyms:
            if p in v:
                ev.psn.add(p)
        if lab and _REF_LABEL.search(lab):
            s = v.strip()
            if len(s) >= 4 and sum(c.isdigit() for c in s) >= 3 and not re.search(r"\[[A-Z ]+\]", s):
                ev.refs.add(re.sub(r"[^0-9A-Za-z]", "", s).upper())  # the value alone: the same id sits under different labels
    ds = sorted(ev.dates)
    ev.intervals = {(b - a).days for i, a in enumerate(ds) for b in ds[i + 1:] if 0 < (b - a).days <= 365}
    ev.text = " \n ".join(t.lower() for t in texts)
    return ev


def pool(evs: list[Evidence]) -> Evidence:
    """Pooled evidence of a profile: age ranges intersected (contradictions fall back to the union), the rest united."""
    out = Evidence()
    rngs = [r for e in evs for r in e.ages]
    if rngs:
        lo, hi = max(r[0] for r in rngs), min(r[1] for r in rngs)
        out.ages = [(lo, hi)] if lo <= hi else rngs
    for f in ("birth_years", "genders", "districts", "tehsils", "villages", "mohallas", "pins", "pin3s", "phones",
              "masked_phones", "emails", "last4s", "houses", "names", "rels", "dates", "intervals", "psn", "refs"):
        s = set()
        for e in evs:
            s |= getattr(e, f)
        setattr(out, f, s)
    out.text = "\n".join(e.text for e in evs)
    return out


# ---------------------------------------------------------------- A2/A3 record linkage


def _filters(ev: Evidence, ref_year: int):
    yield "phone", lambda p: p.phone in ev.phones, bool(ev.phones)
    yield "email", lambda p: p.email in ev.emails, bool(ev.emails)
    yield "last4", lambda p: p.last4 in ev.last4s, bool(ev.last4s)
    yield "masked_phone", lambda p: any(p.phone[:2] == a and p.phone[-2:] == b for a, b in ev.masked_phones), bool(ev.masked_phones)
    yield "district", lambda p: p.district in ev.districts, bool(ev.districts)
    yield "gender", lambda p: p.gender in ev.genders, len(ev.genders) == 1
    yield "age", lambda p: p.age is not None and any(lo - 1 <= p.age <= hi + 2 for lo, hi in ev.ages), bool(ev.ages)
    yield "birth_year", lambda p: p.age is not None and any(abs((ref_year - p.age) - y) <= 1 for y in ev.birth_years), bool(ev.birth_years)
    yield "tehsil", lambda p: p.tehsil in ev.tehsils, bool(ev.tehsils)
    yield "village", lambda p: p.village in ev.villages, bool(ev.villages)
    yield "pin", lambda p: p.pin in ev.pins, bool(ev.pins)
    yield "pin3", lambda p: p.pin[:3] in ev.pin3s, bool(ev.pin3s)


def link(ev: Evidence, reg: Registry, ref_year: int) -> tuple[dict[str, float], list[str]]:
    """Probability per registry person, and the evidence kinds that narrowed or weighted the candidates."""
    cands = reg.people
    used = []
    for name, ok, active in _filters(ev, ref_year):
        if not active:
            continue
        nxt = [p for p in cands if ok(p)]
        if nxt and len(nxt) < len(cands):
            used.append(name)
        if nxt:
            cands = nxt
    weights = {}
    for p in cands:
        w = 1.0
        first, last = p.first in ev.names, bool(p.last) and p.last in ev.names
        if first and last:
            w *= 60
        else:
            if first:
                w *= 8
            if last:
                w *= 3
        if p.rel & ev.rels:
            w *= 8
        if p.house and p.house in ev.houses:
            w *= 2
        weights[p.rid] = w
    tot = sum(weights.values())
    probs = {r: w / tot for r, w in weights.items()} if tot else {}
    if probs:
        best = max(weights.values())
        if best > 1:
            used.append("names/relative/house")
    return probs, used


# ---------------------------------------------------------------- A4 profiles


def profiles(evs: list[Evidence]) -> list[list[int]]:
    """Join records through pseudonyms present in the data and shared reference values (union-find)."""
    parent = list(range(len(evs)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    first_of: dict[str, int] = {}
    for i, e in enumerate(evs):
        for key in [("psn", p) for p in e.psn] + [("ref", r) for r in e.refs]:
            if key in first_of:
                parent[find(i)] = find(first_of[key])
            else:
                first_of[key] = i
    groups = defaultdict(list)
    for i in range(len(evs)):
        groups[find(i)].append(i)
    return list(groups.values())


# ---------------------------------------------------------------- A5 targeted


@dataclass
class Fact:
    rid: str
    visit_dates: list
    hospital: str
    condition: str
    stay_days: Optional[int]


def load_facts(path: Path) -> list[Fact]:
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        vd = d.get("visit_dates") or []
        if isinstance(vd, str):
            vd = [vd]
        dates = []
        for s in vd:
            try:
                dates.append(dt.date.fromisoformat(s[:10]))
            except ValueError:
                pass
        sd = d.get("stay_days")
        out.append(Fact(d["rid"], dates, _low(d.get("hospital", "")), _low(d.get("condition_hint", "")),
                        int(sd) if isinstance(sd, (int, float)) or (isinstance(sd, str) and sd.isdigit()) else None))
    return out


def recover_global_shift(prof_evs: list[Evidence], prof_top: list[tuple[str, float]], facts: list[Fact]) -> Optional[int]:
    """From profiles identified with confidence >= 0.9, find a date offset shared by at least two people."""
    by_rid = {f.rid: f for f in facts}
    votes: dict[int, set] = defaultdict(set)
    for ev, (rid, p) in zip(prof_evs, prof_top):
        f = by_rid.get(rid)
        if p < 0.9 or not f:
            continue
        for d in ev.dates:
            for v in f.visit_dates:
                votes[(d - v).days].add(rid)
    agreed = [(len(r), off) for off, r in votes.items() if len(r) >= 2]
    return max(agreed)[1] if agreed else None


def targeted(facts: list[Fact], prof_evs: list[Evidence], reg: Registry, ref_year: int,
             shift: Optional[int]) -> dict[str, dict[int, float]]:
    """For each known-facts person: {profile index: probability} over the profiles the attacker would point at."""
    off = dt.timedelta(days=shift or 0)
    cond_count = Counter()
    for f in facts:
        if f.condition:
            cond_count[f.condition] = sum(1 for e in prof_evs if f.condition in e.text)
    out = {}
    for f in facts:
        person = reg.by_rid.get(f.rid)
        weights = {}
        for i, e in enumerate(prof_evs):
            w = 0.0
            dates = {d - off for d in e.dates}
            if any(v in dates for v in f.visit_dates):
                w += 1
            if f.condition and f.condition in e.text:
                w += 8 if cond_count[f.condition] <= 3 else 1
            if f.stay_days is not None and f.stay_days in e.intervals:
                w += 1
            if w == 0:
                continue
            if f.hospital and f.hospital in e.text:
                w *= 2
            if person is not None:
                probs, _ = link(e, reg, ref_year)
                if person.rid not in probs:
                    continue  # the profile's evidence contradicts this person
            weights[i] = w
        tot = sum(weights.values())
        out[f.rid] = {i: w / tot for i, w in weights.items()} if tot else {}
    return out
