"""Fictional patients, encounters and the many ways one patient gets written down."""
from __future__ import annotations

import datetime as dt
import random
from dataclasses import dataclass, field

from . import pools as P

HOSPITALS = ["hosp_a", "hosp_b", "hosp_c", "hosp_d", "hosp_e"]


@dataclass
class Person:
    pid: str
    sex: str  # M | F
    first: tuple[str, str]
    last: tuple[str, str]
    birth: dt.date
    father: tuple[str, str]  # (latin full, deva full)
    husband: tuple[str, str] | None
    phone: str
    phone2: str
    email: str | None
    abha: str
    insurance: str | None
    city: tuple[str, str]
    area: tuple[tuple[str, str], tuple[str, str]]  # (word, suffix)
    house: str
    landmark: tuple[str, str]
    pin: str
    mrn: dict[str, str] = field(default_factory=dict)
    hospitals: list[str] = field(default_factory=list)
    twin_of: str | None = None


@dataclass
class Encounter:
    person: Person
    hospital: str
    admit: dt.date
    los: int
    dx: tuple[str, str, str]
    rare: bool
    labs: list[tuple[str, str, str]]  # (name, value, unit)
    vitals: dict[str, str]
    meds: list[tuple[str, str, str, int]]  # (prefix, drug, freq, days)
    procedure: str | None
    doctor: tuple[str, str]  # (latin, deva) full name incl initials
    ward: str


def pools_for(split: str) -> dict:
    if split == "blind":
        from . import blind as B

        return {"fm": B.FIRST_M, "ff": B.FIRST_F, "ln": B.LAST, "city": B.CITIES, "area": B.AREAS, "fx": []}
    held = split == "heldout"
    return {
        "fm": P.FIRST_M_HELD if held else P.FIRST_M_SEEN,
        "ff": P.FIRST_F_HELD if held else P.FIRST_F_SEEN,
        "ln": P.LAST_HELD if held else P.LAST_SEEN,
        "city": P.CITIES_HELD if held else P.CITIES_SEEN,
        "area": P.AREA_WORDS_HELD if held else P.AREA_WORDS_SEEN,
        "fx": P.FATHER_EXTRA_HELD if held else P.FATHER_EXTRA_SEEN,
    }


def _digits(rng: random.Random, n: int) -> str:
    return "".join(str(rng.randrange(10)) for _ in range(n))


def _phone(rng: random.Random) -> str:
    return str(rng.choice([6, 7, 8, 9, 9, 9])) + _digits(rng, 9)


def _mrn(rng: random.Random, hosp: str) -> str:
    if hosp == "hosp_a":
        return "UHID" + _digits(rng, 8)
    if hosp == "hosp_b":
        return f"MRN/{rng.randrange(2014, 2025)}/{_digits(rng, 5)}"
    if hosp == "hosp_c":
        return "REG-" + _digits(rng, 6)
    if hosp == "hosp_d":
        return f"H{rng.randrange(1, 9)}-{rng.randrange(14, 25)}-{_digits(rng, 5)}"
    return "PT" + _digits(rng, 7)


def _insurance(rng: random.Random) -> str:
    k = rng.randrange(4)
    if k == 0:
        return f"POL/{rng.randrange(2016, 2025)}/{_digits(rng, 6)}"
    if k == 1:
        return rng.choice(["HDFC", "STAR", "NIVA", "ICICI"]) + _digits(rng, 9)
    if k == 2:
        return "PMJAY-" + _digits(rng, 10)
    return f"CGHS/{_digits(rng, 7)}"


