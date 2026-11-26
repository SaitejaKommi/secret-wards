"""A sanitized FHIR Bundle must stay structurally valid: ids, base64 attachments, references that resolve (invented data)."""
import base64
import json
import re

from secretwards.contract.run import run_contract

ID = re.compile(r"^[A-Za-z0-9\-\.]{1,64}$")
UUIDS = ["2ef0a1be-5309-4c41-8c64-c101720fb2df", "b1a84a8e-a712-4b6c-9d03-fb31f247775f", "2ef0a1be-9871-2345-60c4-c101720fb2df"]  # the last one hides the (invented) phone digits 9871234560 inside an id
NOTE = "Patient Zephyrine Quillfeather, phone 9871234560, admitted with viral fever. BP 120/80 mmHg."


def bundle():
    p, e, d = UUIDS
    return {
        "resourceType": "Bundle", "id": "bundle-1", "type": "document",
        "entry": [
            {"fullUrl": f"urn:uuid:{p}", "resource": {
                "resourceType": "Patient", "id": p, "gender": "female", "birthDate": "1990-04-12",
                "name": [{"family": "Quillfeather", "given": ["Zephyrine"]}],
                "telecom": [{"system": "phone", "value": "9871234560"}]}},
            {"fullUrl": f"urn:uuid:{e}", "resource": {
                "resourceType": "Encounter", "id": e, "status": "finished", "class": {"code": "IMP"},
                "subject": {"reference": f"urn:uuid:{p}"}, "period": {"start": "2025-03-02T09:30:00Z", "end": "2025-03-05T11:00:00Z"}}},
            {"fullUrl": f"urn:uuid:{d}", "resource": {
                "resourceType": "DocumentReference", "id": d, "status": "current",
                "subject": {"reference": f"urn:uuid:{p}"},
                "content": [{"attachment": {"contentType": "text/plain", "data": base64.b64encode(NOTE.encode()).decode()}}]}},
        ]}


def refs(node, acc):
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "reference":
                acc.append(v)
            else:
                refs(v, acc)
    elif isinstance(node, list):
        for v in node:
            refs(v, acc)


def test_sanitized_bundle_stays_valid(tmp_path):
    inp, out = tmp_path / "in", tmp_path / "out"
    (inp / "fhir").mkdir(parents=True)
    (inp / "fhir" / "bundle_a.json").write_text(json.dumps(bundle(), indent=2), encoding="utf-8")
    assert run_contract(inp, out, b"fhir-test-secret") == 0
    b = json.loads(next((out / "sanitized" / "fhir").glob("*.json")).read_text(encoding="utf-8"))
    entries = b["entry"]
    # every id is still a legal FHIR id (a UUID is a record key: no "[PHONE]" chunks inside it)
    for e in entries:
        assert ID.match(e["resource"]["id"]), e["resource"]["id"]
    # every reference resolves inside the bundle
    r = []
    refs(b, r)
    urls = {e["fullUrl"] for e in entries}
    assert r and all(x in urls for x in r), r
    # the attachment is still valid base64, decodes to text, and the patient is gone from it
    data = entries[2]["resource"]["content"][0]["attachment"]["data"]
    text = base64.b64decode(data, validate=True).decode("utf-8")
    assert "Quillfeather" not in text and "9871234560" not in text
    assert "viral fever" in text and "120/80 mmHg" in text
    # the phone number (telecom.value) is gone as well, and so is its digit run hidden inside an id
    raw = json.dumps(b)
    assert "9871234560" not in raw and "9871-2345-60" not in raw
    # the same id maps to the same alias everywhere (id, fullUrl, reference) and ids are no longer the originals
    assert entries[0]["fullUrl"] == "urn:uuid:" + entries[0]["resource"]["id"]
    assert entries[0]["resource"]["id"] != UUIDS[0]


def test_aliases_depend_on_the_secret_and_are_stable(tmp_path):
    outs = []
    for i, sec in enumerate((b"secret-one", b"secret-one", b"secret-two")):
        inp, out = tmp_path / f"in{i}", tmp_path / f"out{i}"
        (inp / "fhir").mkdir(parents=True)
        (inp / "fhir" / "bundle_a.json").write_text(json.dumps(bundle(), indent=2), encoding="utf-8")
        assert run_contract(inp, out, sec) == 0
        outs.append(json.loads(next((out / "sanitized" / "fhir").glob("*.json")).read_text(encoding="utf-8"))["entry"][0]["resource"]["id"])
    assert outs[0] == outs[1] != outs[2]


import pytest  # noqa: E402


@pytest.mark.xfail(reason="FHIR step 4 (Jaisheel): HumanName family / given are not name fields yet, so a name that is not in the "
                          "gazetteer survives inside a Bundle. Needs resource awareness: a Practitioner's name stays, a Patient's goes.")
def test_unseen_patient_name_in_humanname_is_removed(tmp_path):
    inp, out = tmp_path / "in", tmp_path / "out"
    (inp / "fhir").mkdir(parents=True)
    (inp / "fhir" / "bundle_a.json").write_text(json.dumps(bundle(), indent=2), encoding="utf-8")
    assert run_contract(inp, out, b"fhir-test-secret") == 0
    raw = next((out / "sanitized" / "fhir").glob("*.json")).read_text(encoding="utf-8")
    assert "Quillfeather" not in raw and "Zephyrine" not in raw
