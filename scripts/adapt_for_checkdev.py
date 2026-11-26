"""MEASUREMENT AID ONLY (temporary, until the contract adapter P0 lands).

Mirrors our current per-file outputs (out/<run>/deidentified + manifest.json) into <dest>/sanitized/<path>
so the organisers' check_dev.py can read them. Paths go through `detect.hidden.sanitize_path` (a component is
renamed only if it holds PII), and a minimal report.json maps each input SHA-256 to its output path, the way the
contract declares renames. It does NOT make our output contract-valid (no counts, no records.jsonl, no pseudonym
inside records). Caveat: records our leak gate quarantined are missing, so medical-kept looks low.

usage:  python scripts/adapt_for_checkdev.py <kit>/dev/input out/ours out/ours_adapted [keys_dir]
        python <kit>/check_dev.py --output out/ours_adapted
"""
import hashlib
import json
import shutil
import sys
from pathlib import Path

from secretwards.detect.hidden import sanitize_path
from secretwards.security.keys import load_keys

inp, ours, dest = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
key = load_keys(Path(sys.argv[4]) if len(sys.argv) > 4 else Path("keys")).docid
shutil.rmtree(dest, ignore_errors=True)
(dest / "sanitized").mkdir(parents=True)
rels = sorted(p.relative_to(inp).as_posix() for p in inp.rglob("*") if p.is_file())  # same order our ingest uses
manifest = json.loads((ours / "manifest.json").read_text(encoding="utf-8"))
files = []
n = renamed = 0
mirrored = set()
for m in manifest:
    if len(m["outputs"]) != 1:
        continue
    rel = rels[m["input_ordinal"]]
    mirrored.add(rel)
    out_rel = sanitize_path(rel, key)
    renamed += out_rel != rel
    target = dest / "sanitized" / out_rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ours / "deidentified" / m["outputs"][0], target)
    files.append({"input_sha256": hashlib.sha256((inp / rel).read_bytes()).hexdigest(), "output": "sanitized/" + out_rel,
                  "status": "sanitized"})
    n += 1
# every input file is declared (the contract lists all of them); a file we could not mirror (all its records were
# quarantined by our gate) still gets its sanitized name, otherwise check_dev reads the INPUT name as a filename leak
for rel in rels:
    if rel not in mirrored:
        out_rel = sanitize_path(rel, key)
        files.append({"input_sha256": hashlib.sha256((inp / rel).read_bytes()).hexdigest(), "output": "sanitized/" + out_rel,
                      "status": "quarantined"})
(dest / "report.json").write_text(json.dumps({"schema": "measurement-only", "files": files}, indent=1), encoding="utf-8")
print(f"mirrored {n} of {len(rels)} files into {dest}/sanitized ({renamed} renamed for PII in the path)")