def make_people(rng: random.Random, n: int, split: str) -> list[Person]:
    pl = pools_for(split)
    people: list[Person] = []

    def base(i: int) -> Person:
        sex = rng.choice("MF")
        first = rng.choice(pl["fm"] if sex == "M" else pl["ff"])
        last = rng.choice(pl["ln"])
        age = rng.choice([rng.randrange(1, 15), rng.randrange(18, 60), rng.randrange(18, 60), rng.randrange(55, 92)])
        birth = dt.date(2025 - age, rng.randrange(1, 13), rng.randrange(1, 28))
        ffirst = rng.choice(pl["fm"] + pl["fx"])
        if " " in ffirst[0]:
            father = ffirst
        else:
            father = (f"{ffirst[0]} {last[0]}", f"{ffirst[1]} {last[1]}")
        husband = None
        if sex == "F" and age >= 22 and rng.random() < 0.6:
            hf = rng.choice(pl["fm"])
            hl = rng.choice(pl["ln"])
            husband = (f"{hf[0]} {hl[0]}", f"{hf[1]} {hl[1]}")
        email = None
        if rng.random() < 0.3:
            dom = rng.choice(["gmail.com", "yahoo.co.in", "rediffmail.com", "outlook.com"])
            style = rng.randrange(3)
            fl, ll = first[0].lower(), last[0].lower()
            email = (f"{fl}.{ll}@{dom}" if style == 0 else f"{fl}{ll}{rng.randrange(10, 99)}@{dom}"
                     if style == 1 else f"{fl[0]}{ll}{rng.randrange(1970, 2005)}@{dom}")
        w, s = rng.choice(pl["area"]), rng.choice(P.AREA_SUFFIX)
        hs = rng.randrange(3)
        house = (f"H.No. {rng.randrange(1, 400)}" if hs == 0 else
                 f"Flat {rng.randrange(1, 9)}0{rng.randrange(1, 9)}" if hs == 1 else f"{rng.randrange(1, 300)}/{rng.choice('ABCD')}")
        n_h = rng.choice([1, 1, 2, 2, 3])
        hosp = rng.sample(HOSPITALS, n_h)
        p = Person(
            pid=f"P{i:05d}", sex=sex, first=first, last=last, birth=birth, father=father, husband=husband,
            phone=_phone(rng), phone2=_phone(rng), email=email, abha=_digits(rng, 14),
            insurance=_insurance(rng) if rng.random() < 0.35 else None,
            city=rng.choice(pl["city"]), area=(w, s), house=house, landmark=rng.choice(P.LANDMARKS),
            pin=str(rng.randrange(1, 9)) + _digits(rng, 5), hospitals=sorted(hosp),
        )
        for h in p.hospitals:
            p.mrn[h] = _mrn(rng, h)
        return p

    i = 0
    while len(people) < n:
        p = base(i)
        i += 1
        people.append(p)
        # same-name different person (a trap for name-only linkage)
        if rng.random() < 0.12 and len(people) < n:
            q = base(i)
            i += 1
            q.sex, q.first, q.last = p.sex, p.first, p.last
            q.father = p.father if rng.random() < 0.15 else q.father  # a few share the father's name too
            if rng.random() < 0.5:
                q.city, q.pin, q.area = p.city, p.pin, p.area
            if rng.random() < 0.5:
                q.birth = dt.date(p.birth.year + rng.choice([-1, 1, -2, 2, 0, 25, -25]), q.birth.month, q.birth.day)
            q.twin_of = p.pid
            people.append(q)
    return people[:n]


def make_encounters(rng: random.Random, people: list[Person], split: str = "dev") -> list[Encounter]:
    pl = pools_for(split)
    encs: list[Encounter] = []
    for p in people:
        for _ in range(rng.choice([1, 2, 2, 3, 4])):
            h = rng.choice(p.hospitals)
            admit = dt.date(rng.randrange(2016, 2026), rng.randrange(1, 13), rng.randrange(1, 28))
            if admit.year - p.birth.year < 0:
                admit = dt.date(p.birth.year + 1, admit.month, admit.day)
            rare = rng.random() < 0.04
            dx = rng.choice(P.RARE_DIAGNOSES if rare else P.DIAGNOSES)
            labs = []
            for name, lo, hi, dec, unit in rng.sample(P.LABS, rng.randrange(2, 5)):
                v = rng.uniform(lo, hi)
                labs.append((name, f"{v:.{dec}f}" if dec else str(int(v)), unit))
            vitals = {
                "BP": f"{rng.randrange(90, 180)}/{rng.randrange(55, 110)}",
                "HR": str(rng.randrange(52, 128)),
                "Temp": f"{rng.uniform(97, 104):.1f}",
                "SpO2": str(rng.randrange(88, 100)),
            }
            meds = []
            for prefix_drug in rng.sample(P.DRUGS, rng.randrange(2, 5)):
                meds.append((prefix_drug[1], prefix_drug[0], rng.choice(P.FREQS), rng.choice([3, 5, 5, 7, 10, 14])))
            docf = rng.choice(pl["fm"] + pl["ff"])
            docl = rng.choice(pl["ln"])
            ini = rng.choice(P.DOCTOR_FIRST_INITIALS)
            doctor = (f"{ini}. {docl[0]}", f"{docl[1]}") if rng.random() < 0.5 else (f"{docf[0]} {docl[0]}", f"{docf[1]} {docl[1]}")
            encs.append(Encounter(
                person=p, hospital=h, admit=admit, los=rng.randrange(1, 21), dx=dx, rare=rare, labs=labs,
                vitals=vitals, meds=meds, procedure=rng.choice(P.PROCEDURES) if rng.random() < 0.15 else None,
                doctor=doctor, ward=f"Ward {rng.randrange(1, 15)}",
            ))
    return encs


