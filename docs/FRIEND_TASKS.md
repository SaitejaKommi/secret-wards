# Secret Wards: team guide (two people: Saiteja and Jaisheel)

Track 3 of DevForge. Repo: https://github.com/SaitejaKommi/secret-wards (public, single branch `main`; this `docs/` folder is deleted after the hackathon).
**Saiteja (lead)** owns the output contract, linking, security, README and brief. **Jaisheel** owns detection, FHIR sanitizing and the attacker/privacy tuning.
(A third friend is busy; his tasks are folded into these two lists.)

**STEP 0 for every person and every AI tool: read `docs/TOOLKIT.md` before anything else.** The organisers released an official kit with a strict output contract
(`raksha.toml`, `main.py`, `RAKSHA_SECRET`, `sanitized/`, `report.json`, `records.jsonl`). Our code does not meet it yet. TOOLKIT.md lists every conflict and the plan (P0-P7).
Never hardcode names or values from the practice data or its answer key. Never commit the kit's `dev/` folder (practice data, truth, attacker).

## 1. What the project does (5 lines)
1. It reads messy hospital files (CSV, TSV, JSON, FHIR bundles, TXT; UTF-8, BOM, UTF-16, cp1252) in English, Hindi and Hinglish. Broken files are quarantined, never copied raw.
2. It finds personal data (names, relatives, phones, Aadhaar, PAN, ABHA, MRN, addresses, dates) in cells, keys, headers, file names, metadata and free text, and removes it, but keeps medicines, doses, vitals, labs and diagnoses exactly.
3. It decides which records are the same patient (never by name alone) and gives each patient one keyed pseudonym (from `RAKSHA_SECRET`).
4. It shifts dates per patient, generalizes age and place only where needed, and checks risk against an attacker that holds a voter-style registry.
5. It writes `sanitized/` (same paths and formats as the input), `report.json` and `records.jsonl`. No LLMs, no network, 2 CPUs, 4 GB, 15 minutes, same input and secret give the same bytes.

**Data flow today:** `ingest -> normalize -> detect -> name memory -> link -> pseudonymize -> generalize -> render -> leak gate -> export`.
**Needed (contract):** the same stages, then a *contract writer* that mirrors the input tree into `sanitized/`, redacts in place (no dropped rows, no new columns), writes SHA-256 `report.json` and `records.jsonl`.
Stages talk only through `src/secretwards/contracts.py` (frozen; ask Saiteja before changing it).

## 2. Setup from a fresh clone (Python 3.11 needed)
Windows (PowerShell):
```
git clone https://github.com/SaitejaKommi/secret-wards.git
cd secret-wards
python -m venv .venv          # must be Python 3.11 (python --version); with the py launcher: py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
python -m secretwards keygen
python -m synth --split dev --seed 1 --n 150
python -m secretwards run --in data/synth/dev/in --out out/dev --emit-spans
python -m eval --gold data/synth/dev/gold.json --out out/dev
python -m pytest -q                                   # expected: 100 passed
```
Linux / macOS: same, but `python3.11 -m venv .venv` and `source .venv/bin/activate`.

