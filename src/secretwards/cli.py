"""secretwards run --in DIR --out DIR --config FILE   |   secretwards keygen [--keys-dir DIR]"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import load_config
from .security.keys import KeysMissing, generate_keys, load_keys


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="secretwards", description="Offline de-identification and record linkage")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="de-identify a directory of hospital files")
    r.add_argument("--in", dest="inp", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--config", default=None)
    r.add_argument("--emit-spans", action="store_true", help="write eval_spans.json (offsets/types only)")
    k = sub.add_parser("keygen", help="create local key files (never printed)")
    k.add_argument("--keys-dir", default="keys")
    a = ap.parse_args(argv)
    if a.cmd == "keygen":
        made = generate_keys(a.keys_dir)
        print(f"keys ready in {a.keys_dir} (created: {', '.join(made) or 'none, already present'})")
        return 0
    cfg = load_config(a.config)
    if a.emit_spans:
        cfg.emit_spans = True
    try:
        keys = load_keys(cfg.keys_dir)
    except KeysMissing:
        print("error: key files missing; run `secretwards keygen` first", file=sys.stderr)
        return 2
    from .pipeline import run
    inp = Path(a.inp).resolve()
    out = Path(a.out).resolve()
    if not inp.is_dir():
        print("error: input directory not found", file=sys.stderr)
        return 2
    if out == inp or inp in out.parents or out in inp.parents:
        print("error: output directory must not overlap the input directory", file=sys.stderr)
        return 2
    try:
        rep = run(inp, out, cfg, keys)
    except Exception as e:  # tracebacks and messages can echo record values: print the type only
        print(f"error: run failed ({type(e).__name__}); no further detail is printed on purpose", file=sys.stderr)
        return 1
    print(f"records out: {rep['records']['output']}/{rep['records']['total']}, "
          f"files quarantined: {rep['files']['quarantined']}, patients: {rep['patients']['pseudonyms']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