# --------------------------------------------------------------- formatting helpers
def fmt_phone(num: str, rng: random.Random, deva: bool = False) -> str:
    k = rng.randrange(9)
    a, b = num[:5], num[5:]
    s = {
        0: num, 1: f"+91 {a} {b}", 2: f"+91-{num}", 3: f"0{a}-{b}", 4: f"{a} {b}", 5: f"(+91) {num}",
        6: f"91{num}", 7: f"{num[:4]} {num[4:7]} {num[7:]}", 8: f"+91 {num[:3]}-{num[3:6]}-{num[6:]}",
    }[k]
    return to_deva_digits(s) if deva else s


def to_deva_digits(s: str) -> str:
    return "".join(chr(0x0966 + int(c)) if c.isdigit() else c for c in s)


def fmt_abha(num: str, rng: random.Random) -> str:
    k = rng.randrange(3)
    if k == 0:
        return f"{num[:2]}-{num[2:6]}-{num[6:10]}-{num[10:]}"
    if k == 1:
        return num
    return f"{num[:4]} {num[4:8]} {num[8:12]} {num[12:]}"


def ordinal_day(d: int) -> str:
    suf = "th" if 10 <= d % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(d % 10, "th")
    return f"{d}{suf}"


def fmt_date(d: dt.date, rng: random.Random, style: int | None = None) -> str:
    k = rng.randrange(9) if style is None else style
    mon3 = P.EN_MONTHS[d.month - 1][:3]
    if k == 0:
        return f"{d.day:02d}/{d.month:02d}/{d.year}"
    if k == 1:
        return f"{d.day:02d}-{d.month:02d}-{d.year}"
    if k == 2:
        return f"{d.day:02d}.{d.month:02d}.{d.year % 100:02d}"
    if k == 3:
        return d.isoformat()
    if k == 4:
        return f"{d.day} {mon3} {d.year}"
    if k == 5:
        return f"{ordinal_day(d.day)} {P.EN_MONTHS[d.month - 1]}, {d.year}"
    if k == 6:
        return f"{P.EN_MONTHS[d.month - 1]} {d.day}, {d.year}"
    if k == 7:
        return f"{d.day} {P.HI_MONTHS[d.month - 1]} {d.year}"
    return to_deva_digits(f"{d.day:02d}/{d.month:02d}/{d.year}")


def _mohd(first: str, rng: random.Random) -> str:
    if first == "Mohammad":
        return rng.choice(["Mohammad", "Mohd", "Md", "Muhammad", "Mohammed", "Mohd."])
    return first


def name_text(p: Person, rng: random.Random, script: str = "latin", honorific: bool = True) -> str:
    """One written form of the patient's own name."""
    F, L = _mohd(p.first[0], rng), p.last[0]
    if script == "deva":
        dF, dL = p.first[1], p.last[1]
        return rng.choice([f"{dF} {dL}"] * 5 + [f"{dL} {dF}"])
    k = rng.random()
    if k < 0.34:
        s = f"{F} {L}"
    elif k < 0.44:
        s = f"{L} {F}"
    elif k < 0.54:
        s = f"{F} {L[0]}."
    elif k < 0.64:
        s = f"{F[0]}. {L}"
    elif k < 0.72:
        s = f"{F} {L}".upper()
    elif k < 0.78:
        s = f"{L}, {F}"
    elif k < 0.86:
        s = f"{F} {L}".lower()
    else:
        s = f"{F} {L}"
    if honorific and rng.random() < 0.2:
        if p.sex == "M":
            s = rng.choice(["Mr. ", "Shri ", "Sh. "]) + s
        else:
            s = rng.choice(["Mrs. ", "Smt. ", "Ms. "]) + s
    return s


def relative(p: Person, rng: random.Random, script: str = "latin") -> tuple[str, str, str] | None:
    """(cue, relative-name, relation) e.g. ('s/o', 'Shyam Lal', 'father')."""
    age = 2025 - p.birth.year
    i = 0 if script == "latin" else 1
    if p.sex == "F" and p.husband and rng.random() < 0.7:
        cue = rng.choice(["w/o", "W/o", "wife of"]) if script == "latin" else rng.choice(["पत्नी", "पत्नी श्री"])
        return cue, p.husband[i], "husband"
    if age < 40 or rng.random() < 0.5:
        if p.sex == "M":
            cue = rng.choice(["s/o", "S/o", "S/O", "son of"]) if script == "latin" else rng.choice(["पुत्र", "सुपुत्र"])
        else:
            cue = rng.choice(["d/o", "D/o", "daughter of"]) if script == "latin" else rng.choice(["पुत्री", "सुपुत्री"])
        return cue, p.father[i], "father"
    return None
