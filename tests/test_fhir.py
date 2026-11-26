"""FHIR: resource-aware policy (fhir/sanitize.py) and structural validator (fhir/validate.py). Invented data only."""
import base64
import copy
import json

import pytest

from secretwards.contract import run as contract_run
from secretwards.contracts import PIIType
from secretwards.fhir.sanitize import apply_bundle_policy, bundle_actions
from secretwards.fhir.validate import validate_bundle
from secretwards.ingest import _flatten, path_name
from secretwards.pipeline import make_unit

P, E, O, D, C = ("a1f0c2de-1111-4c41-8c64-c101720fb2df", "b2e1d3ef-2222-4b6c-9d03-fb31f247775f",
                 "c3d2e4f0-3333-4a5b-8c6d-7e8f9a0b1c2d", "d4e3f5a1-4444-4b6c-9d7e-8f9a0b1c2d3e",
                 "e5f4a6b2-5555-4c7d-8e9f-0a1b2c3d4e5f")
NOTE = "Patient Tejbir Tiklani, phone 9871234560, admitted with viral fever. BP 120/80 mmHg."


def bundle():
    return {
        "resourceType": "Bundle", "id": "bundle-1", "type": "document", "timestamp": "2025-03-05T11:00:00+05:30",
        "meta": {"profile": ["https://example.org/fhir/StructureDefinition/DocumentBundle"]},
        "entry": [
            {"fullUrl": f"urn:uuid:{P}", "resource": {
                "resourceType": "Patient", "id": P, "gender": "male", "birthDate": "1981-06-14",
                "name": [{"text": "Tejbir Tiklani", "family": "Tiklani", "given": ["Tejbir"]}],
                "telecom": [{"system": "phone", "value": "9871234560", "use": "mobile"},
                            {"system": "email", "value": "ztiklani@example.org"}],
                "identifier": [{"system": "https://example.org/mrn", "value": "QXH-25-008812"}],
                "address": [{"line": ["H.No. 87, Gali 4"], "city": "Bhimsar", "district": "Fatehganj", "state": "Madhya Pradesh",
                             "postalCode": "201301", "country": "IN"}],
                "contact": [{"relationship": [{"text": "Father"}], "name": {"text": "Harbans Tiklani"}}],
                "extension": [{"url": "https://example.org/fhir/StructureDefinition/mothers-name", "valueString": "Navjot Tiklani"}]}},
            {"fullUrl": f"urn:uuid:{D}", "resource": {
                "resourceType": "Practitioner", "id": D, "name": [{"text": "Dr. Meenakshi Raghavan"}],
                "qualification": [{"code": {"text": "MD Medicine"}}]}},
            {"fullUrl": f"urn:uuid:{O}", "resource": {
                "resourceType": "Organization", "id": O, "name": "Ganga Kinare Seva Niketan",
                "address": [{"city": "Fatehganj", "state": "Madhya Pradesh", "country": "IN"}]}},
            {"fullUrl": f"urn:uuid:{E}", "resource": {
                "resourceType": "Encounter", "id": E, "status": "finished", "class": {"code": "IMP", "display": "inpatient"},
                "identifier": [{"value": "IPD-2025-00412"}],
                "subject": {"reference": f"urn:uuid:{P}", "display": "Tejbir Tiklani"},
                "serviceProvider": {"reference": f"urn:uuid:{O}"},
                "period": {"start": "2025-03-02T09:30:00+05:30", "end": "2025-03-05T11:00:00+05:30"}}},
            {"fullUrl": f"urn:uuid:{C}", "resource": {
                "resourceType": "Composition", "id": C, "status": "final", "type": {"text": "Discharge summary"},
                "date": "2025-03-05", "title": "Discharge summary", "subject": {"reference": f"urn:uuid:{P}", "display": "Tejbir Tiklani"},
                "author": [{"reference": f"urn:uuid:{D}", "display": "Dr. Meenakshi Raghavan"}]}},
            {"fullUrl": "urn:uuid:f6a5b7c3-6666-4d8e-9f0a-1b2c3d4e5f6a", "resource": {
                "resourceType": "DocumentReference", "id": "f6a5b7c3-6666-4d8e-9f0a-1b2c3d4e5f6a", "status": "current",
                "subject": {"reference": f"urn:uuid:{P}"},
                "content": [{"attachment": {"contentType": "text/plain", "data": base64.b64encode(NOTE.encode()).decode()}}]}},
        ]}


