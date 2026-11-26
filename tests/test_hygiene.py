"""Channel hygiene (kit: 15% of integrity): run the real `main.py` as the organisers do and look in all seven side channels.

report.json, records.jsonl, logs/, other output files, output file names, stdout/stderr, TMPDIR/HOME.
Every value below is invented. The canaries sit in contents, file names, JSON keys, headers, a corrupted file and a
file that cannot be parsed, so the error paths are exercised too.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SECRET = "hygiene-test-secret-value-0001"
CANARIES = ["Zephyrine Quillfeather", "Quillfeather", "Zephyrine", "9871234560", "QF-7781234", "zq.canary@example.invalid",
            "Brixtonville"]


def build_input(root: Path) -> None:
    (root / "opd").mkdir(parents=True)
    (root / "lab").mkdir()
    (root / "notes").mkdir()
    (root / "opd" / "zephyrine_quillfeather_visits.csv").write_text(
        "Patient Name,Phone,Age,Diagnosis,Notes\n"
        "Zephyrine Quillfeather,9871234560,34,Viral fever,Patient Zephyrine Quillfeather reachable at zq.canary@example.invalid\n"
        "Rohan Vestergaard,9812345678,41,Hypertension,BP 150/95 mmHg Tab Telmisartan 40 mg 1-0-0\n", encoding="utf-8")
    (root / "lab" / "report_01.json").write_text(json.dumps(
        {"patient_name": "Zephyrine Quillfeather", "mrn": "QF-7781234", "tests": [{"name": "Hb", "value": 11.2, "unit": "g/dL"}],
         "address": "Brixtonville, MG Road", "Zephyrine_Quillfeather_note": "follow up", "9871234560": "key that is itself a phone"}, indent=2), encoding="utf-8")
    (root / "notes" / "visit.txt").write_text(
        "Patient: Zephyrine Quillfeather\nPhone 9871234560. Address: Brixtonville, MG Road.\nBP 130/80 mmHg. Tab Metformin 500 mg 1-0-1.\n", encoding="utf-8")
    # cannot be parsed: the error path must not echo the content
    (root / "lab" / "broken.json").write_text('{"patient_name": "Zephyrine Quillfeather", "phone": 9871234560, ', encoding="utf-8")
    (root / "lab" / "binary.csv").write_bytes(b"\xff\xfe\x00Zephyrine Quillfeather\x00\x00,9871234560\n")


def scan_tree(root: Path):
    """Yield (relative path, bytes) for every file and every file name under root."""
    for p in sorted(root.rglob("*")):
        yield str(p.relative_to(root)), (p.read_bytes() if p.is_file() else b"")


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    base = tmp_path_factory.mktemp("hyg")
    inp, out, tmp, home = base / "in", base / "out", base / "tmp", base / "home"
    tmp.mkdir()
    home.mkdir()
    build_input(inp)
    env = {k: v for k, v in os.environ.items() if k not in ("RAKSHA_SECRET",)}
    env.update(RAKSHA_SECRET=SECRET, TMPDIR=str(tmp), TEMP=str(tmp), TMP=str(tmp), HOME=str(home), USERPROFILE=str(home),
               PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    p = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "main.py"), "--input", str(inp), "--output", str(out)],
                       capture_output=True, env=env, timeout=300)
    return dict(proc=p, inp=inp, out=out, tmp=tmp, home=home)


def test_run_succeeds_and_writes_the_contract_files(run):
    assert run["proc"].returncode == 0, run["proc"].stderr.decode("utf-8", "replace")[-400:]
    assert (run["out"] / "report.json").is_file() and (run["out"] / "records.jsonl").is_file()
    assert (run["out"] / "sanitized").is_dir()


def test_no_canary_in_stdout_or_stderr(run):
    blob = run["proc"].stdout + run["proc"].stderr
    for c in CANARIES + [SECRET]:
        assert c.encode() not in blob, f"{c!r} found in stdout/stderr"


def test_no_canary_in_any_output_file_or_file_name(run):
    for rel, data in scan_tree(run["out"]):
        for c in CANARIES + [SECRET]:
            assert c.lower() not in rel.lower(), f"{c!r} in output file name {rel}"
            assert c.lower().encode() not in data.lower(), f"{c!r} in output file {rel}"


def test_report_and_records_hold_no_canary_and_no_secret(run):
    for name in ("report.json", "records.jsonl"):
        raw = (run["out"] / name).read_text(encoding="utf-8")
        for c in CANARIES + [SECRET]:
            assert c.lower() not in raw.lower(), f"{c!r} in {name}"
    json.loads((run["out"] / "report.json").read_text(encoding="utf-8"))


def test_no_logs_dir_and_no_extra_files(run):
    top = sorted(p.name for p in run["out"].iterdir())
    assert top == ["records.jsonl", "report.json", "sanitized"], top


def test_tmpdir_and_home_stay_empty(run):
    assert list(run["tmp"].rglob("*")) == [], "temp files left behind"
    assert list(run["home"].rglob("*")) == [], "files written under HOME"


def test_input_is_not_modified(run):
    # every input file is still exactly what we wrote (an input modified costs -5)
    assert (run["inp"] / "notes" / "visit.txt").read_text(encoding="utf-8").startswith("Patient: Zephyrine Quillfeather")
    assert "Quillfeather" in (run["inp"] / "lab" / "report_01.json").read_text(encoding="utf-8")


def test_unparseable_files_are_quarantined_not_copied(run):
    """Fail closed: a file we cannot process safely is listed as quarantined (with a reason) and nothing of it is written."""
    rep = json.loads((run["out"] / "report.json").read_text(encoding="utf-8"))
    bad = [f for f in rep["files"] if f["status"] == "quarantined"]
    assert sorted(f["reason"] for f in bad) == ["malformed_json", "undecodable_text"]
    assert all(f["output"] is None for f in bad)
    assert rep["counts"]["files_total"] == 5 == len(rep["files"])  # every input accounted for, none dropped silently
    written = sorted(p.name for p in (run["out"] / "sanitized").rglob("*") if p.is_file())
    assert len(written) == 3 and "broken.json" not in written and "binary.csv" not in written


def test_secret_never_written_anywhere_under_the_run(run):
    for root in (run["out"], run["tmp"], run["home"]):
        for rel, data in scan_tree(root):
            assert SECRET.encode() not in data, rel
            assert SECRET not in rel


def test_wrong_secret_is_not_a_success(tmp_path):
    """A missing secret must fail loudly (exit non-zero) and write no output: a false success costs -10."""
    inp, out = tmp_path / "in", tmp_path / "out"
    build_input(inp)
    env = {k: v for k, v in os.environ.items() if k != "RAKSHA_SECRET"}
    p = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "main.py"), "--input", str(inp), "--output", str(out)],
                       capture_output=True, env=env, timeout=120)
    assert p.returncode != 0
    assert b"Quillfeather" not in p.stdout + p.stderr and b"9871234560" not in p.stdout + p.stderr
    assert not (out / "report.json").exists()
