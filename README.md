# Secret Wards

Offline, LLM-free de-identification and record linkage for messy English / Hindi / Hinglish hospital records (DevForge Track 3).
No network, CPU only, deterministic, synthetic data only.

**Status: working end to end on the organisers' contract, also on Linux; not finished.** `python main.py --input IN --output OUT` (with
`RAKSHA_SECRET` set) writes `sanitized/`, `records.jsonl` and `report.json`. The kit's `check_submission.py --run` prints READY TO SUBMIT in a
Python 3.12 container with 2 CPUs, 4 GB and no network. On the kit's practice data its own self-check reports 0 of 3,230 personal values still
visible, 0 canaries, 99.6% of medical values kept, linking precision 1.00 / recall 0.91; our stand-in for the organisers' attacker re-identifies
4 of 48 patients (47 of 48 on the raw data). We tuned against that practice data, so treat those numbers as an upper bound; see "Known problems".
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
**Official practice data** (200 files, `RAKSHA_SECRET=practice`, the kit's `check_dev.py`; 2026-11-26):

| Measure | Value |
|---|---|
| personal values still visible | 0 of 3,230 (Latin 0.0%, Devanagari 0.0%, Hinglish 0.0%; file names, metadata, base64, keys, headers all 0.0%) |
| planted canaries found | 0 of 4 |
| medical values kept | 4,835 of 4,855 (99.6%) |
| patient linking | precision 1.00, recall 0.91, F0.5 0.98, 0 wrong merges (own reproduction of the kit's identity formula: B-cubed F1 0.96, language trap 0.87, fragmented trap 0.83, homonyms 2 of 2 kept apart) |
| FHIR | 19 of 19 bundles pass our structural validator (ids, value sets, dates, base64, every reference resolves); the organisers' validator is hidden |
| stand-in attacker (our implementation of the kit's A2-A5, `privacy/attack.py`) | patients re-identified by profile linking 4 of 48 (raw data 47 of 48); registry-linkage risk 0.04 (raw 0.71); targeted attack 0.61 (raw 0.93); 0 of 48 pseudonyms inverted; 0 records keep a pseudonym under another secret |
| time / peak memory | 5.3 s / 55 MB on Linux with 2 CPUs (limits: 15 min, 4 GB); about 150 records per second, single process |
| Linux | `check_submission.py --run` READY TO SUBMIT (python:3.12, `--cpus 2 --memory 4g --network none`); output byte-identical to the Windows output for the same secret |

**Synthetic sets we generate ourselves** (older, 2026-11-26; fresh seeds, never tuned on the held-out and blind pools):

| Set | PII recall | PII precision | Medical kept | Link precision | Link recall | Canary leaks |
|---|---|---|---|---|---|---|
| dev | 0.997 | 0.995 | 0.988 | 0.983 | 0.962 | 0/23 |
| heldout names/templates | 0.997 | 0.996 | 0.989 | 1.000 | 0.857 | 0/23 |
| blind names/templates/schemas | 0.995 | 0.977 | 0.992 | 0.996 | 0.597 | 0/23 |

`check_dev.py` is a rough guide, not the official score: it does not run the organisers' attacker (a quarter of the score), does not check date
and age-band truthfulness, and does not validate FHIR. Our attacker is a stand-in calibrated on the raw practice data (A4 47 of 48 against the kit's
99.3%, A5 0.93 against 0.971); it has no registry, so it was never part of `main.py`. The synthetic numbers do not predict the hidden set.

## Security design (assume the server is breached one day)
**What protects data at rest.** Nothing sensitive is stored by the contract run, so there is nothing to encrypt:
- The input is opened read-only. The only files written are the redacted outputs. No raw copy, intermediate file, temp file or log is written to disk;
  records live in process memory for the run only. A test runs `main.py` with a private TMPDIR and HOME and checks both stay empty.
- The released `sanitized/` tree holds no direct identifiers and is not encrypted, because it is meant to be shared. Its protection is the
  de-identification itself: keyed pseudonyms, per-patient date shifts, generalized quasi-identifiers, measured with the stand-in attacker above.
- We do **not** encrypt or manage the raw input; where it lives and how its disk is protected is the operator's job. We cannot control whether the host
  swaps process memory to disk. There is no encryption code in this repository (an earlier unused AES-GCM stub was removed rather than shipped as a claim).
- If the machine is breached after a run, the attacker gets the redacted release, the code, and no keys: the only secret is `RAKSHA_SECRET`, supplied
  in the environment and never written anywhere (tested). Without it the pseudonyms cannot be inverted or linked to another release; anyone who holds
  the secret and the original data can recompute every pseudonym.

**Other controls.**
- **Key separation.** Pseudonyms, date shifts and file-name / UUID aliases use three sub-keys derived from the secret with HMAC-SHA256, one label per
  purpose (a different secret gives unrelated keys, pseudonyms and shifts; checked: 0 records keep a pseudonym). Keys are not held next to data.
- **PII-free logging.** stdout is one line of counts; failures print only an exception type; the report holds hashes, counts and reason codes.
  A subprocess test plants invented canaries in contents, file names, JSON keys, headers and broken files and scans all seven side channels the
  kit lists (report, records, logs, other files, file names, stdout/stderr, TMPDIR/HOME).
- **Quarantine, fail closed.** A file that cannot be parsed or decoded safely is quarantined whole (reason code only, no content), never copied raw;
  a failure removes partial output and exits non-zero (no false success).
- **Last line of defence.** Every rendered field is re-scanned against the raw values found in the run (names, phones, ids, e-mails, ABHA); a field
  that still leaks is blanked, never dropped. Hospital and doctor names inside FHIR leaves are exempt from the name check; phones and ids are not.
- **Not done:** an audit trail (the run keeps no record of its own beyond `report.json`) and key rotation.

## Known problems (open)
- **Tuned on the practice data.** We used its answer key to find and fix bugs, so its numbers are optimistic. A stress test with invented formats
  and layouts found more problems than the practice data did. Hand probes with invented values still leak: an unseen lowercase or Devanagari name with
  no cue, phones written "9 8 7 6 5 ..." or "(98765) 01240", "policy no X" without a colon, a phone written as a hex string.
- **Privacy versus utility.** The stand-in attacker re-identified 40 of 48 patients before per-patient generalization and 4 of 48 after. The price: with
  a "5 patients per group" rule inside a 48-patient release most patients land in coarse age groups (18-59, 60-89), which our proxy of the kit's
  generalization score puts at 0.28 for age (0.54 before). Uniform 10-year bands would leave 19 of 48 re-identified, 5-year bands 28 of 48.
  Counting the group size against the population an attacker searches (4-5 times the patients) would keep finer bands for most patients; not done.
  An age stored as a JSON number cannot hold a band, so the writer emits a keyed surrogate number, which is not truthful for the age-band score.
- **FHIR.** Bundles are handled resource by resource (hospital and doctor names kept; patient and relative names, phones, ids, addresses removed). The
  organisers' validator is hidden, so unusual resource types or elements may still fail it.
- **Linking stops short on purpose.** 33 of 771 required records are not linked: lab records carrying only a shared phone and a relative's name,
  and notes with no identifier. Linking them would merge different people. Same-name patients who share a father's name and birth year can still merge.
- **Speed and memory.** One process, about 150 records (or 0.1 MB of text) per second and about 26 KB of memory per record: roughly 120,000 records fit in
  15 minutes and 150,000 in 4 GB. The practice set (817 records) takes 5 s; a very large bulk export would not fit.
- A label such as `Patient:` can absorb up to four following words ("Patient: Rao seen today"), which over-redacts a little.
- The legacy development run can leave partial output after a failure; the contract run removes it.

## Rules this repo follows
No LLMs or large models; no network; no PII in outputs, logs, temp files, errors, tests or docs (synthetic data only); no hardcoding to our own
synthetic names (gazetteer vs held-out and blind pools is tested); fail closed (quarantine instead of guessing). Never commit `keys/`, `*.key`,
`data/`, `out/`, `.venv/`.
