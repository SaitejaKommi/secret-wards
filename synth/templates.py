"""Record templates. SEEN_* are what we look at while building detectors;
HELD_* are never inspected for tuning and are used for the held-out split.
Every PII / medical value goes through Cell.P / Cell.M so gold spans are exact.
"""
from __future__ import annotations

import datetime as dt
import random

from . import pools as P
from .cell import Cell
from .people import Encounter, Person, fmt_abha, fmt_date, fmt_phone, name_text, relative, to_deva_digits


# ------------------------------------------------------------------ small builders
def hon(p: Person, rng: random.Random, c: Cell, prob: float = 0.2) -> None:
    if rng.random() < prob:
        c.lit(rng.choice(["Mr. ", "Shri ", "Sh. "]) if p.sex == "M" else rng.choice(["Mrs. ", "Smt. ", "Ms. "]))


def name_c(c: Cell, p: Person, rng: random.Random, lang: str, rel: bool = False, honorific: bool = True) -> Cell:
    if lang == "hi":
        c.P("NAME", name_text(p, rng, "deva"), "patient")
    else:
        if honorific:
            hon(p, rng, c)
        t = name_text(p, rng, "latin", honorific=False)
        if lang == "hinglish" and rng.random() < 0.4:
            t = t.lower()
        c.P("NAME", t, "patient")
    if rel:
        r = relative(p, rng, "deva" if lang == "hi" else "latin")
        if r:
            c.lit(f" {r[0]} ").P("NAME", r[1], "relative")
    return c


def rel_c(c: Cell, p: Person, rng: random.Random, lang: str) -> Cell:
    r = relative(p, rng, "deva" if lang == "hi" else "latin")
    if r:
        c.P("NAME", r[1], "relative")
    else:
        c.P("NAME", p.father[1 if lang == "hi" else 0], "relative")
    return c


def doctor_c(c: Cell, enc: Encounter, lang: str) -> Cell:
    c.lit("डॉ. " if lang == "hi" else "Dr. ").P("NAME", enc.doctor[1] if lang == "hi" else enc.doctor[0], "doctor")
    return c


def phone_c(c: Cell, num: str, rng: random.Random, lang: str = "en") -> Cell:
    c.P("PHONE", fmt_phone(num, rng, deva=(lang == "hi" and rng.random() < 0.4)))
    return c


def date_c(c: Cell, d: dt.date, rng: random.Random, lang: str = "en", style: int | None = None) -> Cell:
    if lang == "hi" and style is None:
        style = rng.choice([0, 7, 8])
    c.P("DATE", fmt_date(d, rng, style))
    return c


def addr_c(c: Cell, p: Person, rng: random.Random, lang: str, with_pin: str = "inline") -> Cell:
    """with_pin: 'inline' (", 226001"), 'none', or 'label' ("PIN: 226001")."""
    i = 1 if lang == "hi" else 0
    area = f"{p.area[0][i]} {p.area[1][i]}"
    lm = p.landmark[i]
    parts = []
    if rng.random() < 0.8:
        parts.append(p.house)
    parts.append(area)
    if rng.random() < 0.7:
        if lang == "hi":
            parts.append(f"{lm} {rng.choice(['के पास', 'के सामने', 'के पीछे'])}")
        elif lang == "hinglish":
            parts.append(f"{lm} {rng.choice(['ke paas', 'ke samne', 'ke peeche'])}")
        else:
            parts.append(f"{rng.choice(['near', 'behind', 'opp.', 'opposite', 'beside', 'next to'])} {lm}")
    parts.append(p.city[i])
    c.P("ADDRESS", ", ".join(parts))
    if with_pin == "inline":
        c.lit(rng.choice([", ", " - ", " "])).P("PINCODE", p.pin)
    elif with_pin == "label":
        c.lit(rng.choice([", PIN: ", " Pin ", ", Pincode "])).P("PINCODE", p.pin)
    return c


