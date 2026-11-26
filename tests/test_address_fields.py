"""Address-part detector: village / locality / house / landmark by column meaning and by label.

All place names here are invented. Headers and labels include variants not seen in any practice file.
"""
import pytest

from secretwards.contracts import PIIType
from secretwards.detect import default_detectors, detect_unit
from secretwards.pipeline import make_unit

DETS = default_detectors()


def _spans(text, field=None):
    u = make_unit("d", field, text)
    s, _ = detect_unit(u, DETS)
    return s


def covered(text, value, field=None):
    i = text.index(value)
    j = i + len(value)
    return any(x.start <= i and j <= x.end for x in _spans(text, field))


def untouched(text, value, field=None):
    i = text.index(value)
    j = i + len(value)
    return not any(x.start < j and i < x.end for x in _spans(text, field))


# ---------------- columns
@pytest.mark.parametrize("hdr", ["Gaon", "Village Name", "village_name", "Mauza", "ग्राम", "गाँव का नाम", "Mohalla", "Locality",
                                 "Makan No", "house_no", "Landmark", "Gali"])
@pytest.mark.parametrize("value", ["Kesarpura Uttari", "धनौरा खुर्द", "Lakhanpur", "12/B"])
def test_address_part_columns(hdr, value):
    assert covered(value, value, field=hdr)


@pytest.mark.parametrize("hdr", ["Tehsil", "Jila", "District", "City", "State", "तहसील", "जिला"])
def test_generalization_columns_are_kept(hdr):
    # tehsil / district / city carry the generalization utility; never blank them here
    assert not [s for s in _spans("Fatehganj", field=hdr) if s.detector == "address_fields"]


def test_hospital_ward_column_is_not_an_address():
    assert untouched("Medicine", "Medicine", field="Ward")


# ---------------- labels in text
@pytest.mark.parametrize("text,value", [
    ("ग्राम: धनौरा खुर्द\nतारीख: 01/02/2025", "धनौरा खुर्द"),
    ("गाँव - रामपुरा", "रामपुरा"),
    ("Village: Kesarpura Uttari, Tehsil Fatehganj", "Kesarpura Uttari"),
    ("Gaon: Lakhanpur  Umar: 45", "Lakhanpur"),
    ("Mauza: Bhaironpur, Post Khera", "Bhaironpur"),
    ("Mohalla: Neem Tola; Pin 123456", "Neem Tola"),
    ("Landmark: Purana Peepal Ped", "Purana Peepal Ped"),
    ("मकान नं.: 45/7", "45/7"),
    ("Gram: Sundarpur", "Sundarpur"),
])
def test_labelled_values(text, value):
    assert covered(text, value)


def test_label_value_stops_before_tehsil():
    text = "Village: Kesarpura Uttari, Tehsil Fatehganj"
    assert untouched(text, "Fatehganj") or not [s for s in _spans(text) if s.detector == "address_fields"
                                                and text[s.start:s.end].endswith("Fatehganj")]


# ---------------- municipal ward vs hospital ward
@pytest.mark.parametrize("text", ["Address (attendant): C/O Gurmeet Bhatia, Ward 3",
                                  "H.No. 21, Ward 14, Mohalla Sabzi Mandi, Tehsil Fatehganj",
                                  "पता: मकान नं. 9, वार्ड 6, मोहल्ला नई बस्ती"])
def test_municipal_ward_in_address(text):
    w = "Ward 3" if "Ward 3" in text else ("Ward 14" if "Ward 14" in text else "वार्ड 6")
    assert covered(text, w)


@pytest.mark.parametrize("text,keep", [
    ("Ward: 4 (Medicine)", "4"),
    ("NURSING NOTES - Ward 9 (Surgery), Bed 12", "Ward 9"),
    ("Shifted to Ward 5, Bed 3", "Ward 5"),
    ("Ward 2 Female, bed 7", "Ward 2"),
])
def test_hospital_ward_kept(text, keep):
    assert untouched(text, keep)


# ---------------- medical collisions
@pytest.mark.parametrize("text,keep", [
    ("Gram stain: Gram positive cocci in clusters", "Gram positive"),
    ("Gram: negative bacilli", "negative"),
    ("Road traffic accident, head injury", "Road traffic accident"),
    ("Complete heart block on ECG", "heart block"),
    ("OPD: C/O fever for 8 days", "fever"),
])
def test_medical_phrases_untouched(text, keep):
    assert untouched(text, keep), [(s.type, text[s.start:s.end]) for s in _spans(text)]


# fixed in detect/address.py / detect/rules.py (these used to be strict xfails)
@pytest.mark.parametrize("text,keep", [
    ("Dal 50 ग्राम roz", "ग्राम"),
    ("Colony count >10^5 CFU/ml", "Colony count"),
    ("House surgeon on call informed", "House surgeon"),
])
def test_known_address_py_false_positives(text, keep):
    assert untouched(text, keep)
