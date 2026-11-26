"""Command line of the contract path: python main.py --input DIR --output DIR  (secret in RAKSHA_SECRET)."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Secret Wards: contract run")
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    a = ap.parse_args(argv)
    secret = os.environ.get("RAKSHA_SECRET", "").encode("utf-8")
    if not secret:
        print("error: RAKSHA_SECRET is not set", file=sys.stderr)
        return 2
    inp, out = Path(a.input).resolve(), Path(a.output).resolve()
    if not inp.is_dir():
        print("error: input directory not found", file=sys.stderr)
        return 2
    if out == inp or inp in out.parents or out in inp.parents:
        print("error: output directory must not overlap the input directory", file=sys.stderr)
        return 2
    from .run import run_contract

    return run_contract(inp, out, secret)