def age_c(c: Cell, p: Person, enc: Encounter, rng: random.Random, lang: str = "en", bare: bool = False) -> Cell:
    a = enc.admit.year - p.birth.year
    c.native = a
    if bare:
        return c.M("AGE", str(a))
    if lang == "hi":
        return c.M("AGE", f"{a} वर्ष")
    if lang == "hinglish":
        return c.M("AGE", rng.choice([f"{a} saal", f"{a} yrs", f"{a}y"]))
    return c.M("AGE", rng.choice([f"{a} years", f"{a} yrs", f"{a}Y", f"{a} year old"]))


def sex_word(p: Person, lang: str, short: bool = False) -> str:
    if short:
        return p.sex
    if lang == "hi":
        return "पुरुष" if p.sex == "M" else "महिला"
    return "Male" if p.sex == "M" else "Female"


def dx_text(enc: Encounter, lang: str) -> str:
    return enc.dx[{"en": 0, "hinglish": 1, "hi": 2}[lang]]


def meds_c(c: Cell, enc: Encounter, rng: random.Random, sep: str = "; ", lang: str = "en") -> Cell:
    for i, (prefix, drug, freq, days) in enumerate(enc.meds):
        if i:
            c.lit(sep)
        c.lit(prefix + " ").M("DRUG", drug).lit(" ").M("FREQ", freq).lit(" x ")
        c.M("DURATION", f"{days} days" if lang != "hi" else f"{days} दिन")
    return c


def vitals_c(c: Cell, enc: Encounter, rng: random.Random) -> Cell:
    v = enc.vitals
    c.M("VITAL", f"BP {v['BP']} mmHg").lit(rng.choice([", ", "; ", " | "]))
    c.M("VITAL", f"HR {v['HR']}/min").lit(rng.choice([", ", "; ", " | "]))
    c.M("VITAL", f"Temp {v['Temp']} F").lit(", ")
    c.M("VITAL", f"SpO2 {v['SpO2']}%")
    return c


def labs_c(c: Cell, enc: Encounter, rng: random.Random, sep: str = ", ") -> Cell:
    for i, (n, v, u) in enumerate(enc.labs):
        if i:
            c.lit(sep)
        c.M("LAB", f"{n} {v} {u}")
    return c


def los_c(c: Cell, enc: Encounter, lang: str = "en", bare: bool = False) -> Cell:
    c.native = enc.los
    if bare:
        return c.M("LOS", str(enc.los))
    return c.M("LOS", f"{enc.los} दिन" if lang == "hi" else f"{enc.los} days")


def proc_c(c: Cell, enc: Encounter) -> Cell:
    if enc.procedure:
        c.M("PROCEDURE", enc.procedure)
    return c


def mrn_c(c: Cell, p: Person, enc: Encounter) -> Cell:
    c.P("MRN", p.mrn[enc.hospital])
    return c


def abha_c(c: Cell, p: Person, rng: random.Random) -> Cell:
    c.P("ABHA", fmt_abha(p.abha, rng))
    return c


def disch(enc: Encounter) -> dt.date:
    return enc.admit + dt.timedelta(days=enc.los)


TRAPS = [
    "Dispensed from Dr. Reddy's pharmacy counter.",
    "Glucometer strips (Dr. Morepen) advised.",
    "Continue Tab. Dolo 650 BD x 5 days if fever persists.",
    "Inj. Pan 40 mg IV OD given.",
]


def trap_c(c: Cell, rng: random.Random) -> Cell:
    c.lit(rng.choice(TRAPS))
    return c


