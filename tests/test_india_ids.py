"""India id detector: Aadhaar, masked Aadhaar, PAN, hospital record numbers.

All values are invented. Labels deliberately include variants that are NOT in any practice file,
because the hidden data uses unseen labels and column names.
"""
import pytest

from secretwards.contracts import PIIType
from secretwards.detect import default_detectors, detect_unit
from secretwards.pipeline import make_unit

DETS = default_detectors()


def spans(text, field=None):
    u = make_unit("d", field, text)
    s, _ = detect_unit(u, DETS)
    return [(x.type, text[x.start:x.end]) for x in s]


def covered(text, value, field=None):
    """value is entirely inside one redacted span"""
    i = text.index(value)
    j = i + len(value)
    u = make_unit("d", field, text)
    s, _ = detect_unit(u, DETS)
    return any(x.start <= i and j <= x.end for x in s)


def untouched(text, value, field=None):
    i = text.index(value)
    j = i + len(value)
    u = make_unit("d", field, text)
    s, _ = detect_unit(u, DETS)
    return not any(x.start < j and i < x.end for x in s)


# ---------------- Aadhaar
@pytest.mark.parametrize("v", ["2468 1357 9024", "3579-2468-1350", "513579246801", "७५३१ ८६४२ ०९७५"])
def test_aadhaar_in_text_with_label(v):
    assert covered(f"Aadhaar No. {v}, mobile not given", v)


@pytest.mark.parametrize("label", ["आधार संख्या:", "UID No -", "Adhar card", "aadhar #"])
def test_aadhaar_unseen_labels(label):
    v = "6802 4613 5791"
    assert covered(f"{label} {v}", v)


@pytest.mark.parametrize("hdr", ["Aadhar", "aadhaar_no", "UID", "आधार नंबर", "AadhaarNumber"])
def test_aadhaar_column_whole_cell(hdr):
    for v in ["802468135790", "8024 6813 5790", "XXXX-XXXX-5790", "8024 6813 579"]:  # last one malformed: still removed
        assert covered(v, v, field=hdr), (hdr, v)


def test_aadhaar_grouped_without_label():
    assert covered("ID proof 4321 8765 2109 seen", "4321 8765 2109")


@pytest.mark.parametrize("v", ["XXXX XXXX 4821", "xxxx-xxxx-4821", "********4821"])
def test_masked_aadhaar_tail_removed(v):
    # the visible last four digits match the attacker's registry
    assert covered(f"Aadhaar: {v}", v)


def test_abha_is_not_split_into_aadhaar():
    v = "71-2345-6789-0123"
    out = spans(f"ABHA {v}")
    assert (PIIType.ABHA, v) in out


# ---------------- PAN
@pytest.mark.parametrize("v", ["ABCPK1234Q", "XYZFM9876L", "QWEHT0001Z"])
def test_pan_shape_anywhere(v):
    assert covered(f"payer {v} cleared", v)


@pytest.mark.parametrize("hdr", ["payer_pan", "PAN No", "pan card", "Permanent Account Number", "पैन"])
def test_pan_column(hdr):
    assert covered("ABCPK1234Q", "ABCPK1234Q", field=hdr)
    assert covered("abcpk1234q", "abcpk1234q", field=hdr)


def test_pan_lowercase_with_label():
    assert covered("PAN no: abcpk1234q", "abcpk1234q")


@pytest.mark.parametrize("text", ["Pan masala chewing 10 yrs, quit", "paan khata hai roz", "pan-systolic murmur grade 3/6",
                                  "Pantoprazole 40 mg 1-0-0"])
def test_pan_word_alone_is_not_pii(text):
    assert not [t for t, _ in spans(text) if t == PIIType.ID]


# ---------------- hospital record numbers
@pytest.mark.parametrize("v", ["IPD-2025-01234", "IP/25/00321", "KMC/OPD/24/5521", "RGH2025-007731", "MR-77-123456"])
def test_hospital_number_structure(v):
    assert covered(f"Nursing notes - Ward 3, Bed 12 - {v}", v)


