"""BLIND split: written after the detectors were frozen for the final report. Different name pool,
different cities / areas, different template phrasing and column schemas. It is scored ONCE per
release and never used for tuning. (Honest limit: the author of this file also wrote the detectors.)"""
from __future__ import annotations

import random

from .cell import Cell
from .people import Encounter, Person
from . import templates as T

FIRST_M = [("Abhinav", "अभिनव"), ("Bhuvan", "भुवन"), ("Chirag", "चिराग"), ("Devansh", "देवांश"), ("Ekansh", "एकांश"),
           ("Farid", "फरीद"), ("Gaurang", "गौरांग"), ("Hitesh", "हितेश"), ("Inder", "इंदर"), ("Jayant", "जयंत"),
           ("Kartik", "कार्तिक"), ("Lokendra", "लोकेंद्र"), ("Mayank", "मयंक"), ("Nakul", "नकुल"), ("Pushkar", "पुष्कर"),
           ("Qasim", "कासिम"), ("Ritesh", "रितेश"), ("Siddharth", "सिद्धार्थ")]
FIRST_F = [("Aarushi", "आरुषि"), ("Bhavya", "भव्या"), ("Charulata", "चारुलता"), ("Deepti", "दीप्ति"), ("Esha", "ईशा"),
           ("Falguni", "फाल्गुनी"), ("Garima", "गरिमा"), ("Harshita", "हर्षिता"), ("Ishita", "इशिता"), ("Juhi", "जूही"),
           ("Kashvi", "काश्वी"), ("Lavanya", "लावण्या"), ("Mrunal", "मृणाल"), ("Nandini", "नंदिनी"), ("Pallavi", "पल्लवी"),
           ("Rukhsar", "रुखसार")]
LAST = [("Acharya", "आचार्य"), ("Bajpai", "बाजपेयी"), ("Chandel", "चंदेल"), ("Dixit", "दीक्षित"), ("Gokhale", "गोखले"),
        ("Hussain", "हुसैन"), ("Inamdar", "इनामदार"), ("Jaiswal", "जायसवाल"), ("Kaushik", "कौशिक"), ("Lamba", "लांबा"),
        ("Menon", "मेनन"), ("Nagpal", "नागपाल"), ("Oberoi", "ओबेरॉय"), ("Parmar", "परमार"), ("Raizada", "रायजादा"),
        ("Sethi", "सेठी")]
CITIES = [("Satna", "सतना"), ("Rewa", "रीवा"), ("Sagar", "सागर"), ("Haldwani", "हल्द्वानी"), ("Bhilwara", "भीलवाड़ा"), ("Durg", "दुर्ग")]
AREAS = [("Kanhaiya", "कन्हैया"), ("Rani", "रानी"), ("Maharana", "महाराणा"), ("Jyotiba", "ज्योतिबा"), ("Lokmanya", "लोकमान्य")]


def rel_phrase(p: Person, rng: random.Random):
    if p.sex == "F" and p.husband:
        return p.husband, rng.choice(["husband", "pati"])
    return p.father, rng.choice(["father", "pita"])


def blind_case_sheet(p: Person, enc: Encounter, rng: random.Random, noise: float) -> Cell:
    c = Cell(rng, noise)
    c.lit("CASE SHEET\nName of the patient : ")
    T.hon(p, rng, c, 0.3)
    c.P("NAME", T.name_text(p, rng, "latin", honorific=False), "patient")
    r, word = rel_phrase(p, rng)
    c.lit(f"\nInformant : ").P("NAME", r[0], "relative").lit(f" ({word})")
    c.lit("\nSex/Age : " + p.sex + " / ")
    T.age_c(c, p, enc, rng)
    c.lit("\nResident of ")
    T.addr_c(c, p, rng, "en", "label")
    c.lit("\nTel. ")
    T.phone_c(c, p.phone, rng)
    if p.email:
        c.lit("   Email id: ").P("EMAIL", p.email)
    c.lit("\nReg. No. ")
    T.mrn_c(c, p, enc)
    c.lit("\nAdmitted ")
    T.date_c(c, enc.admit, rng)
    c.lit(" -- Discharged ")
    T.date_c(c, T.disch(enc), rng)
    c.lit("\nFinal impression: ").M("DIAGNOSIS", T.dx_text(enc, "en"))
    c.lit("\nRx: ")
    T.meds_c(c, enc, rng, " / ")
    c.lit("\nInvestigations: ")
    T.labs_c(c, enc, rng)
    c.lit("\nSigned ")
    T.doctor_c(c, enc, "en")
    c.lit("\n")
    return c