# ---------------------------------------------------------------- SEEN free-text templates
def seen_discharge_en(p: Person, enc: Encounter, rng: random.Random, noise: float) -> Cell:
    c = Cell(rng, noise)
    c.lit("DISCHARGE SUMMARY\n").lit("Patient Name: ")
    name_c(c, p, rng, "en", rel=rng.random() < 0.5)
    c.lit("\nAge/Sex: ")
    age_c(c, p, enc, rng)
    c.lit(f" / {sex_word(p, 'en')}      UHID: ")
    mrn_c(c, p, enc)
    c.lit("\nAddress: ")
    addr_c(c, p, rng, "en", rng.choice(["inline", "label"]))
    c.lit("\nPhone: ")
    phone_c(c, p.phone, rng)
    if rng.random() < 0.5:
        c.lit("  Alt: ")
        phone_c(c, p.phone2, rng)
    if rng.random() < 0.6:
        c.lit("\nABHA No: ")
        abha_c(c, p, rng)
    if p.insurance and rng.random() < 0.7:
        c.lit("\nInsurance Policy No: ").P("INSURANCE", p.insurance)
    if p.email and rng.random() < 0.7:
        c.lit("\nEmail: ").P("EMAIL", p.email)
    c.lit("\nDate of Admission: ")
    date_c(c, enc.admit, rng)
    c.lit("   Date of Discharge: ")
    date_c(c, disch(enc), rng)
    c.lit("\nLength of stay: ")
    los_c(c, enc)
    c.lit("\nDiagnosis: ").M("DIAGNOSIS", dx_text(enc, "en"))
    if enc.procedure:
        c.lit("\nProcedure: ")
        proc_c(c, enc)
    c.lit("\nVitals on admission: ")
    vitals_c(c, enc, rng)
    c.lit("\nInvestigations: ")
    labs_c(c, enc, rng)
    c.lit("\nTreatment: ")
    meds_c(c, enc, rng)
    c.lit("\nAdvice: Follow up with ")
    doctor_c(c, enc, "en")
    c.lit(" after 7 days. ")
    if rng.random() < 0.5:
        trap_c(c, rng)
    c.lit("\nIn case of emergency contact ")
    rel_c(c, p, rng, "en")
    c.lit(" on ")
    phone_c(c, p.phone2, rng)
    c.lit(".\n")
    return c


def seen_rx_hinglish(p: Person, enc: Encounter, rng: random.Random, noise: float) -> Cell:
    c = Cell(rng, noise)
    c.lit("Rx\nMareez ka naam: ")
    name_c(c, p, rng, "hinglish", rel=rng.random() < 0.4)
    c.lit("\nUmar: ")
    age_c(c, p, enc, rng, "hinglish")
    c.lit(f", {sex_word(p, 'en', True)}\nPata: ")
    addr_c(c, p, rng, "hinglish", "inline")
    c.lit("\nMobile: ")
    phone_c(c, p.phone, rng)
    c.lit("\nDate: ")
    date_c(c, enc.admit, rng)
    c.lit("\nBimari: ").M("DIAGNOSIS", dx_text(enc, "hinglish"))
    c.lit("\nDawai:\n")
    for i, (prefix, drug, freq, days) in enumerate(enc.meds):
        c.lit(f" {i + 1}. {prefix} ").M("DRUG", drug).lit(" ").M("FREQ", freq).lit(" x ").M("DURATION", f"{days} days").lit("\n")
    fn = p.first[0].lower()
    if rng.random() < 0.7:
        who = rng.choice(["bhaiya", "ji", "sahab"]) if p.sex == "M" else rng.choice(["didi", "ji", "behen"])
        c.lit("Note: ").P("NAME", fn, "patient").lit(f" {who} ko ")
        c.M("VITAL", f"BP {enc.vitals['BP']} mmHg").lit(" tha, ").M("LAB", f"{enc.labs[0][0]} {enc.labs[0][1]} {enc.labs[0][2]}")
        c.lit(" aaya. Pita ka naam ").P("NAME", p.father[0], "relative").lit(" ne bataya.\n")
    doctor_c(c, enc, "en")
    c.lit("\n")
    return c


