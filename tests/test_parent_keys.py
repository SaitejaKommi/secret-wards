"""A JSON leaf whose own key says nothing ("v", "tq", "n") takes its meaning from the nearest informative parent ("addr", "guardian").
CSV headers with dots ("Mob.", "Pt. Name") are used whole. Invented values only."""
import json

import pytest

from secretwards.contract.run import run_contract
from secretwards.contracts import PIIType
from secretwards.detect import default_detectors, detect_unit
from secretwards.detect.headers import hint_for
from secretwards.pipeline import header_of, make_unit

DETS = default_detectors()


def spans(field, text, source="json"):
    s, _ = detect_unit(make_unit("d", field, text, source), DETS)
    return s


# ---- header_of
@pytest.mark.parametrize("path,expected", [
    ("encounters[3].addr.v", "addr v"),                       # unknown leaf under an address object
    ("a.address.line1", "address line1"),
    ("patient.contact.addr.colony", "addr colony"),            # nearest informative parent, any depth
    ("guardian.n", "guardian n"),                              # short leaf under a name object
    ("patient.name", "name"),                                  # a leaf with its own meaning never changes
    ("address.state", "state"),                                # kept on purpose
    ("address.district", "district"),
    ("address.use", "use"),
    ("patient.notes", "notes"),                                # a longer unknown leaf is not a name
    ("patient.diagnosis", "diagnosis"),
    ("visits[0].bp", "bp"),                                    # no informative parent: unchanged
    ("hospital", "hospital"),
])
def test_header_of_json_paths(path, expected):
    assert header_of(path, "json") == expected


@pytest.mark.parametrize("col,kind", [
    ("Mob.", "phone"), ("Ph No", "phone"), ("Ph.", "phone"), ("Mobile No.", "phone"), ("Sampark", "phone"),
    ("Pt. Name", "name"), ("Pt Nm", "name"), ("Janm Tithi", "dob"), ("Ling", "sex"), ("Rishtedar", "name"),
    ("pH", ""), ("Hb", ""),                                    # a lab pH / Hb column is not a phone
])
def test_csv_header_is_used_whole(col, kind):
    h = header_of(col, "csv")
    assert h.replace(" ", "") == col.strip().lower().replace(" ", "")   # camel-case split may add a space ("pH" -> "p h"), nothing else changes
    assert hint_for(h).kind == kind


# ---- detection
@pytest.mark.parametrize("parent", ["addr", "address", "residence", "perm_address", "addresses[0].addr", "patient.contact.addr"])
@pytest.mark.parametrize("leaf", ["v", "vill", "line1", "colony", "landmark", "street", "area"])
def test_unknown_leaf_under_an_address_object_is_an_address(parent, leaf):
    s = spans(f"encounters[1].{parent}.{leaf}", "Marikuppam")
    assert any(x.type == PIIType.ADDRESS and x.start == 0 and x.end >= len("Marikuppam") for x in s), (parent, leaf, s)


@pytest.mark.parametrize("path,value", [
    ("addr.state", "Karnataka"), ("address.district", "Chitradurga"), ("address.use", "home"), ("addr.tq", "Challakere"), ("address.type", "physical"),
    ("patient.notes", "follow up in one week"), ("patient.diagnosis", "hypertension"),
])
def test_schema_and_kept_leaves_are_untouched(path, value):
    assert not [x for x in spans("p." + path, value) if x.type in (PIIType.ADDRESS, PIIType.NAME)]


@pytest.mark.parametrize("path", ["guardian.n", "patient.n", "patient.nm", "relative.v"])
def test_short_leaf_under_a_name_object_is_a_name(path):
    s = spans("x." + path, "ravindranath")   # lowercase, unseen: only the structure says it is a person
    assert any(x.type == PIIType.NAME for x in s), s


# ---- end to end
def test_nested_json_with_unfamiliar_keys_leaks_no_village(tmp_path):
    inp, out = tmp_path / "in", tmp_path / "out"
    inp.mkdir()
    enc = [{"pt": {"nm": "Zephyrine Quillfeather", "ph": "9871234560"},
            "addr": {"v": f"Marikuppam{i}", "tq": "Challakere", "pin": "577522", "state": "Karnataka", "use": "home"},
            "vit": {"bp": "142/88 mmHg"}, "note": "C/O fever x 3 days"} for i in range(4)]
    (inp / "visits.json").write_text(json.dumps({"hospital": "Mission Hospital", "encounters": enc}), encoding="utf-8")
    assert run_contract(inp, out, b"parent-key-secret") == 0
    raw = (out / "sanitized" / "visits.json").read_text(encoding="utf-8")
    assert "Marikuppam" not in raw and "Quillfeather" not in raw and "9871234560" not in raw and "577522" not in raw
    assert "Karnataka" in raw and '"home"' in raw and "142/88 mmHg" in raw and "C/O fever x 3 days" in raw


def test_csv_with_dotted_headers_redacts_the_phone_column(tmp_path):
    inp, out = tmp_path / "in", tmp_path / "out"
    inp.mkdir()
    (inp / "r.csv").write_text("Pt. Name,Mob.,Janm Tithi,Ling\nZephyrine Quillfeather,98765-01234,12.03.1971,F\n", encoding="utf-8")
    assert run_contract(inp, out, b"parent-key-secret") == 0
    text = (out / "sanitized" / "r.csv").read_text(encoding="utf-8")
    assert "Quillfeather" not in text and "98765" not in text and "12.03.1971" not in text, text
    assert text.splitlines()[0] == "Pt. Name,Mob.,Janm Tithi,Ling"   # the headers themselves are not personal data