@pytest.mark.parametrize("label", ["IPD No:", "Indoor No.:", "पंजीकरण सं.:", "भर्ती क्रमांक:", "Case No #", "Ref. Number:"])
def test_hospital_number_after_label(label):
    v = "4471203"
    assert covered(f"{label} {v}", v)


def test_prefix_letters_and_digits_go_together():
    # a partial match (letters only) would leave the digits visible
    text = "पंजीकरण सं.: ABC/25/073318"
    assert covered(text, "ABC/25/073318")


@pytest.mark.parametrize("hdr", ["Panjikaran", "IPD No", "admission_no", "पंजीकरण संख्या"])
def test_hospital_number_column(hdr):
    assert covered("A-77012", "A-77012", field=hdr)


# ---------------- meaning traps: these must NOT become ids
@pytest.mark.parametrize("text,keep", [
    ("BP 141/77 mmHg, Pulse 91/min", "141/77"),
    ("BP-130/80 sitting", "130/80"),
    ("WBC 11200 /cumm", "11200"),
    ("COVID-19 negative", "COVID-19"),
    ("Dx: J18.9 pneumonia", "J18.9"),
    ("Tab Paracetamol 650 mg 1-1-1 x 5 days", "650"),
    ("Bed No: 12345", "12345"),
    ("Ward No: 4 (Medicine)", "4"),
    ("Batch No: 230415 exp 2027", "230415"),
    ("NS-500/100 ml infusion", "500/100"),
])
def test_medical_and_ward_values_untouched(text, keep):
    out = spans(text)
    assert not [v for t, v in out if t in (PIIType.ID, PIIType.MRN) and keep in v], out


def test_admission_date_column_is_a_date_not_an_id():
    out = spans("12/03/2025", field="admission_date")
    assert out and all(t == PIIType.DATE for t, _ in out)


def test_date_after_prefix_is_not_an_mrn():
    out = spans("DOB-12/04/1977")
    assert not [v for t, v in out if t == PIIType.MRN]


def test_deterministic():
    text = "Aadhaar 2468 1357 9024, PAN ABCPK1234Q, IPD-2025-01234"
    assert spans(text) == spans(text)


# ---------------- MRN feeds linking: doctor / facility numbers must never be typed MRN
_NON_PATIENT = [
    ("Dr. P. Lohani, MBBS, Reg. No. 45678", "45678"),
    ("Regd. No: XY/CEA/2019/1234", "XY/CEA/2019/1234"),
    ("Drug Lic. No: 20B-55123", "55123"),
    ("Hospital Reg No: HR-2011-00456", "HR-2011-00456"),
    ("Ref. Number: 7712045", "7712045"),
]


@pytest.mark.parametrize("text,value", _NON_PATIENT)
def test_non_patient_numbers_redacted_but_not_mrn(text, value):
    from secretwards.detect.india_ids import IndiaIdDetector
    u = make_unit("d", None, text)
    assert not [s for s in IndiaIdDetector().detect(u) if s.type == PIIType.MRN]
    assert covered(text, value)


# Pre-existing in the lead's detect/rules.py (_MRN_CUE types any "Reg No" as MRN). strict xfail: remove once fixed there.
@pytest.mark.xfail(strict=True, reason="detect/rules.py _MRN_CUE types doctor / hospital Reg No as MRN")
@pytest.mark.parametrize("text,value", [_NON_PATIENT[0], _NON_PATIENT[3]])
def test_known_rules_py_mrn_on_facility_numbers(text, value):
    assert not [v for t, v in spans(text) if t == PIIType.MRN]


@pytest.mark.parametrize("text,value", [("UHID: 5520117", "5520117"), ("IPD No: 2025/00412", "2025/00412"),
                                        ("पंजीकरण सं.: 4471203", "4471203"), ("Patient ID - KP-88213", "KP-88213")])
def test_patient_numbers_are_mrn(text, value):
    assert (PIIType.MRN, value) in spans(text)