def seen_whatsapp(p: Person, enc: Encounter, rng: random.Random, noise: float) -> Cell:
    c = Cell(rng, noise)
    d = enc.admit
    ds = f"{d.day:02d}/{d.month:02d}/{d.year % 100:02d}"
    c.lit("[").P("DATE", ds).lit(", 10:42 am] ").P("NAME", p.father[0], "relative").lit(": ")
    c.lit("Sir report bhej raha hu. Patient ")
    name_c(c, p, rng, "hinglish", honorific=False)
    c.lit(" (")
    age_c(c, p, enc, rng, "hinglish")
    c.lit(f"/{p.sex})\n")
    c.lit("[").P("DATE", ds).lit(", 10:44 am] Lab: ")
    labs_c(c, enc, rng, " | ")
    c.lit("\n")
    c.lit("[").P("DATE", ds).lit(", 10:51 am] ").P("NAME", p.father[0], "relative").lit(": ")
    c.lit("Aap call kar lo ")
    phone_c(c, p.phone, rng)
    c.lit(" ya ")
    if p.email:
        c.P("EMAIL", p.email)
    else:
        c.lit("WhatsApp pe bata do")
    c.lit(". Hum ")
    addr_c(c, p, rng, "hinglish", "none")
    c.lit(" mein rehte hain.\n")
    c.lit("Dx: ").M("DIAGNOSIS", dx_text(enc, "hinglish")).lit(", ").M("DRUG", enc.meds[0][1]).lit(" ").M("FREQ", enc.meds[0][2]).lit("\n")
    return c


def seen_hindi_note(p: Person, enc: Encounter, rng: random.Random, noise: float) -> Cell:
    c = Cell(rng, noise)
    c.lit("मरीज़ का नाम: ")
    name_c(c, p, rng, "hi", rel=rng.random() < 0.5)
    c.lit("\nआयु: ")
    age_c(c, p, enc, rng, "hi")
    c.lit(f"   लिंग: {sex_word(p, 'hi')}\nपता: ")
    addr_c(c, p, rng, "hi", "label")
    c.lit("\nमोबाइल: ")
    phone_c(c, p.phone, rng, "hi")
    c.lit("\nभर्ती की तारीख: ")
    date_c(c, enc.admit, rng, "hi")
    c.lit("\nनिदान: ").M("DIAGNOSIS", dx_text(enc, "hi"))
    c.lit("\nदवाइयाँ: ")
    meds_c(c, enc, rng, ", ", "hi")
    c.lit("\nजाँच: ")
    labs_c(c, enc, rng)
    c.lit("\nबेटे ").P("NAME", p.first[1], "patient").lit(" के पिता ").P("NAME", p.father[1], "relative").lit(" ने बताया।\n")
    return c


# ---------------------------------------------------------------- HELD-OUT free-text templates
def held_referral_en(p: Person, enc: Encounter, rng: random.Random, noise: float) -> Cell:
    c = Cell(rng, noise)
    c.lit("To,\nThe Medical Superintendent\n\nRe: Referral of ")
    name_c(c, p, rng, "en")
    c.lit(", ")
    age_c(c, p, enc, rng, "en")
    c.lit(f" {sex_word(p, 'en').lower()}, resident of ")
    addr_c(c, p, rng, "en", "label")
    c.lit(".\n\nDear Sir/Madam,\nThis is to refer ")
    c.P("NAME", p.first[0], "patient")
    c.lit(" who was admitted on ")
    date_c(c, enc.admit, rng)
    c.lit(" with ").M("DIAGNOSIS", dx_text(enc, "en")).lit(". On examination ")
    vitals_c(c, enc, rng)
    c.lit(". ")
    labs_c(c, enc, rng)
    c.lit(". Started on ")
    meds_c(c, enc, rng, " and ")
    c.lit(". Kindly contact the family on ")
    phone_c(c, p.phone, rng)
    if p.email:
        c.lit(" or write to ").P("EMAIL", p.email)
    c.lit(".\n\nYours sincerely,\n")
    doctor_c(c, enc, "en")
    c.lit(f"\n{enc.ward}\n")
    return c


