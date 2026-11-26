"""The organisers' output contract (docs/toolkit/docs/SPEC.md): structure, honesty, determinism, hygiene.
All names, numbers and ids below are made up for these tests."""
import csv
import hashlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from secretwards.contract import run as contract_run
from secretwards.contract.run import run_contract

ROOT = Path(__file__).resolve().parent.parent
SECRET = b"unit-test-secret-do-not-leak"

NOTE_A = ("Patient Name: Pranav Wadekar\r\nAge/Sex: 41 / M\r\nPhone: 98765 01234\r\nAdmitted 12/03/2021, discharged 21/03/2021.\r\n"
          "Diagnosis: Dengue fever. Tab. Dolo 650 BD x 5 days. BP 120/80 mmHg.\r\nReviewed by Dr. Tanmay Phadke.\r\n")
NOTE_B = ("Patient Name: Pranav Wadekar\r\nPhone: +91 98765-01234\r\nAdmitted 02/04/2022 for follow up. Hb 9.8 g/dL.\r\n")


def build_input(root: Path) -> Path:
    h = root / "h1"
    h.mkdir(parents=True)
    (h / "Pranav_Wadekar_9876501234_note.txt").write_bytes(NOTE_A.encode("utf-8"))
    (h / "followup.txt").write_bytes(NOTE_B.encode("utf-16"))
    # table with a ragged row, a diagnosis sitting in an id-typed column, semicolon-free CSV
    rows = [["Reg No", "Patient Name", "Phone", "Age", "Diagnosis"],
            ["UHID5551234", "Pranav Wadekar", "9876501234", "41", "Dengue fever"],
            ["UHID5559999", "Meghna Kunte", "9811100022", "29", "Type 2 diabetes mellitus"],
            ["Type 2 diabetes mellitus", "Revati Ghaisas", "9822200033", "62"],
            ["UHID5557777", "Nitin Sabnis", "9833300044", "55", "Dengue fever", "extra cell"]]
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\r\n").writerows(rows)
    (h / "registry.csv").write_bytes(b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8"))
    (h / "registry (1).csv").write_bytes(b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8"))  # duplicate content
    visits = {"_export_meta": {"hospital": "H1", "exported": "2022-05-01"},
              "visits": [{"patient": {"name": "Pranav Wadekar", "age": 41, "phone": 9876501234},
                          "admitted": "2021-03-12", "note": "BP 120/80 mmHg, Tab. Dolo 650 BD x 5 days"},
                         {"patient": {"name": "Meghna Kunte", "age": 29, "phone": 9811100022},
                          "admitted": "2021-07-02", "note": "Hb 9.8 g/dL"}]}
    (h / "visits.json").write_text(json.dumps(visits), encoding="utf-8")
    lab = {"patient": {"name": "Revati Ghaisas", "phone": "9822200033"}, "panels": [{"test": "Hb", "value": 9.8}, {"test": "WBC", "value": 11200}]}
    (h / "lab_report.json").write_text(json.dumps(lab), encoding="utf-8")
    (h / "bundle.json").write_text(json.dumps({"resourceType": "Bundle", "type": "document", "entry": [
        {"resource": {"resourceType": "Patient", "id": "p1", "name": [{"family": "Joglekar", "given": ["Ishaan"]}], "birthDate": "1980-04-05"}}]}), encoding="utf-8")
    # things that must be quarantined, never copied
    (h / "broken.json").write_text('{"patient": {"name": "Trunc', encoding="utf-8")
    (h / "scan.pdf").write_bytes(b"%PDF-1.4 fake")
    (h / "empty.txt").write_bytes(b"")
    (h / "json_in_csv.csv").write_text(json.dumps({"patient": "Someone Else"}), encoding="utf-8")
    (h / "sheet.xlsx").write_bytes(b"PK\x03\x04 not really")
    return root


@pytest.fixture()
def inp(tmp_path):
    return build_input(tmp_path / "in")


def tree_hash(d: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(d.rglob("*")):
        if p.is_file():
            h.update(p.relative_to(d).as_posix().encode() + b"\0" + p.read_bytes() + b"\0")
    return h.hexdigest()


def run(inp, out, secret=SECRET):
    code = run_contract(inp, out, secret)
    assert code == 0
    return json.loads((out / "report.json").read_text(encoding="utf-8")), [
        json.loads(x) for x in (out / "records.jsonl").read_text(encoding="utf-8").splitlines()]


def all_text(out: Path) -> str:
    parts = []
    for p in sorted(out.rglob("*")):
        parts.append(p.relative_to(out).as_posix())
        if p.is_file():
            parts.append(p.read_bytes().decode("utf-8", errors="ignore"))
    return "\n".join(parts)


def test_report_is_complete_and_honest(inp, tmp_path):
    out = tmp_path / "out"
    rep, lines = run(inp, out)
    files = sorted(p for p in inp.rglob("*") if p.is_file())
    assert rep["schema"] == "raksha-report/1" and len(rep["files"]) == len(files)
    assert {e["input_sha256"] for e in rep["files"]} == {hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    c = rep["counts"]
    written = [p for p in (out / "sanitized").rglob("*") if p.is_file()]
    assert c["files_total"] == len(files) and c["files_sanitized"] == len(written)
    assert c["files_sanitized"] + c["files_quarantined"] == c["files_total"]
    assert c["records_processed"] == len(lines) and c["records_linked"] == sum(1 for x in lines if x["patient"])
    for k in ("identifiers_detected", "records_generalized", "records_suppressed", "records_quarantined"):
        assert isinstance(c[k], int)
    assert "seconds" in rep["timing"] and "peak_rss_mb" in rep["resources"] and rep["entities"]
    for e in rep["files"]:
        if e["status"] == "sanitized":
            assert (out / e["output"]).is_file()
        else:
            assert e["status"] == "quarantined" and e["output"] is None and e["reason"]


def test_broken_and_unsupported_files_are_quarantined_never_copied(inp, tmp_path):
    out = tmp_path / "out"
    rep, _ = run(inp, out)
    reasons = {e["reason"] for e in rep["files"] if e["status"] == "quarantined"}
    assert {"malformed_json", "unsupported_format", "empty_file", "content_mismatch"} <= reasons
    names = " ".join(p.name for p in (out / "sanitized").rglob("*"))
    assert "scan" not in names and "broken" not in names and "sheet" not in names
    # a raw copy of any input file anywhere in the output would be a -5 penalty
    raw = {p.read_bytes() for p in inp.rglob("*") if p.is_file() and p.stat().st_size > 20}
    assert not any(p.read_bytes() in raw for p in out.rglob("*") if p.is_file())


def test_csv_structure_is_preserved(inp, tmp_path):
    out = tmp_path / "out"
    run(inp, out)
    src = list(csv.reader(io.StringIO((inp / "h1" / "registry.csv").read_bytes().decode("utf-8-sig"), newline="")))
    dst = list(csv.reader(io.StringIO((out / "sanitized" / "h1" / "registry.csv").read_bytes().decode("utf-8-sig"), newline="")))
    assert dst[0] == src[0]                                  # header unchanged (it holds no PII)
    assert len(dst) == len(src)                              # no row dropped, none added
    assert [len(r) for r in dst] == [len(r) for r in src]    # ragged lengths kept, no column added
    assert "Wadekar" not in all_text(out) and "9876501234" not in all_text(out)
    assert any("Dengue fever" in r for r in dst[1:])         # medical value kept
    # a diagnosis that sat in the id column must not be treated as an id everywhere (over-quarantine regression)
    assert dst[3][0] == "Type 2 diabetes mellitus"


def test_json_structure_and_types_are_preserved(inp, tmp_path):
    out = tmp_path / "out"
    run(inp, out)
    src = json.loads((inp / "h1" / "visits.json").read_text(encoding="utf-8"))
    dst = json.loads((out / "sanitized" / "h1" / "visits.json").read_text(encoding="utf-8"))

    def shape(n):
        if isinstance(n, dict):
            return {k: shape(v) for k, v in n.items()}
        if isinstance(n, list):
            return [shape(v) for v in n]
        return type(n).__name__

    s_src, s_dst = shape(src), shape(dst)
    assert list(s_dst) == list(s_src)                                  # same keys, same order
    assert isinstance(dst["visits"][0]["patient"]["phone"], int)       # a numeric phone stays a number (surrogate)
    assert dst["visits"][0]["patient"]["phone"] != 9876501234
    assert dst["visits"][0]["note"] == src["visits"][0]["note"]        # medical text untouched
    assert dst["visits"][0]["admitted"] != "2021-03-12"                # dates are shifted


def test_text_is_redacted_in_place_and_doctors_stay(inp, tmp_path):
    out = tmp_path / "out"
    run(inp, out)
    rep = json.loads((out / "report.json").read_text(encoding="utf-8"))
    renamed = next(e for e in rep["files"] if e["status"] == "sanitized" and e["output"].endswith(".txt") and "f_" in e["output"])
    data = (out / renamed["output"]).read_bytes().decode("utf-8")
    assert "\r\n" in data and data.count("\r\n") >= NOTE_A.count("\r\n")      # line structure kept
    for secret in ("Pranav", "Wadekar", "98765 01234", "12/03/2021"):
        assert secret not in data
    for keep in ("Dolo 650 BD x 5 days", "120/80 mmHg", "Dengue fever", "Dr. Tanmay Phadke"):
        assert keep in data, keep


def test_filenames_with_pii_are_renamed_and_declared(inp, tmp_path):
    out = tmp_path / "out"
    rep, _ = run(inp, out)
    assert "Wadekar" not in all_text(out) and "9876501234" not in all_text(out)  # not in any file or file name
    ent = next(e for e in rep["files"] if e["input_sha256"] == hashlib.sha256((inp / "h1" / "Pranav_Wadekar_9876501234_note.txt").read_bytes()).hexdigest())
    assert ent["status"] == "sanitized" and ent["output"] != "sanitized/h1/Pranav_Wadekar_9876501234_note.txt"
    kept = [e["output"] for e in rep["files"] if e["output"] and e["output"].endswith("visits.json")]
    assert kept == ["sanitized/h1/visits.json"]                                    # clean names are NOT renamed


def test_records_jsonl_locators_and_embedded_claims(inp, tmp_path):
    out = tmp_path / "out"
    rep, lines = run(inp, out)
    by_file = {}
    for x in lines:
        by_file.setdefault(x["file"], []).append(x)
        assert (out / x["file"]).is_file() and set(x) >= {"file", "loc", "patient"}
    assert {x["loc"] for x in by_file["sanitized/h1/registry.csv"]} == {"row:0", "row:1", "row:2", "row:3"}
    assert {x["loc"] for x in by_file["sanitized/h1/visits.json"]} == {"/visits/0", "/visits/1"}   # the _export_meta record is not listed
    assert {x["loc"] for x in by_file["sanitized/h1/lab_report.json"]} == {"doc"}                # one patient's report = one record
    assert {x["loc"] for x in by_file["sanitized/h1/bundle.json"]} == {"doc"}
    # a claimed pseudonym must really appear inside that exported record
    claimed = [x for x in lines if x["patient"]]
    assert claimed, "the repeated patient should be linked"
    for x in claimed:
        body = (out / x["file"]).read_bytes().decode("utf-8", errors="ignore")
        assert x["patient"] in body
    assert len({x["patient"] for x in claimed if x["patient"]}) < len(claimed)   # at least one pseudonym is shared across records


def test_secret_never_appears_and_input_is_untouched(inp, tmp_path):
    before = tree_hash(inp)
    out = tmp_path / "out"
    r = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "main.py"), "--input", str(inp), "--output", str(out)],
                       capture_output=True, env={**os.environ, "RAKSHA_SECRET": SECRET.decode()}, cwd=ROOT, timeout=300)
    assert r.returncode == 0, r.stderr.decode("utf-8", "ignore")[-300:]
    assert SECRET not in r.stdout + r.stderr and SECRET.decode() not in all_text(out)
    assert tree_hash(inp) == before
    assert b"Wadekar" not in r.stdout + r.stderr


def test_deterministic_and_keyed(inp, tmp_path):
    a, b, c = tmp_path / "a", tmp_path / "b", tmp_path / "c"
    run(inp, a)
    run(inp, b)
    run(inp, c, b"another-secret")
    digest = lambda d: hashlib.sha256((tree_hash(d / "sanitized") + (d / "records.jsonl").read_text(encoding="utf-8")).encode()).hexdigest()  # noqa: E731
    assert digest(a) == digest(b)          # same secret: byte-identical sanitized/ and records.jsonl
    assert digest(a) != digest(c)          # different secret: pseudonyms and date shifts change


def test_missing_secret_fails_closed(inp, tmp_path):
    out = tmp_path / "out"
    env = {k: v for k, v in os.environ.items() if k != "RAKSHA_SECRET"}
    r = subprocess.run([sys.executable, str(ROOT / "main.py"), "--input", str(inp), "--output", str(out)], capture_output=True, env=env, cwd=ROOT, timeout=120)
    assert r.returncode != 0 and b"RAKSHA_SECRET" in r.stderr
    assert not (out / "sanitized").exists() and not (out / "report.json").exists()


def test_fatal_error_removes_partial_output_and_leaks_no_message(inp, tmp_path, monkeypatch, capsys):
    out = tmp_path / "out"

    def boom(*a, **k):
        raise ValueError("Pranav Wadekar 9876501234")

    monkeypatch.setattr(contract_run, "_sanitize", boom)
    assert run_contract(inp, out, SECRET) == 1
    err = capsys.readouterr()
    assert "ValueError" in err.err and "Wadekar" not in err.out + err.err
    assert not (out / "sanitized").exists() and not (out / "report.json").exists() and not (out / "records.jsonl").exists()


def test_plain_schema_words_are_not_renamed():
    """FHIR's "extension" is on the address detector's street-type list; as a key it must not be treated as personal data."""
    from secretwards.contract.renamer import Renamer
    from secretwards.detect import default_detectors
    from secretwards.security.keys import keys_from_secret

    rn = Renamer(keys_from_secret(b"k"), default_detectors())
    for k in ("extension", "telecom", "status", "contact", "address", "identifier"):
        assert rn.key(k) == k, k
    assert rn.key("9871234560") != "9871234560"  # a phone number as a key is still renamed