**Official kit (next to the repo, NOT inside it):**
```
cd ..                                             # the folder that contains secret-wards/
git clone -c core.autocrlf=false https://github.com/Reinforce-SST/Secret-Wards-ToolKit.git   # -c core.autocrlf=false is REQUIRED on Windows
$env:RAKSHA_SECRET="practice"                     # PowerShell;  Linux/macOS: export RAKSHA_SECRET=practice
python Secret-Wards-ToolKit/starter/main.py --input Secret-Wards-ToolKit/dev/input --output secret-wards/out/starter
python Secret-Wards-ToolKit/validate_output.py --input Secret-Wards-ToolKit/dev/input --output secret-wards/out/starter   # CONTRACT OK
python Secret-Wards-ToolKit/check_dev.py --output secret-wards/out/starter                                                # about 84% leaked: expected
```
**The contract path is now on `main` (after Saiteja's PR). Measure with the real run:**
```
cd secret-wards
$env:RAKSHA_SECRET="practice"         # Linux: export RAKSHA_SECRET=practice
python main.py --input ../Secret-Wards-ToolKit/dev/input --output out/ours
python ../Secret-Wards-ToolKit/validate_output.py --input ../Secret-Wards-ToolKit/dev/input --output out/ours   # CONTRACT OK
python ../Secret-Wards-ToolKit/check_dev.py --output out/ours
```
First check the kit is intact: all 200 files in `dev/input` must hash to the sha256 values in `dev/truth/truth.json` (a CRLF checkout breaks this).
Old helper, for the legacy pipeline only:
```
cd secret-wards
python -m secretwards run --in ../Secret-Wards-ToolKit/dev/input --out out/ours
python scripts/adapt_for_checkdev.py ../Secret-Wards-ToolKit/dev/input out/ours out/ours_adapted
python ../Secret-Wards-ToolKit/check_dev.py --output out/ours_adapted
```
(Baseline today: 4.7% leaked; PAN 95%, Aadhaar 31%, MRN 9%, village 12%, metadata 38%; medical kept 77.8% only because our leak gate drops records; filename 100% is an artefact of the helper.)

## 3. Real status (measured 2026-11-26; details in `docs/TOOLKIT.md` section 7)
- Our synthetic data (own generator; does NOT predict the hidden set): PII recall 0.995-0.997, precision 0.977-0.996, medical kept 0.988-0.992, link precision 0.98-1.0, link recall 0.60-0.96, canaries 0/23.
- Official practice data, kit starter: CONTRACT OK, 84.1% leaked, 4/4 canaries, score about 8.
- Official practice data, our contract path (P0 + Jaisheel PR #1-#3): **CONTRACT OK**; 0.2% leaked (5 house numbers), hiding places 0%, canaries 0/4, medical kept 98.0%, linking P 1.00 / R 0.61 / 0 wrong merges, 6.5 s.
- Still open: FHIR sanitizing (hospital names in bundles lost), linking recall, coarse age bands, the stand-in attacker, one slow big-file case.
- Known bugs (Saiteja): gate over-quarantine, quadratic time on one big text file, non-atomic output, a few phone/ID misses, same-name merges when phones differ.

## 4. Git workflow (both of you)
- Never commit to `main` directly. Saiteja: `feat/contract` (P0), then `feat/identity`, `feat/hygiene`. Jaisheel: `feat/detection`, then `feat/fhir`, `feat/attacker`.
- Commit from your OWN GitHub account (check `git config user.name` and `user.email`; use your GitHub noreply email so your personal email is not public). Small commits, honest messages. Never rewrite or force-push shared history.
- Before every PR: `python -m pytest -q` green; run the synthetic scorer on dev and blind; once P0 is merged also run the kit's `validate_output.py` and `check_dev.py`; paste the numbers in the PR text.
- After each finished task update your rows in `docs/PROGRESS.md` (in the same PR).
- NEVER commit: `keys/`, `*.key`, `data/`, `out/`, `.venv/`, caches, the kit's `dev/`, any answer key or attacker file, anything containing `RAKSHA_SECRET`. Read `git status` before every commit.

### Pull request steps (copy these)
```
git fetch origin
git checkout -b feat/detection origin/main
# ... work, small commits ...
python -m pytest -q
git push -u origin feat/detection
gh pr create --base main --head feat/detection --title "short title" --body "what changed; test result; scorer numbers before/after"
```
- Keep your branch current with `git fetch origin && git merge origin/main`. Do not rebase or force-push anything already pushed.
- One topic per PR (under about 400 changed lines). Do not edit files owned by the other person (section 7). If you must, ask in the PR first.
- Review each other's PRs within a few hours (the team is two people). Saiteja merges PRs that touch `pipeline.py`, `contracts.py`, `contract/`; otherwise whoever did not write the PR merges it after tests pass.
- A PR that touches `src/secretwards/contracts.py` is not merged without both people agreeing.
- Rules that cannot be broken: no LLMs or generative models, no model over 50M parameters (declare any model in README), no network at run time, deterministic output, fake data only,
  no PII or `RAKSHA_SECRET` in logs, errors, tests or docs, no hardcoding to our own or the practice names/values, fail closed (quarantine whole files you cannot clean; never drop records silently).
- New dependency: agree first, pin the exact version in `requirements.txt` and `pyproject.toml`. The run environment is Linux; check wheels exist.

## 5. Jaisheel: detection, FHIR sanitizer, attacker (plan steps P2, P3, P4; about 26 hours)
**Why:** detection is 20 points and every surviving identifier costs -1 (a canary -3); privacy is 25 points and is judged by the organisers' attacker; every FHIR file must stay valid.
**Files you own (mostly NEW files, so we do not collide):**
`src/secretwards/detect/india_ids.py` (Aadhaar 12 digits with any separators and Devanagari digits, masked Aadhaar, PAN, ABHA, UHID/MRN styles, insurance),
`detect/address_fields.py` (village, locality/mohalla, house, landmark, PIN, tehsil/district; by context and by column meaning),
`detect/hidden.py` (base64/hex/entity decoding, metadata and `source_path` rules, JSON keys, file-name PII), `detect/diagnosis.py` (canonical diagnosis key), optional `detect/crf/*`,
`privacy/*` (`generalize.py`, `risk.py`, new `attack.py`), `fhir/*` (new: `sanitize.py`, `validate.py`), `scripts/adapt_for_checkdev.py`, and the tests `tests/test_india_ids.py`, `test_address_fields.py`, `test_hidden.py`, `test_attack.py`, `test_fhir.py`.
Register new detectors ONLY in `detect/__init__.py` `default_detectors()` (a one-line change per detector; Saiteja will not touch that file).
**Files NOT to touch (Saiteja's):** `contracts.py`, `pipeline.py`, `main.py`, `raksha.toml`, `contract/*`, `ingest/*`, `export/*`, `link/*`, `detect/rules.py`, `detect/merge.py`, `detect/names.py`, `detect/address.py`, `detect/lexicon.py`, `security/*`, `eval/*`, `docs/*` except your rows in PROGRESS.md.
**Steps in order (one small commit each, each with tests):**
1. **Indian IDs and address fields** (biggest leaks today: PAN, Aadhaar, MRN, village, locality, metadata). Use `check_dev.py` per-type rows to prioritise. Write rules that understand *context* (a label, a column meaning, a digit pattern with validation), never lists of practice values: hidden data has unseen labels, column names and formats.
2. **Hidden places:** base64 attachments (decode, clean, re-encode), JSON keys, metadata, file names. The official leak scan decodes base64, hex, `\uXXXX`, HTML entities and folds homoglyphs and zero-width characters, so do the same when detecting.
3. **Meaning traps:** keep `Dr. <name>`, `C/O fever`, `K/C/O`, `h/o`, wards, doses, `1-0-1`, eponyms, ASHA; remove relatives (S/o, W/o, C/O <name>).
4. **FHIR sanitizer** in `fhir/sanitize.py` + validator `fhir/validate.py`. Interface (Saiteja's contract writer will supply the context):
   `sanitize_bundle(bundle: dict, ctx) -> dict`, with `ctx.redact(text, field_hint) -> str`, `ctx.shift_date(value: str) -> str` (same syntax: date, dateTime or instant) and `ctx.pseudonym(key) -> str`.
   Keep resource ids and every `reference` resolvable inside the Bundle, keep value types and R4 syntax, clean `meta.source`, `identifier`, narrative `text.div`, extensions and base64 attachments; never add or drop entries.
   Write a tiny fake `ctx` for your tests. Validate the kit's 19 practice bundles locally (never commit them). Spec for what the organisers check: `docs/toolkit/docs/SCORING.md` section 5 (FHIR validity).
5. **Stand-in attacker** in `privacy/attack.py` from `docs/toolkit/docs/ATTACKS.md` and the kit's `dev/attacker/` files (registry linkage A2/A3, profile A4, targeted A5 with global-shift recovery, pseudonym inversion A6). Report risk raw vs sanitized under `privacy` in the report.
6. **Tune generalization** against that attacker and the kit's utility formulas (5-year band 0.9, village to tehsil/district 0.7-0.8, rare-value suppression only for rare combinations, per-patient date shifts so a global shift cannot be recovered). Add a canonical diagnosis key so groups stop fragmenting.
7. **Optional, last:** a CRF name tagger for names with no cue (`sklearn-crfsuite`, agree first; train only on our synthetic data).
**Definition of done:** tests pass; on the practice data PAN and Aadhaar leaks under 2%, village/locality/house/landmark under 5%, metadata and base64 under 5%, name leaks do not rise; medical values kept does not fall; sanitized bundles validate with all references resolving; the stand-in attacker succeeds less on sanitized than on raw data; numbers are in each PR.

### Prompt for Jaisheel's Claude Code (paste this once, as your first message)
```
You are working on "Secret Wards" (DevForge hackathon Track 3): an offline, CPU-only, LLM-free pipeline that de-identifies messy English/Hindi/Hinglish hospital records,
links records of the same patient, and must follow the organisers' strict output contract. I am Jaisheel; the lead is Saiteja. Be careful, honest and incremental.

FIRST, before changing anything:
1. Read CLAUDE.md, then docs/TOOLKIT.md, then docs/FRIEND_TASKS.md (sections 1-5 and 7). Skim docs/toolkit/docs/SPEC.md and SCORING.md.
2. Set up: Python 3.11 venv in the repo (python -m venv .venv; activate it), pip install -r requirements.txt, pip install -e ., python -m secretwards keygen, python -m pytest -q (expect 100 passed).
   Tell me if anything fails; do not paper over it.
3. Clone the organisers' kit NEXT TO the repo (not inside), with line endings untouched: git clone -c core.autocrlf=false https://github.com/Reinforce-SST/Secret-Wards-ToolKit.git ../Secret-Wards-ToolKit.
   Verify all 200 files in ../Secret-Wards-ToolKit/dev/input hash to the sha256 values in dev/truth/truth.json (if not, re-clone with autocrlf off). Read its START_HERE.md and its scripts before running them.
   Then run the real contract path from docs/FRIEND_TASKS.md section 2 (RAKSHA_SECRET=practice python main.py --input ../Secret-Wards-ToolKit/dev/input --output out/ours; validate_output.py; check_dev.py) and show me the numbers.
4. Create the branch feat/detection from origin/main. Check git config user.name / user.email are MY GitHub account (noreply email).

THEN do my tasks from docs/FRIEND_TASKS.md section 5, in order, one small commit each, each with tests, and after each step run: python -m pytest -q, the synthetic scorer
(python -m synth --split dev --seed 1 --n 150; python -m secretwards run --in data/synth/dev/in --out out/dev --emit-spans; python -m eval --gold data/synth/dev/gold.json --out out/dev),
and the kit's validate_output.py and check_dev.py on the real contract run. Show me the numbers before and after each step. Update my rows in docs/PROGRESS.md.
When a step is done: git push -u origin feat/detection and open a pull request into main with gh pr create (include the numbers); never push to main.

HARD RULES: no LLMs or generative models, no model above 50M parameters, no network at run time, deterministic output, fake data only. NEVER hardcode names, numbers or values from the practice data or its
answer key (hidden data has new patients and unseen formats): write context-aware rules. NEVER commit keys/, data/, out/, .venv/, the kit's dev/ folder, answer keys, attacker files, or anything containing RAKSHA_SECRET.
No PII or secrets in logs, errors, tests or docs. Do not edit files owned by Saiteja (docs/FRIEND_TASKS.md section 7): contracts.py, pipeline.py, main.py, contract/, ingest/, export/, link/, security/,
detect/rules.py, detect/merge.py, detect/names.py, detect/address.py, detect/lexicon.py, eval/. Register new detectors only in detect/__init__.py. If a design choice is unclear or a bug survives two attempts, stop and ask me.
Start with step 1 of section 5 only, and report back before moving on.
```

## 6. Saiteja: contract, identity, security, brief (plan steps P0, P1, P5, P6, P7; about 27 hours)
**Why:** without the contract every category scores 0 and the -10 false-success and -20 raw-copy penalties are live. Linking is 15 points; the brief and public repo are required to submit.
**Files you own:** `pipeline.py`, new root `main.py`, `raksha.toml`, new package `src/secretwards/contract/` (keys derived from `RAKSHA_SECRET`, mirror writer, in-place redaction, SHA-256 report, `records.jsonl`, atomic output, exit codes),
`ingest/*`, `export/*`, `link/*`, `detect/rules.py`, `detect/merge.py`, `detect/names.py`, `detect/address.py`, `detect/lexicon.py`, `security/*`, `eval/*`, `contracts.py` (frozen), `README.md`, `docs/*`, `.github/workflows/*`, `docs/brief.pdf`.
**Steps in order:**
1. **P0 contract adapter** (`feat/contract`, about 8 h): `raksha.toml` and `main.py`; HKDF-derive the four sub-keys from `RAKSHA_SECRET` (no `keys/` on the organiser machine); write `sanitized/` as a mirror of the input tree (same paths, formats, delimiters, headers, row counts); redact in place, never drop rows or add columns; put the pseudonym inside records using an existing id column or a `Patient:` line; SHA-256 `report.json` (9 counts, entities, timing, resources); `records.jsonl` with `row:N` / JSON pointers / `doc`; atomic output; exit codes. Stop quarantining records; quarantine only whole files you cannot process. Publish the FHIR `ctx` object (see section 5, step 4) for Jaisheel.
2. **P1** (`feat/hygiene`, about 4 h): fix gate over-quarantine (`detect/rules.py` header rule, `security/leak_gate.py`), fix the quadratic merge (`detect/merge.py`) with a perf test, run the contract path on Linux (CI).
3. **P5 identity** (`feat/identity`, about 5 h): `records.jsonl` pseudonyms from linking, `null` when evidence is weak, stop same-name merges when phones differ, homonym tests from the kit's traps.
4. **P6 hygiene and security** (about 5 h): tests that stdout/stderr/logs/report/records/file names/TMPDIR contain no planted canary or secret; honest security design (the pipeline writes no raw or intermediate data; keep `RAKSHA_SECRET` out of everything); optional AES-GCM for any spill file.
5. **P7 submission** (about 5 h): README (setup, architecture diagram, how each part works, security design, limitations), the 2-page Project Brief PDF with measured numbers (`docs/toolkit/brief/PROJECT_BRIEF_TEMPLATE.md`), `check_submission.py --repo . --run` green, repo public, last commit before the deadline is the one to be judged.
Review and merge Jaisheel's PRs; keep `docs/PROGRESS.md` current. Open decision: age accuracy vs attack resistance (`qi_include_dx`).

## 7. Who owns which file (avoid conflicts)
| Area | Owner |
|---|---|
| `contracts.py` | frozen; change only if both agree |
| `pipeline.py`, `main.py`, `raksha.toml`, `contract/*`, `ingest/*`, `export/*`, `link/*`, `eval/*`, `security/*` | Saiteja |
| `detect/rules.py`, `detect/merge.py`, `detect/names.py`, `detect/address.py`, `detect/lexicon.py` | Saiteja |
| `detect/india_ids.py`, `detect/address_fields.py`, `detect/hidden.py`, `detect/diagnosis.py`, `detect/crf/*`, `detect/__init__.py` (detector list only) | Jaisheel |
| `privacy/*`, `fhir/*`, `scripts/adapt_for_checkdev.py` | Jaisheel |
| `synth/*` | Jaisheel may ADD templates/splits; never edit gold logic to raise a score |
| `tests/*` | each person for their own new test files; Saiteja for existing ones |
| `README.md`, `docs/*`, CI workflow, brief | Saiteja (Jaisheel updates only his rows in `docs/PROGRESS.md`) |

## 8. Order of work and hand-offs
1. DONE: Jaisheel steps 1-2 (merged), Saiteja P0 + gate fixes (PR). Everyone measures with `python main.py` + the kit checkers.
2. NEXT: Jaisheel step 3 (meaning traps, 5 house numbers), then the FHIR sanitizer (step 4) and the stand-in attacker; Saiteja P5 identity, P1 speed, the FHIR `ctx` hook, P6 and the README. Jaisheel: use `hidden.safe_label` / `sanitize_path` / `clean_encoded` from your own PR #2 when wiring FHIR; Saiteja's writer already renames paths and headers itself.
3. Then: Jaisheel finishes the attacker and tuning; Saiteja does P6 and P7.
4. Last 3 hours before the deadline: freeze features; run `check_submission.py --repo . --run`, fix only what it reports, make the repo public, final commit.

## 9. Quick checks before you push
`git status` shows only your files; `git diff --stat main` is small; `python -m pytest -q` is green; no key, data, out, kit `dev/`, answer key or personal path in the diff; the kit checkers do not get worse.