def held_nursing_handover(p: Person, enc: Encounter, rng: random.Random, noise: float) -> Cell:
    c = Cell(rng, noise)
    c.lit(f"Bed {rng.randrange(1, 40)} pt ")
    c.P("NAME", f"{p.first[0]} {p.last[0]}".lower() if rng.random() < 0.5 else f"{p.first[0]} {p.last[0]}", "patient")
    c.lit(" ")
    age_c(c, p, enc, rng, "hinglish")
    c.lit(f"/{p.sex} - ").M("DIAGNOSIS", dx_text(enc, "hinglish"))
    c.lit(". Attendant ")
    c.P("NAME", p.father[0].split()[0].lower(), "relative")
    c.lit(" bhai ")
    phone_c(c, p.phone2, rng)
    c.lit(". Vitals ")
    vitals_c(c, enc, rng)
    c.lit(". Continue ")
    prefix, drug, freq, days = enc.meds[0]
    c.lit(prefix + " ").M("DRUG", drug).lit(" ").M("FREQ", freq).lit(". D/c planned ")
    date_c(c, disch(enc), rng)
    c.lit(". Ghar: ")
    addr_c(c, p, rng, "hinglish", "none")
    c.lit(".\n")
    return c


def held_lab_report(p: Person, enc: Encounter, rng: random.Random, noise: float) -> Cell:
    c = Cell(rng, noise)
    c.lit("PATHOLOGY LAB REPORT\nSample ID: ").P("ID", "LB" + str(rng.randrange(100000, 999999)))
    c.lit("\nPatient: ")
    name_c(c, p, rng, "en")
    c.lit("   DOB: ")
    date_c(c, p.birth, rng)
    c.lit("   Sex: " + p.sex + "\nCollected on: ")
    date_c(c, enc.admit, rng)
    c.lit("   Referred by: ")
    doctor_c(c, enc, "en")
    c.lit("\nPatient ID: ")
    mrn_c(c, p, enc)
    c.lit("\n\n")
    for n, v, u in enc.labs:
        c.lit("  ").M("LAB", f"{n} {v} {u}").lit("\n")
    c.lit("\nReport sent to ")
    if p.email:
        c.P("EMAIL", p.email)
    else:
        phone_c(c, p.phone, rng)
    c.lit("\n")
    return c


def held_opd_hindi(p: Person, enc: Encounter, rng: random.Random, noise: float) -> Cell:
    c = Cell(rng, noise)
    c.lit("ओपीडी पर्ची\nनाम- ")
    name_c(c, p, rng, "hi")
    c.lit("\nपिता/पति- ")
    rel_c(c, p, rng, "hi")
    c.lit("\nजन्म तिथि- ")
    date_c(c, p.birth, rng, "hi")
    c.lit("\nफोन: ")
    phone_c(c, p.phone, rng, "hi")
    c.lit("\nगाँव/मोहल्ला: ")
    addr_c(c, p, rng, "hi", "none")
    c.lit(" पिन ").P("PINCODE", p.pin)
    c.lit("\nशिकायत/निदान: ").M("DIAGNOSIS", dx_text(enc, "hi"))
    c.lit("\n")
    meds_c(c, enc, rng, "\n", "hi")
    c.lit("\n")
    return c


def held_claim_summary(p: Person, enc: Encounter, rng: random.Random, noise: float) -> Cell:
    c = Cell(rng, noise)
    c.lit("CLAIM SUMMARY\nMember: ")
    name_c(c, p, rng, "en", rel=True)
    c.lit("\nPolicy: ").P("INSURANCE", p.insurance or "POL/2020/" + str(rng.randrange(100000, 999999)))
    c.lit("\nHospital reg: ")
    mrn_c(c, p, enc)
    c.lit("\nAddress for correspondence: ")
    addr_c(c, p, rng, "en", "inline")
    c.lit("\nAdmitted ")
    date_c(c, enc.admit, rng)
    c.lit(" discharged ")
    date_c(c, disch(enc), rng)
    c.lit(" (LOS ")
    los_c(c, enc)
    c.lit(")\nPrincipal diagnosis: ").M("DIAGNOSIS", dx_text(enc, "en"))
    c.lit("\nContact: ")
    phone_c(c, p.phone, rng)
    c.lit("\n")
    return c


