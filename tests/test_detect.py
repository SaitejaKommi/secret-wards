import pytest

from secretwards.contracts import MedKind, PIIType
from secretwards.detect import default_detectors, detect_unit
from secretwards.pipeline import make_unit

DETS = default_detectors()


def spans(text, field=None):
    u = make_unit("d", field, text)
    s, m = detect_unit(u, DETS)
    return [(x.type, text[x.start:x.end]) for x in s], m


def types(text, field=None):
    return {t for t, _ in spans(text, field)[0]}


def found(text, typ, value, field=None):
    return any(t == typ and value in v for t, v in spans(text, field)[0])


# ---- traps called out in the brief
def test_dose_is_not_a_phone():
    s, meds = spans("Tab. Dolo 650 BD x 5 days")
    assert not s
    assert {k for _, _, k in [(m.start, m.end, m.kind) for m in meds]} >= {MedKind.DRUG, MedKind.FREQ, MedKind.DURATION}


def test_doctor_titled_drug_is_not_a_person():
    assert not found("Dr. Paracetamol 500 mg advised", PIIType.NAME, "Paracetamol")
    assert not spans("Dr. Paracetamol")[0]


def test_medical_values_are_not_pii():
    s, _ = spans("BP 120/80 mmHg, HR 88/min, SpO2 97%, Hb 9.8 g/dL, WBC 11200 /cumm, Platelets 150000 /cumm, Creatinine 1.2 mg/dL")
    assert not s


# ---- phones
@pytest.mark.parametrize("p", ["9876543210", "+91 98765 43210", "+91-9876543210", "098765-43210", "(+91) 9876543210",
                               "919876543210", "9876 543 210", "९८७६५४३२१०", "98765 4321O"])
def test_phone_formats(p):
    assert found(f"Contact: {p} for details", PIIType.PHONE, p[-4:])


def test_phone_next_to_a_date():
    assert found("Date: 20.07.18 9876543210", PIIType.PHONE, "9876543210")


# ---- ids, email, dates
def test_ids_and_email():
    t = "ABHA: 12-3456-7890-1234, Policy POL/2021/123456, UHID 12345678, mail ravi.k@example.com"
    ty = types(t)
    assert {PIIType.ABHA, PIIType.INSURANCE, PIIType.MRN, PIIType.EMAIL} <= ty


@pytest.mark.parametrize("d", ["12/03/2021", "12-03-2021", "12.03.21", "2021-03-12", "12 Mar 2021", "12th March, 2021", "March 12, 2021",
                               "१२/०३/२०२१", "12 मार्च 2021", "12-03-2O21"])
def test_date_formats(d):
    assert PIIType.DATE in types(f"Admitted on {d}.")


def test_age_is_medical_not_pii():
    s, meds = spans("47 year old male")
    assert not s
    assert any(m.kind == MedKind.AGE for m in meds)


# ---- names
@pytest.mark.parametrize("text,expect", [
    ("Patient Name: Tushar Zaidi", "Tushar Zaidi"),
    ("Mr. Chandrakant Pillai was admitted", "Chandrakant Pillai"),
    ("Rajesh Kumar s/o Shyam Lal", "Shyam Lal"),
    ("Sunita Devi w/o Rajesh Kumar", "Rajesh Kumar"),
    ("मरीज़ का नाम: राजेश कुमार", "राजेश कुमार"),
    ("मरीज़ का नाम: निशा सिंह, पिता: राशिद सिंह", "राशिद सिंह"),
    ("Referred by Dr. Nilesh Bhosale", "Nilesh Bhosale"),
    ("Guardian: Banwari Lal", "Banwari Lal"),
    ("rajesh bhaiya ko dawai di", "rajesh"),
    ("Kumar, Rajesh admitted", "Rajesh"),
    ("Patient R. Kumar stable", "R. Kumar"),
])
def test_names_in_three_languages(text, expect):
    assert found(text, PIIType.NAME, expect)


def test_name_not_triggered_by_clinical_words():
    assert not spans("Patient presented with fever and cough. w/o vomiting. h/o diabetes.")[0]


def test_header_hint_marks_name_cell_but_content_wins_on_shifted_columns():
    assert found("Tushar Zaidi", PIIType.NAME, "Zaidi", field="Patient Name")
    # a phone number that landed in the name column is still a phone
    assert found("9876543210", PIIType.PHONE, "9876543210", field="Patient Name")
    # a diagnosis in the name column is not a name
    assert not found("Typhoid fever", PIIType.NAME, "Typhoid", field="Patient Name")


# ---- addresses
def test_address_with_landmarks_and_pin():
    t = "Flat 506, Ambedkar Chowk, near Sai Baba mandir, Bhopal, Pincode 295301"
    s, _ = spans(t)
    assert any(ty == PIIType.ADDRESS and "Sai Baba" in v for ty, v in s)
    assert any(ty in (PIIType.PINCODE, PIIType.ADDRESS) and "295301" in v for ty, v in s)  # the PIN is covered


def test_hinglish_and_hindi_landmarks():
    assert found("Ghar: Gandhi Nagar, Hanuman mandir ke paas, Lucknow", PIIType.ADDRESS, "Hanuman mandir ke paas")
    assert found("पता: गांधी नगर, हनुमान मंदिर के पास, लखनऊ", PIIType.ADDRESS, "हनुमान मंदिर के पास")


def test_platelet_count_is_not_a_pin():
    assert not found("Platelets 150000 /cumm", PIIType.PINCODE, "150000")


def test_pin_in_hindi_label_line_is_not_address_word():
    # the label "गाँव/मोहल्ला:" must not be treated as a locality
    assert PIIType.ADDRESS not in types("गाँव/मोहल्ला: ")
