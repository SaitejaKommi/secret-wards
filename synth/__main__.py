import argparse

from .generate import generate

ap = argparse.ArgumentParser(prog="python -m synth")
ap.add_argument("--out", default="data/synth")
ap.add_argument("--split", choices=["dev", "heldout", "blind"], default="dev")
ap.add_argument("--seed", type=int, default=1)
ap.add_argument("--n", type=int, default=300, help="number of patients")
a = ap.parse_args()
root = generate(a.out, a.split, a.seed, a.n)
print(f"wrote {root}")
