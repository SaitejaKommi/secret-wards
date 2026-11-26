import hashlib
import json
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

import pytest

from eval.score import score
from secretwards.config import Config
from secretwards.pipeline import run
from secretwards.security import safe_log
from synth.generate import generate

ROOT = Path(__file__).resolve().parent.parent


def _all_text(out: Path) -> str:
    parts = []
    for p in sorted(out.rglob("*")):
        parts.append(p.relative_to(out).as_posix())
        if p.is_file():
            parts.append(p.read_bytes().decode("utf-8", errors="ignore"))
    return "\n".join(parts)


def _digits(s: str) -> str:
    return "".join(str(unicodedata.decimal(c)) for c in unicodedata.normalize("NFKC", s) if unicodedata.decimal(c, None) is not None)


def test_expected_files_are_quarantined_and_nothing_else(dataset, run_out, keys):
    from secretwards.security.keys import hmac_hex

    out, report = run_out
    root, gold = dataset
    q = json.loads((out / "quarantine" / "index.json").read_text(encoding="utf-8"))
    refs = {x["ref"] for x in q if x["scope"] == "file"}
    exp = {hmac_hex(keys.docid, "file", r, n=12) for r in gold["quarantine_expected"]}
    assert exp <= refs and refs == exp
    # the quarantine folder holds only the index: no raw copies
    assert [p.name for p in (out / "quarantine").iterdir()] == ["index.json"]


def test_no_canary_or_gold_pii_anywhere_in_outputs(dataset, run_out, keys):
    out, _ = run_out
    root, gold = dataset
    big = unicodedata.normalize("NFKC", _all_text(out)).casefold()
    bigd = _digits(big)
    for c in gold["canaries"]:
        if c["type"] == "PHONE":
            assert _digits(c["text"]) not in bigd, "canary phone leaked"
        else:
            assert c["text"].casefold() not in big, "canary leaked"
    # every gold phone / email / id value of every patient
    leaks = 0
    total = 0
    for rec in gold["records"]:
        for g in rec["pii"]:
            if g["type"] in ("PHONE",):
                total += 1
                leaks += _digits(g["text"]) in bigd and len(_digits(g["text"])) >= 10
            elif g["type"] in ("EMAIL", "ABHA", "INSURANCE", "MRN"):
                total += 1
                leaks += g["text"].casefold() in big
    assert total > 100
    assert leaks / total < 0.005, f"{leaks}/{total} structured identifiers leaked"


def test_scorer_thresholds_on_heldout(dataset, run_out, cfg):
    out, _ = run_out
    root, _ = dataset
    r = score(root / "gold.json", out, cfg.keys_dir)
    assert r["canary_leaks"] == 0
    assert r["recall_overall"] > 0.97
    assert r["precision_overall"] > 0.95
    assert r["medical_retention_overall"] > 0.97
    assert r["link_precision"] > 0.99
    assert r["twin_pairs_merged"] <= 1
    assert r["leak_rate_overall"] < 0.01


def test_report_has_counts_only(run_out):
    out, report = run_out
    txt = (out / "report.json").read_text(encoding="utf-8")
    assert "files" in report and "privacy" in report and "leak_gate" in report
    assert not re.search(r"\d{10}", txt)  # no phone-like numbers
    assert "@" not in txt


def test_every_output_record_has_a_pseudonym_and_no_raw_header_names(run_out, dataset):
    out, _ = run_out
    recs = json.loads((out / "deidentified.json").read_text(encoding="utf-8"))
    assert recs and all(r["pseudonym"].startswith("PT-") for r in recs)
    root, gold = dataset
    # header / key canaries are replaced by keyed hashes
    for r in recs:
        for k in r["fields"]:
            assert not re.search(r"(?i)referred by|alt_contact|\d{8}", k)


def test_outputs_are_valid_csv_and_json(run_out):
    import csv

    out, _ = run_out
    n = 0
    for p in (out / "deidentified").iterdir():
        if p.suffix == ".json":
            json.loads(p.read_text(encoding="utf-8"))
            n += 1
        elif p.suffix == ".csv":
            rows = list(csv.reader(p.read_text(encoding="utf-8").splitlines()))
            assert rows and rows[0][0] == "pseudonym"
            n += 1
    assert n > 5