def seen_narrative(p: Person, enc: Encounter, rng: random.Random, noise: float) -> Cell:
    """Code-mixed clinic note with no label cues: names appear mid-sentence."""
    c = Cell(rng, noise)
    rel_word = rng.choice(["brother", "son", "husband", "neighbour"]) if p.sex == "F" else rng.choice(["brother", "father", "wife", "son"])
    c.P("NAME", name_text(p, rng, "latin", honorific=False), "patient").lit(", ")
    age_c(c, p, enc, rng)
    c.lit(f" {sex_word(p, 'en').lower()}, was brought on ")
    date_c(c, enc.admit, rng)
    c.lit(" by ").lit("his " if p.sex == "M" else "her ").lit(rel_word + " ")
    c.P("NAME", p.father[0].split()[0] + " " + p.last[0], "relative")
    c.lit(" with ").M("DIAGNOSIS", dx_text(enc, "en").lower())
    c.lit(". Ghar ")
    addr_c(c, p, rng, "hinglish", "none")
    c.lit(" mein hai. Family ne bataya ki ")
    c.P("NAME", p.first[0], "patient")
    c.lit(" ko 3 din se bukhar hai. Call ")
    phone_c(c, p.phone, rng)
    c.lit(". Started ")
    prefix, drug, freq, days = enc.meds[0]
    c.lit(prefix + " ").M("DRUG", drug).lit(" ").M("FREQ", freq).lit(" x ").M("DURATION", f"{days} days").lit(". ")
    doctor_c(c, enc, "en")
    c.lit(" to review.\n")
    return c


def held_narrative(p: Person, enc: Encounter, rng: random.Random, noise: float) -> Cell:
    """Hinglish shorthand note: names mid-sentence, no labels, mixed case."""
    c = Cell(rng, noise)
    c.lit("Today ")
    c.P("NAME", f"{p.first[0]} {p.last[0]}", "patient")
    c.lit(" aaye the, ")
    age_c(c, p, enc, rng, "hinglish")
    c.lit(f"/{p.sex}, ").M("DIAGNOSIS", dx_text(enc, "hinglish"))
    c.lit(" ki shikayat. Saath mein ")
    c.P("NAME", p.father[0].split()[0], "relative")
    c.lit(" ji the. ")
    c.P("NAME", p.first[0].lower(), "patient")
    c.lit(" bhaiya ka number " if p.sex == "M" else " didi ka number ")
    phone_c(c, p.phone, rng)
    c.lit(". ")
    vitals_c(c, enc, rng)
    c.lit(". Admit kiya on ")
    date_c(c, enc.admit, rng)
    c.lit(". ")
    doctor_c(c, enc, "en")
    c.lit(" ne dekha.\n")
    return c


SEEN_TXT = [seen_discharge_en, seen_rx_hinglish, seen_whatsapp, seen_hindi_note, seen_narrative]
HELD_TXT = [held_referral_en, held_nursing_handover, held_lab_report, held_opd_hindi, held_claim_summary, held_narrative]
TXT_BY_HOSP = {
    "seen": {"hosp_a": [0, 4], "hosp_b": [1], "hosp_c": [2, 4], "hosp_d": [3], "hosp_e": [0, 1, 2, 3, 4]},
    "held": {"hosp_a": [0, 5], "hosp_b": [1], "hosp_c": [2, 5], "hosp_d": [3], "hosp_e": [4, 0, 2, 5, 5]},
}


# ---------------------------------------------------------------- structured schemas
def _blank(rng: random.Random) -> Cell:
    return Cell(rng)


