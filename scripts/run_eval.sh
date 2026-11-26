#!/bin/sh
# Generate (if missing), de-identify and score one synthetic split.
# usage: sh scripts/run_eval.sh dev|heldout|blind [seed] [patients]
# Uses $PYTHON if set, else "python" (activate your venv first).
PY=${PYTHON:-python}
S=${1:-dev}
SEED=${2:-1}
N=${3:-150}
[ -d "data/synth/$S/in" ] || $PY -X utf8 -m synth --split "$S" --seed "$SEED" --n "$N"
$PY -X utf8 -m secretwards run --in "data/synth/$S/in" --out "out/$S" --emit-spans
$PY -X utf8 -m eval --gold "data/synth/$S/gold.json" --out "out/$S"