def flat(b):
    leaves = []
    _flatten(b, [], leaves)
    return {path_name(p): ("" if v is None else str(v)) for p, v, _t in leaves}


def by_suffix(actions, suffix):
    return {a for k, a in actions.items() if k.endswith(suffix)}


# ---------------------------------------------------------------- policy
def test_actions_by_resource():
    a = bundle_actions(flat(bundle()))
    pat, prac, org, enc, comp = (f"entry[{i}].resource." for i in (0, 1, 2, 3, 4))
    assert a[pat + "name[0].family"] == a[pat + "name[0].given[0]"] == a[pat + "name[0].text"] == "patient_name"
    assert a[pat + "telecom[0].value"] == "phone" and a[pat + "telecom[1].value"] == "email"
    assert a[pat + "identifier[0].value"] == "mrn" and a[enc + "identifier[0].value"] == "mrn"
    assert a[pat + "address[0].line[0]"] == a[pat + "address[0].city"] == "address"
    assert a[pat + "address[0].postalCode"] == "pin"
    assert a[pat + "address[0].state"] == a[pat + "address[0].district"] == "keep"   # generalization levels
    assert a[pat + "contact[0].name.text"] == "relative_name"
    assert a[pat + "extension[0].url"] == "keep" and a[pat + "extension[0].valueString"] == "detect"
    assert a[prac + "name[0].text"] == "keep" and a[org + "name"] == "keep" and a[org + "address[0].city"] == "keep"
    assert a[comp + "subject.display"] == a[enc + "subject.display"] == "patient_name"
    assert a[comp + "author[0].display"] == "keep"
    assert a["meta.profile[0]"] == "keep" and a["entry[0].fullUrl"] == "keep"
    assert a["entry[5].resource.content[0].attachment.data"] == "detect"   # base64: cleaned and re-encoded downstream


def test_unknown_resource_falls_back_to_detection():
    b = bundle()
    b["entry"].append({"fullUrl": "urn:uuid:0a1b2c3d-7777-4e8f-9a0b-1c2d3e4f5a6b",
                       "resource": {"resourceType": "FutureThing", "id": "x1", "note": "free text"}})
    a = bundle_actions(flat(b))
    assert a["entry[6].resource.note"] == "detect"


def test_not_a_bundle_has_no_actions():
    assert bundle_actions({"resourceType": "Patient", "name[0].text": "x"}) == {}


def test_apply_policy_forces_and_clears_spans():
    fields = flat(bundle())
    units = [make_unit("d", f, v) for f, v in fields.items() if v.strip()]
    spans = {u.field: [] for u in units}
    org = "entry[2].resource.name"
    from secretwards.contracts import Span
    spans[org] = [Span("d", org, 0, 7, PIIType.NAME, "names", 0.9, "patient")]  # a detector thought it was a person
    counts = apply_bundle_policy(fields, units, spans)
    assert spans[org] == []
    fam = spans["entry[0].resource.name[0].family"]
    assert len(fam) == 1 and fam[0].type == PIIType.NAME and fam[0].role == "patient" and (fam[0].start, fam[0].end) == (0, 7)
    assert spans["entry[0].resource.telecom[0].value"][0].type == PIIType.PHONE
    assert spans["entry[0].resource.address[0].postalCode"][0].type == PIIType.PINCODE
    assert counts["patient_name"] >= 5 and counts["keep"] > 0


# ---------------------------------------------------------------- validator
def test_valid_bundle_passes():
    assert validate_bundle(bundle()) == []


