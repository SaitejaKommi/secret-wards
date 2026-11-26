# Secret Wards

Offline, LLM-free de-identification and record linkage for messy English / Hindi / Hinglish hospital records (DevForge Track 3).
No network, CPU only, deterministic, synthetic data only.

**Status: working end to end on the organisers' contract; not finished.** `python main.py --input IN --output OUT` (with `RAKSHA_SECRET` set)
writes `sanitized/`, `records.jsonl` and `report.json`, and the kit's `validate_output.py` prints CONTRACT OK. On the kit's practice data the
kit's own self-check reports 0 of 3,230 personal values still visible, 0 canaries, 99.2% of medical values kept, linking precision 1.00 /
recall 0.91. We tuned against that practice data, so treat those numbers as an upper bound; see "Known problems".
Team docs (status, metrics, task lists, the official kit analysis) are in the [`docs/`](docs) folder: start with
[`docs/TOOLKIT.md`](docs/TOOLKIT.md), then [`docs/FRIEND_TASKS.md`](docs/FRIEND_TASKS.md) and [`docs/PROGRESS.md`](docs/PROGRESS.md).

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

## Official contract run (what the organisers execute)
```
RAKSHA_SECRET=practice python main.py --input INPUT_DIR --output OUT_DIR      # PowerShell: $env:RAKSHA_SECRET="practice"
```
Writes `OUT_DIR/sanitized/` (same paths and formats as the input; names holding personal data are renamed and declared), `report.json` (written last) and `records.jsonl`.
Exit 0 only for a complete release. `RAKSHA_SECRET` keys every pseudonym and date shift and is never written. Details: [`docs/TOOLKIT.md`](docs/TOOLKIT.md).

## Our own development run (same commands on both systems; use `\` instead of `/` in paths on Windows if your shell needs it)
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

Outputs in `OUT_DIR` (contract run): `sanitized/` (the input tree mirrored: same relative paths unless a file name itself holds personal data,
same formats, delimiters, headers, row counts and JSON key order; UTF-8), `records.jsonl` (one line per record: `file`, `loc`, and a `PSN-xxxxxxxx`
pseudonym only when that pseudonym really appears inside the record) and `report.json` (SHA-256 of every input file, what was written or quarantined
and why, counts, timing, memory; written last). A file we cannot process safely is quarantined as a whole with a reason code; it is never copied raw.
The older development run (`python -m secretwards run`) writes a different layout (`deidentified/`, `manifest.json`).

## Measured status
**Official practice data** (200 files, `RAKSHA_SECRET=practice`, the kit's `check_dev.py`; 2026-11-26, after PR #13):

| Measure | Value |
|---|---|
| personal values still visible | 0 of 3,230 (Latin 0.0%, Devanagari 0.0%, Hinglish 0.0%; file names, metadata, base64, keys, headers all 0.0%) |
| planted canaries found | 0 of 4 |
| medical values kept | 4,816 of 4,855 (99.2%) |
| patient linking | precision 1.00, recall 0.91, F0.5 0.98, 0 wrong merges |
| FHIR (our own structural check) | 351 of 351 ids valid, 9 of 9 attachments valid base64, 459 of 459 references resolve |
| time / peak memory | 5.2 s / about 64 MB (limits: 15 min, 4 GB) |

**Synthetic sets we generate ourselves** (older, 2026-11-26; fresh seeds, never tuned on the held-out and blind pools):

| Set | PII recall | PII precision | Medical kept | Link precision | Link recall | Canary leaks |
|---|---|---|---|---|---|---|
| dev | 0.997 | 0.995 | 0.988 | 0.983 | 0.962 | 0/23 |
| heldout names/templates | 0.997 | 0.996 | 0.989 | 1.000 | 0.857 | 0/23 |
| blind names/templates/schemas | 0.995 | 0.977 | 0.992 | 0.996 | 0.597 | 0/23 |

`check_dev.py` is a rough guide, not the official score: it does not run the organisers' attacker (a quarter of the score), does not check date
and age-band truthfulness, and does not validate FHIR. The synthetic numbers do not predict the hidden set.

## Security design (assume the server is breached one day)
- **Nothing sensitive is written to disk by the contract run.** Input is opened read-only; the only files written are the redacted outputs.
  There is no raw or intermediate copy, no temp file, no log file, so there is nothing to encrypt at rest. (An encrypted vault exists in
  `security/` for the older run; the contract run does not use it.) A test runs `main.py` with a private TMPDIR and HOME and checks both stay empty.
- **Keys.** The only secret is `RAKSHA_SECRET`, read from the environment. Pseudonyms, date shifts, file-name replacements and UUID aliases are
  derived from it with keyed hashes (HMAC-SHA256, one label per purpose), so a breached output cannot be inverted or linked to another release
  without the secret; a different secret gives different pseudonyms and shifts. The secret is never written anywhere (tested).
- **PII-free logging.** stdout is one line of counts; failures print only an exception type; the report holds hashes, counts and reason codes.
  A subprocess test plants invented canaries in contents, file names, JSON keys, headers and broken files and scans all seven side channels the
  kit lists (report, records, logs, other files, file names, stdout/stderr, TMPDIR/HOME).
- **Quarantine, fail closed.** A file that cannot be parsed or decoded safely is quarantined whole (reason code only, no content), never copied raw;
  a failure removes partial output and exits non-zero (no false success).
- **Last line of defence.** Every rendered field is re-scanned against the raw values found in the run (names, phones, ids, e-mails, ABHA); a field
  that still leaks is blanked, never dropped.
- **Not done:** an audit trail, encryption of the released `sanitized/` tree (it is meant to be shared), key rotation. Anyone who holds the secret
  and the original data can recompute every pseudonym.

## Known problems (open)
- **Tuned on the practice data.** We used its answer key to find and fix bugs, so its numbers are optimistic. Hand probes with invented values still
  leak: an unseen lowercase or Devanagari name with no cue, phones written "9 8 7 6 5 ..." or "(98765) 01240", "policy no X" without a colon.
- **FHIR.** The Bundle is sanitized generically, not resource by resource: hospital names inside bundles are lost (19 of 19 in the practice data),
  and a patient name outside the gazetteer under `name.family` / `name.given` survives (recorded as an expected-failure test).
- **Privacy attacks are not measured.** There is no stand-in for the organisers' attacker. Linking more records per pseudonym gives an attacker that
  joins records by pseudonym more evidence to combine, but generalization is decided per record. Age bands may be coarser than needed.
- **Linking stops short on purpose.** 33 of 771 required records are not linked: lab records carrying only a shared phone and a relative's name,
  and notes with no identifier. Linking them would merge different people. Same-name patients who share a father's name and birth year can still merge.
- **Platform.** All numbers come from Windows; the evaluator runs Linux. A static check found nothing Windows-only, but we have not run it on Linux.
- The legacy development run can leave partial output after a failure; the contract run removes it.

## Rules this repo follows
No LLMs or large models; no network; no PII in outputs, logs, temp files, errors, tests or docs (synthetic data only); no hardcoding to our own
synthetic names (gazetteer vs held-out and blind pools is tested); fail closed (quarantine instead of guessing). Never commit `keys/`, `*.key`,
`data/`, `out/`, `.venv/`.