def cell_for(logical: str, p: Person, enc: Encounter, rng: random.Random, lang: str, noise: float,
             dstyle: int) -> Cell:
    c = Cell(rng, noise)
    if logical == "mrn":
        mrn_c(c, p, enc)
    elif logical == "name":
        name_c(c, p, rng, lang, rel=False)
    elif logical == "name_rel":
        name_c(c, p, rng, lang, rel=rng.random() < 0.25)
    elif logical == "guardian":
        rel_c(c, p, rng, lang)
    elif logical == "age":
        age_c(c, p, enc, rng, lang, bare=True)
    elif logical == "agesex":
        age_c(c, p, enc, rng, lang, bare=True)
        c.lit("/" + p.sex)
    elif logical == "sex":
        c.lit(sex_word(p, lang, short=rng.random() < 0.5))
    elif logical == "phone":
        phone_c(c, p.phone, rng, lang)
    elif logical == "phones":
        phone_c(c, p.phone, rng, lang)
        c.lit(rng.choice([", ", " / ", "; "]))
        phone_c(c, p.phone2, rng, lang)
    elif logical == "email":
        if p.email:
            c.P("EMAIL", p.email)
    elif logical == "address":
        addr_c(c, p, rng, lang, "none")
    elif logical == "address_pin":
        addr_c(c, p, rng, lang, rng.choice(["inline", "label"]))
    elif logical == "pin":
        c.P("PINCODE", p.pin)
    elif logical == "city":
        c.P("ADDRESS", p.city[1 if lang == "hi" else 0])
    elif logical == "admit":
        date_c(c, enc.admit, rng, lang, dstyle)
    elif logical == "discharge":
        date_c(c, disch(enc), rng, lang, dstyle)
    elif logical == "dob":
        date_c(c, p.birth, rng, lang, dstyle)
    elif logical == "dx":
        c.M("DIAGNOSIS", dx_text(enc, "hi" if lang == "hi" else "en"))
    elif logical == "meds":
        meds_c(c, enc, rng, "; ", lang)
    elif logical == "los":
        los_c(c, enc, lang, bare=True)
    elif logical == "labs":
        labs_c(c, enc, rng, "; ")
    elif logical == "vitals":
        vitals_c(c, enc, rng)
    elif logical == "abha":
        abha_c(c, p, rng)
    elif logical == "insurance":
        if p.insurance:
            c.P("INSURANCE", p.insurance)
    elif logical == "procedure":
        proc_c(c, enc)
    elif logical == "remarks":
        r = rng.random()
        if r < 0.35:
            c.lit("Pt c/o fever x 3 days. Attendant ").P("NAME", p.father[0], "relative").lit(" ")
            phone_c(c, p.phone2, rng)
        elif r < 0.6:
            c.lit("Discharged on ").M("DRUG", enc.meds[0][1]).lit(" ").M("FREQ", enc.meds[0][2]).lit(". Review OPD.")
        elif r < 0.75:
            c.lit("Referred by ")
            doctor_c(c, enc, "en")
        elif r < 0.85:
            trap_c(c, rng)
        elif r < 0.95:
            name_c(c, p, rng, "hinglish", honorific=False)
            c.lit(" ke ghar wale ")
            phone_c(c, p.phone2, rng)
            c.lit(" pe call karo")
    elif logical == "ward":
        c.lit(enc.ward)
    return c


