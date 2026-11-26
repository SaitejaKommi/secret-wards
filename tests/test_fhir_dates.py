"""Every date in a FHIR Bundle moves by the same per-patient offset, including meta.lastUpdated (invented values).

If lastUpdated stays real while the other dates are shifted, anyone who knows one true visit date can compare it with it and recover the shift.
"""
import datetime as dt
import json

import pytest

from secretwards.contract.run import run_contract
from secretwards.fhir.validate import validate_bundle

UUIDS = ["2ef0a1be-5309-4c41-8c64-c101720fb2df", "b1a84a8e-a712-4b6c-9d03-fb31f247775f"]


def bundle(day: str):
    p, e = UUIDS
    return {
        "resourceType": "Bundle", "id": "b1", "type": "document", "meta": {"lastUpdated": f"{day}T10:30:00.000Z"}, "timestamp": f"{day}T10:30:00Z",
        "entry": [
            {"fullUrl": f"urn:uuid:{p}", "resource": {"resourceType": "Patient", "id": p, "gender": "female", "birthDate": "1971-03-12",
                                                     "meta": {"lastUpdated": f"{day}T10:30:00.000Z"}, "name": [{"family": "Quillfeather", "given": ["Zephyrine"]}]}},
            {"fullUrl": f"urn:uuid:{e}", "resource": {"resourceType": "Encounter", "id": e, "status": "finished", "class": {"code": "IMP"},
                                                     "subject": {"reference": f"urn:uuid:{p}"}, "meta": {"lastUpdated": f"{day}T10:30:00.000Z"},
                                                     "period": {"start": f"{day}T09:30:00Z", "end": "2025-03-12T11:00:00Z"}}}]}


@pytest.mark.parametrize("day", ["2025-03-02", "2024-11-30", "2026-07-15"])
def test_last_updated_shifts_with_the_visit_dates(tmp_path, day):
    inp, out = tmp_path / "in", tmp_path / "out"
    (inp / "fhir").mkdir(parents=True)
    (inp / "fhir" / "b.json").write_text(json.dumps(bundle(day), indent=2), encoding="utf-8")
    assert run_contract(inp, out, b"fhir-date-secret") == 0
    b = json.loads(next((out / "sanitized" / "fhir").glob("*.json")).read_text(encoding="utf-8"))
    last = b["meta"]["lastUpdated"]
    start = b["entry"][1]["resource"]["period"]["start"]
    assert day not in last, last                        # no longer the real day
    assert last[:10] == start[:10]                      # still the same day as the visit it describes: one offset for everything
    assert b["timestamp"][:10] == start[:10]
    assert b["entry"][0]["resource"]["meta"]["lastUpdated"][:10] == start[:10]
    assert dt.datetime.fromisoformat(last.replace("Z", "+00:00"))  # still a valid instant
    assert validate_bundle(b) == []