@pytest.mark.parametrize("mutate,code", [
    (lambda b: b["entry"][0]["resource"].__setitem__("id", "[PHONE]"), "bad_id"),
    (lambda b: b["entry"][3]["resource"]["subject"].__setitem__("reference", "urn:uuid:nowhere"), "unresolved_reference"),
    (lambda b: b["entry"][0]["resource"].__setitem__("birthDate", "14/06/1981"), "bad_date"),
    (lambda b: b["entry"][3]["resource"]["period"].__setitem__("start", "[DATE]"), "bad_datetime"),
    (lambda b: b.__setitem__("timestamp", "2025-03-05"), "bad_instant"),
    (lambda b: b["entry"][5]["resource"]["content"][0]["attachment"].__setitem__("data", "[ID]"), "attachment_not_base64"),
    (lambda b: b["entry"][0]["resource"].__setitem__("key_1a2b3c4d", b["entry"][0]["resource"].pop("extension")), "bad_element_name"),
    (lambda b: b["entry"][0]["resource"].__setitem__("gender", "M"), "value_set"),
    (lambda b: b["entry"][3]["resource"].pop("status"), "missing_required"),
    (lambda b: b["entry"][0]["resource"]["name"][0].__setitem__("family", "  "), "empty_string"),
    (lambda b: b["entry"][1]["resource"].__setitem__("resourceType", "Doctor"), "unknown_resource_type"),
])
def test_validator_catches(mutate, code):
    b = copy.deepcopy(bundle())
    mutate(b)
    assert code in {c for c, _ in validate_bundle(b)}


def test_validator_reports_paths_not_values():
    b = copy.deepcopy(bundle())
    b["entry"][0]["resource"]["birthDate"] = "Tejbir"
    out = json.dumps(validate_bundle(b))
    assert "Tejbir" not in out


# ---------------------------------------------------------------- end to end, with the hook the contract writer will call
def _run_with_policy(tmp_path, monkeypatch, b):
    from secretwards.fhir.sanitize import is_bundle
    orig = contract_run.build_mention

    def hooked(doc, units, spans, meds):
        if is_bundle(doc.fields):
            apply_bundle_policy(doc.fields, units, spans)
        return orig(doc, units, spans, meds)

    monkeypatch.setattr(contract_run, "build_mention", hooked)
    inp, out = tmp_path / "in", tmp_path / "out"
    (inp / "fhir").mkdir(parents=True)
    (inp / "fhir" / "bundle_a.json").write_text(json.dumps(b, indent=2), encoding="utf-8")
    assert contract_run.run_contract(inp, out, b"fhir-policy-test") == 0
    raw = next((out / "sanitized" / "fhir").glob("*.json")).read_text(encoding="utf-8")
    return raw, json.loads(raw)


def test_contract_run_with_policy(tmp_path, monkeypatch):
    raw, b = _run_with_policy(tmp_path, monkeypatch, bundle())
    for gone in ("Tiklani", "Tejbir", "9871234560", "ztiklani", "QXH-25-008812", "201301", "Bhimsar", "Gali 4", "Harbans"):
        assert gone not in raw, gone
    assert b["entry"][2]["resource"]["name"] == "Ganga Kinare Seva Niketan"
    assert b["entry"][1]["resource"]["name"][0]["text"] == "Dr. Meenakshi Raghavan"
    pa = b["entry"][0]["resource"]["address"][0]
    assert pa["state"] == "Madhya Pradesh" and pa["district"] == "Fatehganj"
    assert b["meta"]["profile"] == ["https://example.org/fhir/StructureDefinition/DocumentBundle"]
    assert [c for c, _ in validate_bundle(b) if c != "bad_element_name"] == []


# The next one is in Saiteja's files (reported on the PR); non-strict so it does not block anyone.
# fixed: contract/renamer.py no longer treats a plain lowercase schema word such as 'extension' as personal data
def test_extension_element_keeps_its_name(tmp_path, monkeypatch):
    _raw, b = _run_with_policy(tmp_path, monkeypatch, bundle())
    assert "extension" in b["entry"][0]["resource"]
    assert validate_bundle(b) == []


@pytest.mark.xfail(reason="security/leak_gate.py repairs every learned patient-name word, also inside a hospital name the "
                          "FHIR policy keeps")
def test_hospital_sharing_a_word_with_the_patient_is_kept(tmp_path, monkeypatch):
    b = bundle()
    b["entry"][2]["resource"]["name"] = "Tejbir Memorial Seva Niketan"
    _raw, out = _run_with_policy(tmp_path, monkeypatch, b)
    assert out["entry"][2]["resource"]["name"] == "Tejbir Memorial Seva Niketan"
