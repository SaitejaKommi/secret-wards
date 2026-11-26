# Secret Wards

Offline, LLM-free de-identification and record linkage for messy English / Hindi / Hinglish hospital records (DevForge Track 3).
No network, CPU only, deterministic, synthetic data only.

**Status: working core, not finished.** Detection, linkage, privacy layer and leak gate work end to end on synthetic data.
Missing: FHIR R4 export, encryption at rest, audit trail, technical report. Several known bugs are listed below.
Team docs (status, metrics, task lists) live on the `docs` branch: see `FRIEND_TASKS.md` and `PROGRESS.md` there
(`git worktree add docs-wt docs`).

## What it does
1. **Reads** CSV, TSV, JSON, JSONL, TXT, XLSX. Anything unreadable is quarantined (reason code only, no content).
2. **Finds personal data** in table cells and free text: names (any order, initials, s/o d/o w/o, Devanagari, Hinglish), phones, dates,
   ABHA / insurance / MRN ids, e-mails, addresses with landmarks. A medical guard keeps drugs, doses, vitals and lab values intact.
3. **Links records** of the same patient across scripts and hospitals (never on a name alone) and gives each patient a keyed pseudonym.
4. **Protects quasi-identifiers:** per-patient date shift, age / PIN generalization only where a group is too small, rare-diagnosis suppression,
   a self-made linkage attack to measure the remaining risk.
5. **Gates and writes:** every output is re-checked for leaks, then written as CSV / JSON / TXT plus `report.json`.

Flow: `ingest -> normalize -> detect -> name memory -> link -> pseudonymize -> generalize -> render -> leak gate -> export`.

## Setup from a fresh clone (Python 3.11 required)
Windows (PowerShell):
```
git clone https://github.com/SaitejaKommi/secret-wards.git
cd secret-wards
python -m venv .venv          # must be Python 3.11 (check: python --version); if you have the py launcher: py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
```
Linux / macOS:
```
git clone https://github.com/SaitejaKommi/secret-wards.git
cd secret-wards
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```
Offline machine: on a networked machine run `pip download -r requirements.txt -d wheels`, copy `wheels/` over, then
`pip install --no-index --find-links wheels -r requirements.txt`. Versions are pinned to what the reported numbers were measured with.

## Run (same commands on both systems; use `\` instead of `/` in paths on Windows if your shell needs it)
```
python -m secretwards keygen                                   # once; creates ./keys (gitignored, never printed)
python -m synth --split dev --seed 1 --n 150                   # also: --split heldout | blind
python -m secretwards run --in data/synth/dev/in --out out/dev --emit-spans
python -m eval --gold data/synth/dev/gold.json --out out/dev
python -m pytest -q
```
Or in one step: `sh scripts/run_eval.sh dev`.
Real runs: `python -m secretwards run --in INPUT_DIR --out OUT_DIR --config config.example.toml`. Put `keys_dir` in the config to a folder
OUTSIDE the project. The output folder must not overlap the input folder. Always run on the `in/` folder, never on the folder holding `gold.json`.

Outputs in `OUT_DIR`: `deidentified/` (one file per input; XLSX becomes one CSV per sheet), `deidentified.json` (all records with `pseudonym`
and `meta`), `report.json` (counts, quarantine reasons, privacy and risk numbers, leak-gate stats), `manifest.json`, `quarantine/index.json`.

## Measured status (synthetic data only; fresh seeds, 2026-11-26)
| Set | PII recall | PII precision | Medical kept | Link precision | Link recall | Canary leaks |
|---|---|---|---|---|---|---|
| dev | 0.997 | 0.995 | 0.988 | 0.983 | 0.962 | 0/23 |
| heldout names/templates | 0.997 | 0.996 | 0.989 | 1.000 | 0.857 | 0/23 |
| blind names/templates/schemas | 0.995 | 0.977 | 0.992 | 0.996 | 0.597 | 0/23 |

"Medical kept" counts a generalized age as kept when its band contains the true age; exact ages are kept for only 13-42% of records.
These numbers do not predict the hidden set.

## Known problems (open)
- Leak gate can quarantine many records because of one misclassified cell (20 of 1034 on one fresh dev set).
- Run time is quadratic for one large text file (about 15 s for 106 KB; a 4 MB file would hang).
- A failed run leaves partial output behind (not atomic).
- Leaks in hand probes: lowercase or Devanagari unseen names without any cue, phones written "9 8 7 6 5 ..." or "(98765) 01240", "policy no X" without a colon.
- Same-name patients can merge when they share a father's name and birth year but have different phones.
- No FHIR export, no encryption at rest, no audit trail, no technical report.

## Rules this repo follows
No LLMs or large models; no network; no PII in outputs, logs, temp files, errors, tests or docs (synthetic data only); no hardcoding to our own
synthetic names (gazetteer vs held-out and blind pools is tested); fail closed (quarantine instead of guessing). Never commit `keys/`, `*.key`,
`data/`, `out/`, `.venv/`.