def test_determinism_across_processes_and_hash_seeds(tmp_path, keys_dir):
    """Run the real CLI twice in separate processes with different PYTHONHASHSEED; outputs must be byte-identical."""
    data = generate(tmp_path / "d", "dev", seed=4, n_patients=40)
    cfgp = tmp_path / "cfg.json"
    cfgp.write_text(json.dumps({"keys_dir": str(keys_dir)}), encoding="utf-8")
    digests = []
    for i, seed in enumerate(("1", "12345")):
        out = tmp_path / f"o{i}"
        env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONIOENCODING": "utf-8"}
        r = subprocess.run([sys.executable, "-X", "utf8", "-m", "secretwards", "run", "--in", str(data / "in"), "--out", str(out),
                            "--config", str(cfgp)], capture_output=True, env=env, cwd=ROOT, timeout=600)
        assert r.returncode == 0, r.stderr.decode("utf-8", "ignore")[-500:]
        h = hashlib.sha256()
        for p in sorted(out.rglob("*")):
            if p.is_file():
                h.update(p.relative_to(out).as_posix().encode())
                h.update(p.read_bytes())
        digests.append(h.hexdigest())
    assert digests[0] == digests[1]


def test_logs_and_errors_carry_no_values(tmp_path, keys, cfg, capsys):
    """A detector that crashes with PII in its message must quarantine the record and leak nothing."""
    data = generate(tmp_path / "d", "dev", seed=2, n_patients=15)
    gold = json.loads((data / "gold.json").read_text(encoding="utf-8"))
    secret = next(g["text"] for r in gold["records"] for g in r["pii"] if g["type"] == "NAME" and len(g["text"]) > 6)

    class Exploding:
        name = "boom"

        def detect(self, unit):
            if secret in unit.original:
                raise ValueError(f"cannot parse {secret}")
            return []

    import io

    buf = io.StringIO()
    safe_log.set_stream(buf)
    try:
        out = tmp_path / "o"
        run(data / "in", out, cfg, keys, detectors=[Exploding()])
    finally:
        safe_log.set_stream(None)
    logs = buf.getvalue() + capsys.readouterr().out + capsys.readouterr().err
    assert secret not in logs and "ValueError" in logs
    assert secret not in _all_text(out)
    rep = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert rep["records"]["quarantined"] >= 1


def test_run_makes_no_network_calls(tmp_path, keys, cfg):
    data = generate(tmp_path / "d", "dev", seed=6, n_patients=10)
    run(data / "in", tmp_path / "o", cfg, keys)  # conftest's autouse fixture turns any socket use into a failure
    import sys as _s

    assert not any(m in _s.modules for m in ("requests", "urllib3", "http.client", "aiohttp"))


def test_unreadable_inputs_are_quarantined_not_passed_through(tmp_path, keys, cfg):
    d = tmp_path / "in" / "h"
    d.mkdir(parents=True)
    (d / "a.csv").write_bytes(b"\x00\x01\x02binary")
    (d / "b.json").write_text('{"x": ', encoding="utf-8")
    (d / "c.xlsx").write_bytes(b"not a zip")
    (d / "d.txt").write_bytes(b"")
    (d / "e.pdf").write_bytes(b"%PDF")
    (d / "ok.txt").write_text("Patient Name: Tushar Zaidi\nPhone: 9876543210\n", encoding="utf-8")
    out = tmp_path / "out"
    rep = run(tmp_path / "in", out, cfg, keys)
    assert rep["files"]["quarantined"] == 5 and rep["records"]["output"] == 1
    assert "Zaidi" not in _all_text(out) and "9876543210" not in _all_text(out)


def test_crlf_and_utf16_inputs_are_handled(tmp_path, keys, cfg):
    d = tmp_path / "in"
    d.mkdir()
    (d / "a.txt").write_bytes("Patient Name: Tushar Zaidi\r\nPhone: 9876543210\r\n".encode("utf-8"))
    (d / "b.txt").write_bytes("Patient Name: Tushar Zaidi\r\nPhone: 9876543210\r\n".encode("utf-16"))
    out = tmp_path / "out"
    rep = run(d, out, cfg, keys)
    assert rep["records"]["output"] == 2
    t = _all_text(out)
    assert "Zaidi" not in t and "9876543210" not in t


def test_changing_the_key_changes_pseudonyms_not_structure(tmp_path, keys, cfg):
    from secretwards.security.keys import generate_keys, load_keys

    data = generate(tmp_path / "d", "dev", seed=8, n_patients=12)
    r1 = run(data / "in", tmp_path / "o1", cfg, keys)
    generate_keys(tmp_path / "k2")
    k2 = load_keys(tmp_path / "k2")
    r2 = run(data / "in", tmp_path / "o2", cfg, k2)
    assert r1["patients"]["pseudonyms"] == r2["patients"]["pseudonyms"]
    a = json.loads((tmp_path / "o1" / "deidentified.json").read_text(encoding="utf-8"))
    b = json.loads((tmp_path / "o2" / "deidentified.json").read_text(encoding="utf-8"))
    assert {x["pseudonym"] for x in a}.isdisjoint({x["pseudonym"] for x in b})
