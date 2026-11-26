"""The kit's 'meaning traps' and place handling, as general rules (all values invented)."""
from secretwards.contracts import MedKind, PIIType
from secretwards.detect import default_detectors, detect_unit
from secretwards.detect.medical_guard import find_medical
from secretwards.pipeline import make_unit

DETS = default_detectors()


def spans(text, field=None):
    u = make_unit("d", field, text)
    s, _ = detect_unit(u, DETS)
    return [(x.type, text[x.start:x.end], x.role) for x in s]


def ages(text):
    return [text[a:b] for a, b, k in find_medical(text) if k == MedKind.AGE]


def test_known_case_of_is_history_not_a_relative():
    assert not spans("History: K/C/O DM2 x 9 yrs. No K/C/O HTN. H/O TB 3 yrs back (completed ATT).")
    assert not spans("C/O fever x 3 days, cough 2 days")
    # but care-of a person still is a relative
    assert any("Ramakant" in v for _, v, _ in spans("Mother attended. C/O Ramakant Joglekar, Plot 5"))


def test_durations_are_not_ages():
    for t in ("K/C/O DM2 x 9 yrs", "H/O TB 9 yrs back", "diabetic for 12 years", "hypertensive since 2 yrs"):
        assert ages(t) == [], t
    assert ages("47 year old male") == ["47 year old"]
    assert ages("Age: 52 yrs / F") and ages("pt is 35 yrs, c/o fever") and ages("61Y/M")


def test_columns_that_name_things_other_than_people_are_not_name_columns():
    for header, value in (("Test Name", "Serum Creatinine"), ("Drug Name", "Tab. Metformin"), ("Hospital Name", "Kalyani Memorial Hospital"),
                          ("Department", "Medicine"), ("Diagnosis Name", "Typhoid Fever")):
        assert not spans(value, header), (header, value)
    assert any(t == PIIType.NAME for t, _, _ in spans("Pranav Wadekar", "Patient Name"))


def test_specialty_words_are_not_names():
    assert not [x for x in spans("Dr. Tanmay Phadke (MD Medicine), Neurology OPD") if x[0] == PIIType.NAME and x[2] != "doctor"]
    assert not any("Medicine" in v for _, v, _ in spans("Reviewed by Dr. Tanmay Phadke (MD Medicine)"))


def test_district_and_tehsil_are_kept_but_village_level_is_removed():
    assert not spans("Rampura Kalan", "District")                    # a district column is what generalization keeps
    assert not spans("Distt. Rampura Kalan")                          # "Distt. <place>" is not a person
    assert not any(t == PIIType.ADDRESS for t, v, _ in spans("Tehsil: Bhimpur, Distt. Rampura Kalan"))
    assert any(t == PIIType.ADDRESS for t, _, _ in spans("Gopalpur", "City"))   # a City column in a rural export holds villages
    assert any(t == PIIType.ADDRESS for t, _, _ in spans("Rampur Khurd", "Village/Mohalla"))


def test_pin_on_an_address_line_is_found_even_after_district():
    got = spans("Address: H.No 12, near Shiv mandir, Tehsil Bhimpur, Distt. Rampura Kalan 226017")
    assert any(t == PIIType.PINCODE and "226017" in v for t, v, _ in got)
    assert not any("226017" in v for t, v, _ in spans("Platelets 226017 /cumm"))