# (header, logical)
SEEN_SCHEMAS = {
    "hosp_a": ("csv", "en", [("MRN", "mrn"), ("Patient Name", "name_rel"), ("Age", "age"), ("Sex", "sex"), ("Mobile", "phone"),
                             ("Address", "address"), ("Pincode", "pin"), ("Admission Date", "admit"),
                             ("Discharge Date", "discharge"), ("Diagnosis", "dx"), ("Medicines", "meds"), ("Remarks", "remarks")]),
    "hosp_b": ("xlsx", "hinglish", [("Reg No", "mrn"), ("Name", "name"), ("Guardian", "guardian"), ("Age/Sex", "agesex"),
                                    ("Contact", "phones"), ("Address", "address_pin"), ("DOA", "admit"), ("DOD", "discharge"),
                                    ("Dx", "dx"), ("Treatment", "meds"), ("LOS", "los")]),
    "hosp_c": ("json", "en", None),
    "hosp_d": ("csv", "hi", [("पंजीकरण संख्या", "mrn"), ("रोगी का नाम", "name"), ("आयु", "age"), ("लिंग", "sex"), ("फोन", "phone"),
                             ("पता", "address_pin"), ("भर्ती तिथि", "admit"), ("छुट्टी तिथि", "discharge"), ("निदान", "dx")]),
    "hosp_e": ("csv", "en", [("UID", "mrn"), ("Name", "name"), ("DOB", "dob"), ("Sex", "sex"), ("Phone", "phone"), ("Email", "email"),
                             ("City", "city"), ("PIN", "pin"), ("ABHA", "abha"), ("Insurance", "insurance"), ("Dx", "dx"),
                             ("Labs", "labs"), ("Vitals", "vitals")]),
}
HELD_SCHEMAS = {
    "hosp_a": ("csv", "en", [("Hospital No.", "mrn"), ("Full Name", "name_rel"), ("Years", "age"), ("Gender", "sex"),
                             ("Phone No", "phone"), ("Residence", "address_pin"), ("Admitted On", "admit"),
                             ("Discharged On", "discharge"), ("Final Diagnosis", "dx"), ("Rx", "meds"), ("Comments", "remarks")]),
    "hosp_b": ("xlsx", "en", [("UHID", "mrn"), ("Pt Name", "name"), ("Father/Husband Name", "guardian"), ("Age", "age"),
                              ("M/F", "sex"), ("Mobile No.", "phone"), ("Addr", "address"), ("Zip", "pin"), ("Admit Dt", "admit"),
                              ("Disch Dt", "discharge"), ("Diagnosis", "dx"), ("Procedure", "procedure"), ("Stay (days)", "los")]),
    "hosp_c": ("json", "en", None),
    "hosp_d": ("csv", "hi", [("क्रम", "mrn"), ("मरीज का नाम", "name"), ("पिता/पति का नाम", "guardian"), ("उम्र", "age"),
                             ("जन्म तिथि", "dob"), ("मोबाइल", "phones"), ("पता", "address_pin"), ("भर्ती", "admit"),
                             ("रोग", "dx")]),
    "hosp_e": ("csv", "hinglish", [("ID", "mrn"), ("Naam", "name"), ("Phone", "phone"), ("Ghar ka pata", "address_pin"),
                                   ("Date", "admit"), ("Bimari", "dx"), ("Dawai", "meds"), ("Ward", "ward"), ("Notes", "remarks")]),
}


def json_record(split: str, p: Person, enc: Encounter, rng: random.Random, noise: float, dstyle: int) -> dict:
    """Nested dict whose leaves are Cell objects (or lists of Cells)."""
    L = lambda name: cell_for(name, p, enc, rng, "en", noise, dstyle)  # noqa: E731
    if split == "dev":
        return {
            "patient_id": L("mrn"),
            "patient": {"name": L("name_rel"), "guardian": L("guardian"), "age": L("age"), "sex": L("sex")},
            "contact": {"mobile": L("phone"), "email": L("email"), "address": L("address"), "pincode": L("pin")},
            "visit": {
                "admitted": L("admit"), "discharged": L("discharge"), "diagnosis": L("dx"),
                "medications": [_one_med(enc, i, rng, noise) for i in range(len(enc.meds))],
                "notes": L("remarks"),
            },
        }
    return {
        "uhid": L("mrn"),
        "demographics": {"full_name": L("name"), "dob": L("dob"), "gender": L("sex"), "abha": L("abha")},
        "phones": [L("phone"), _phone2(p, rng, noise)],
        "residence": {"line": L("address_pin")},
        "encounter": {"admit_date": L("admit"), "los_days": L("los"), "final_dx": L("dx"), "labs": [_one_lab(enc, i, rng, noise) for i in range(len(enc.labs))],
                      "comment": L("remarks")},
    }


def _one_med(enc: Encounter, i: int, rng: random.Random, noise: float) -> Cell:
    prefix, drug, freq, days = enc.meds[i]
    c = Cell(rng, noise)
    c.lit(prefix + " ").M("DRUG", drug).lit(" ").M("FREQ", freq).lit(" x ").M("DURATION", f"{days} days")
    return c


def _one_lab(enc: Encounter, i: int, rng: random.Random, noise: float) -> Cell:
    n, v, u = enc.labs[i]
    c = Cell(rng, noise)
    c.M("LAB", f"{n} {v} {u}")
    return c


def _phone2(p: Person, rng: random.Random, noise: float) -> Cell:
    c = Cell(rng, noise)
    phone_c(c, p.phone2, rng)
    return c