def blind_hinglish_msg(p: Person, enc: Encounter, rng: random.Random, noise: float) -> Cell:
    c = Cell(rng, noise)
    r, _ = rel_phrase(p, rng)
    c.P("NAME", r[0].split()[0], "relative").lit(" ji ne bola ki ")
    c.P("NAME", p.first[0], "patient").lit(" ki tabiyat kharab hai, ")
    c.M("DIAGNOSIS", T.dx_text(enc, "hinglish"))
    c.lit(" ho gaya. ")
    T.date_c(c, enc.admit, rng)
    c.lit(" ko admit karna hai. Number ")
    T.phone_c(c, p.phone, rng)
    c.lit(". Hum ")
    T.addr_c(c, p, rng, "hinglish", "none")
    c.lit(" mein rehte hain. Bukhar ")
    c.M("VITAL", f"Temp {enc.vitals['Temp']} F")
    c.lit(" hai aur ")
    prefix, drug, freq, days = enc.meds[0]
    c.M("DRUG", drug).lit(" ").M("FREQ", freq).lit(" de rahe hain.\n")
    return c


def blind_hindi_card(p: Person, enc: Encounter, rng: random.Random, noise: float) -> Cell:
    c = Cell(rng, noise)
    c.lit("रोगी: ")
    c.P("NAME", T.name_text(p, rng, "deva"), "patient")
    r, _ = rel_phrase(p, rng)
    c.lit("\nसंरक्षक: ").P("NAME", r[1], "relative")
    c.lit("\nसंपर्क सूत्र: ")
    T.phone_c(c, p.phone, rng, "hi")
    c.lit("\nनिवास: ")
    T.addr_c(c, p, rng, "hi", "inline")
    c.lit("\nतिथि: ")
    T.date_c(c, enc.admit, rng, "hi")
    c.lit("\nरोग: ").M("DIAGNOSIS", T.dx_text(enc, "hi"))
    c.lit("\nउपचार: ")
    T.meds_c(c, enc, rng, ", ", "hi")
    c.lit("\n")
    return c


BLIND_TXT = [blind_case_sheet, blind_hinglish_msg, blind_hindi_card]
BLIND_TXT_BY_HOSP = {"hosp_a": [0, 1], "hosp_b": [1, 2], "hosp_c": [0, 2], "hosp_d": [2, 1], "hosp_e": [0, 1, 2]}

BLIND_SCHEMAS = {
    "hosp_a": ("csv", "en", [("Sl", "mrn"), ("Patient", "name"), ("Relative", "guardian"), ("Yrs", "age"), ("Sx", "sex"), ("Tel", "phone"),
                             ("Home", "address_pin"), ("Admit", "admit"), ("Dx", "dx"), ("Rx", "meds")]),
    "hosp_b": ("xlsx", "en", [("Hospital ID", "mrn"), ("Name of Patient", "name_rel"), ("Date of Birth", "dob"), ("Mobile", "phones"),
                              ("Locality", "address"), ("Pin", "pin"), ("DOA", "admit"), ("Final Diagnosis", "dx"), ("Remarks", "remarks")]),
    "hosp_c": ("json", "en", None),
    "hosp_d": ("csv", "hi", [("रोगी", "name"), ("संरक्षक", "guardian"), ("आयु", "age"), ("संपर्क", "phone"), ("निवास", "address_pin"),
                             ("तारीख", "admit"), ("रोग", "dx")]),
    "hosp_e": ("csv", "hinglish", [("Reg", "mrn"), ("Patient ka naam", "name"), ("Umar", "age"), ("Mobile", "phone"), ("Pata", "address_pin"),
                                   ("Tareekh", "admit"), ("Bimari", "dx"), ("Dawai", "meds"), ("Note", "remarks")]),
}


def blind_json_record(p: Person, enc: Encounter, rng: random.Random, noise: float, dstyle: int) -> dict:
    L = lambda name: T.cell_for(name, p, enc, rng, "en", noise, dstyle)  # noqa: E731
    first, last = Cell(rng, noise), Cell(rng, noise)
    first.P("NAME", p.first[0], "patient")
    last.P("NAME", p.last[0], "patient")
    return {
        "id": L("mrn"),
        "person": {"first": first, "last": last, "gender": L("sex"), "born": L("dob"), "next_of_kin": L("guardian")},
        "phone": L("phone"),
        "where": {"address": L("address_pin")},
        "stay": {"from": L("admit"), "days": L("los"), "dx": L("dx"), "treatment": [T._one_med(enc, i, rng, noise) for i in range(len(enc.meds))]},
    }
