"""MEASUREMENT AID ONLY (temporary, until the contract adapter P0 lands).

Mirrors our current per-file outputs (out/<run>/deidentified + manifest.json) into <dest>/sanitized/<input rel path>
so the organisers' check_dev.py can read them. It does NOT make our output contract-valid (no SHA-256 report,
no records.jsonl, no pseudonym inside records). Caveats: file names in the mirror are the INPUT names, so check_dev
shows 100% 'filename' leaks (an artefact); records our leak gate quarantined are missing, so medical-kept looks low.

usage:  python scripts/adapt_for_checkdev.py <kit>/dev/input out/ours out/ours_adapted
        python <kit>/check_dev.py --output out/ours_adapted
"""
import json
import shutil
import sys
from pathlib import Path

inp, ours, dest = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
shutil.rmtree(dest, ignore_errors=True)
(dest / "sanitized").mkdir(parents=True)
rels = sorted(p.relative_to(inp).as_posix() for p in inp.rglob("*") if p.is_file())  # same order our ingest uses
manifest = json.loads((ours / "manifest.json").read_text(encoding="utf-8"))
n = 0
for m in manifest:
    if len(m["outputs"]) != 1:
        continue
    target = dest / "sanitized" / rels[m["input_ordinal"]]
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ours / "deidentified" / m["outputs"][0], target)
    n += 1
print(f"mirrored {n} of {len(rels)} files into {dest}/sanitized")
