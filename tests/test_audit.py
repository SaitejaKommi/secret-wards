"""The audit trail: counts only, chained with a keyed MAC, verifiable with the secret, deterministic, inside report.json (invented values)."""
import copy
import json

import pytest

from secretwards.contract.audit import AuditError, AuditTrail, verify
from secretwards.contract.run import run_contract
from secretwards.security.keys import keys_from_secret

KEYS = keys_from_secret(b"audit-secret")


def trail():
    t = AuditTrail(KEYS)
    t.record("ingest", files=3, quarantined=1)
    t.record("detect", records=10, spans=42)
    t.record("write", files_sanitized=2)
    return t.export()


def test_chain_verifies_with_the_secret_and_not_with_another():
    a = trail()
    assert verify(a, KEYS)
    assert not verify(a, keys_from_secret(b"another-secret"))


@pytest.mark.parametrize("tamper", ["count", "stage", "drop", "reorder", "head", "extra"])
def test_any_change_breaks_the_chain(tamper):
    a = copy.deepcopy(trail())
    if tamper == "count":
        a["events"][1]["counts"]["records"] = 11
    elif tamper == "stage":
        a["events"][0]["stage"] = "other"
    elif tamper == "drop":
        del a["events"][1]
    elif tamper == "reorder":
        a["events"][0], a["events"][1] = a["events"][1], a["events"][0]
    elif tamper == "head":
        a["head"] = "0" * 32
    elif tamper == "extra":
        a["events"].append({"seq": 3, "stage": "write", "counts": {}, "mac": "0" * 32})
    assert not verify(a, KEYS)


def test_nothing_but_counts_is_accepted_and_errors_never_echo_values():
    t = AuditTrail(KEYS)
    for bad in ("Ravi Kumar 9876501234", 3.5, None, True, [1]):
        with pytest.raises(AuditError) as e:
            t.record("detect", records=bad)
        assert "Ravi" not in str(e.value) and "9876501234" not in str(e.value)
    for bad_name in ("Name With Spaces", "9starts_with_digit", "has-dash", "x" * 60):
        with pytest.raises(AuditError):
            t.record("detect", **{bad_name: 1})
        with pytest.raises(AuditError):
            t.record(bad_name, records=1)


def make_input(inp):
    inp.mkdir(parents=True)
    (inp / "a.txt").write_text("Patient: Zephyrine Quillfeather, phone 9871234560. BP 120/80 mmHg.\n", encoding="utf-8", newline="")
    (inp / "r.csv").write_text("Pt Nm,Mobile\nZephyrine Quillfeather,9871234560\n", encoding="utf-8", newline="")
    (inp / "broken.json").write_text('{"name": "Zephyrine Quillfeather", ', encoding="utf-8")


def test_report_carries_a_verifiable_pii_free_trail(tmp_path):
    make_input(tmp_path / "in")
    assert run_contract(tmp_path / "in", tmp_path / "out", b"audit-secret") == 0
    raw = (tmp_path / "out" / "report.json").read_text(encoding="utf-8")
    rep = json.loads(raw)
    a = rep["audit"]
    assert [e["stage"] for e in a["events"]] == ["ingest", "detect", "link", "privacy", "gate", "write"]
    assert verify(a, KEYS)
    ingest = a["events"][0]["counts"]
    assert ingest["files"] == 3 and ingest["quarantined"] == 1 and ingest["quarantine_malformed_json"] == 1
    # only integers anywhere in the counts, and none of the planted values anywhere in the report
    assert all(isinstance(v, int) for e in a["events"] for v in e["counts"].values())
    assert "Quillfeather" not in raw and "9871234560" not in raw and "audit-secret" not in raw


def test_trail_is_deterministic_and_secret_dependent(tmp_path):
    heads = []
    for i, secret in enumerate((b"audit-secret", b"audit-secret", b"other-secret")):
        make_input(tmp_path / f"in{i}")
        assert run_contract(tmp_path / f"in{i}", tmp_path / f"out{i}", secret) == 0
        heads.append(json.loads((tmp_path / f"out{i}" / "report.json").read_text(encoding="utf-8"))["audit"])
    assert heads[0] == heads[1]            # same input and secret: identical events and MACs (no timestamps)
    assert heads[0]["head"] != heads[2]["head"] and not verify(heads[2], KEYS)
