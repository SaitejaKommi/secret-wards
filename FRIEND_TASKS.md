# Secret Wards: team guide (read this first)

Track 3 of DevForge. Repo: https://github.com/SaitejaKommi/secret-wards (public). Lead: Saiteja Kommi. Friend A: detection. Friend B: output and security.

## 1. What the project does (5 lines)
1. It reads messy hospital files (CSV, TSV, JSON, JSONL, TXT, XLSX) in English, Hindi and Hinglish. Broken files go to quarantine.
2. It finds personal data (names, phones, dates, ABHA / insurance / MRN ids, e-mails, addresses) and removes it, but keeps medicines, doses, vitals, lab values and diagnoses.
3. It decides which records belong to the same patient (never by name alone) and gives each patient one keyed pseudonym.
4. It shifts dates per patient, makes ages and PIN codes coarser only where a group is too small, and measures re-identification risk with its own attack.
5. A leak gate re-checks every output, then it writes CSV / JSON / TXT, a report and a quarantine index. No LLMs, no network, CPU only, same input gives same output.

**Data flow:** `ingest -> normalize -> detect -> name memory -> link -> pseudonymize -> generalize -> render -> leak gate -> export`.
Stages talk only through the types in `src/secretwards/contracts.py` (do not change it without asking the lead).
Code map: `src/secretwards/{ingest,normalize,detect,link,privacy,export,security}`, `synth/` (fake data with answer keys), `eval/` (scorer), `tests/`.

## 2. Setup from a fresh clone (Python 3.11 needed)
Windows (PowerShell):
```
git clone https://github.com/SaitejaKommi/secret-wards.git
cd secret-wards
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
python -m secretwards keygen
python -m synth --split dev --seed 1 --n 150
python -m secretwards run --in data/synth/dev/in --out out/dev --emit-spans
python -m eval --gold data/synth/dev/gold.json --out out/dev
python -m pytest -q
```
Linux / macOS: same, but `python3.11 -m venv .venv`, `source .venv/bin/activate`, and the paths already use `/`.
Other splits: `--split heldout` and `--split blind` (different names, cities, templates, schemas). Docs worktree: `git worktree add docs-wt docs`.
Always run the pipeline on the `.../in` folder, never on the folder that holds `gold.json`. Expected: `100 passed`, and `records_scored` above 0 in the eval output.

## 3. Real status (measured 2026-11-26 on fresh seeds; synthetic data only, it does NOT predict the hidden set)
| Set | PII recall | PII precision | Medical kept | Link precision | Link recall | Canary leaks |
|---|---|---|---|---|---|---|
| dev | 0.997 | 0.995 | 0.988 | 0.983 | 0.962 | 0/23 |
| heldout names and templates | 0.997 | 0.996 | 0.989 | 1.000 | 0.857 | 0/23 |
| blind names, templates, schemas | 0.995 | 0.977 | 0.992 | 0.996 | 0.597 | 0/23 |

- "Medical kept" counts a generalized age as kept if its band contains the true age. Exact age is kept for only 13-42% of records.
- Expected score if the hidden set behaves like ours: about 71 / 100 (range 58-78, partly a guess).
- Missing: FHIR R4, encryption at rest, audit trail, technical report, stronger attack.

**Open bugs (lead owns these, do not fix them in your branch):**
1. Leak gate can quarantine many records because of one misclassified cell (20 of 1034 on one dev set). Files: `detect/rules.py`, `security/leak_gate.py`.
2. Run time is quadratic for one big text file (15 s for 106 KB, a 4 MB file hangs). File: `detect/merge.py`.
3. A failed run leaves partial output (not atomic). File: `pipeline.py`.
4. Missed: phones like "9 8 7 6 5 0 1 2 4" or "(98765) 01240", "policy no X" without a colon. File: `detect/rules.py`.
5. Same-name patients can merge when they share a father's name and birth year but have different phones. File: `link/compare.py`.

## 4. Git workflow (everyone)
- Never commit to `main` directly. Friend A: branch `feat/detection`. Friend B: branch `feat/output-security`.
  `git checkout main && git pull && git checkout -b feat/detection`
- Commit from your OWN GitHub account (check `git config user.name` and `user.email` before the first commit). Small commits, honest messages
  ("add diagnosis canonical map", not "update"). Never rewrite or force-push shared history.
- Before every pull request: `python -m pytest -q` must pass, and re-run the scorer on dev and blind and paste the numbers in the PR text.
- Open a pull request into `main`. The lead reviews and merges. Keep PRs under about 400 changed lines.
- Update your sections of `docs-wt/PROGRESS.md` on the `docs` branch after each finished task (`cd docs-wt && git add -A && git commit && git push`).
- NEVER commit: `keys/`, `*.key`, `data/`, `out/`, `.venv/`, caches. `.gitignore` covers them; check `git status` before every commit.
- Rules that cannot be broken: no LLMs or generative models, no model over 50M parameters, no network at run time, deterministic output,
  no real personal data anywhere (fake data only), no PII in logs, errors, tests or docs, no hardcoding to our own fake names or templates,
  fail closed (quarantine when unsure).
- Adding a dependency: ask the lead first, pin the exact version in `requirements.txt` and `pyproject.toml`.

## 5. Friend A: detection, diagnosis mapping, stronger attack, CRF last
**Why it matters:** diagnosis words come in many spellings (English, Hinglish, Hindi, OCR typos): 227 different strings for about 75 real
diagnoses. That breaks the privacy grouping and is why most ages get coarsened. A better attack and a CRF raise the privacy and detection scores.

**Files you may touch:** new `src/secretwards/detect/diagnosis.py`; `src/secretwards/privacy/generalize.py` and `privacy/risk.py`
(you own these two); new `src/secretwards/privacy/attack.py`; new `src/secretwards/detect/crf/` (code and a small trained model file under
2 MB); `src/secretwards/detect/__init__.py` (only the `default_detectors()` list); new tests `tests/test_diagnosis.py`, `tests/test_attack.py`,
`tests/test_crf.py`; `synth/` only to ADD new templates or splits (never edit existing gold logic to raise a score).
**Files NOT to touch:** `contracts.py`, `pipeline.py`, `link/*`, `export/*`, `security/*`, `detect/rules.py`, `detect/merge.py`, `detect/names.py`
(the lead is editing these), and anything under `docs-wt/` except PROGRESS.md.

**Steps in order:**
1. **Diagnosis mapping.** Build a canonical diagnosis finder: map English / Hinglish / Hindi / typo variants to one key (lexicon + fuzzy match with
   `rapidfuzz`, transliteration helpers exist in `normalize/translit.py`). Use the key in `privacy/generalize.py` (`extract_facts` and `qi_key`) so groups
   stop fragmenting. Do not change the released diagnosis text, only the grouping key.
2. **Stronger attack.** Implement `contracts.RiskAttack` in `privacy/attack.py` and call it from `privacy/risk.py`. Add what an attacker could know:
   admission date window (we shift dates by 30-365 days), ward, length of stay, drug combination. Report unique-match rate and mean risk for raw data
   versus release, in `report.json` under `privacy`. Keep the existing numbers so we can compare.
3. **Tune the privacy trade-off** with the new grouping: goal is more exact ages kept while the attack stays low. Show a before/after table.
4. **CRF last.** Add a name tagger behind `contracts.Detector` using `sklearn-crfsuite` (ask the lead before adding it). Train on `dev` data from several seeds
   (`python -m synth --split dev --seed N`), never on `blind`. Features: word shape, prefix/suffix, neighbours, gazetteer flag, script. Goal: catch names with
   no cue (lowercase Hinglish, Devanagari). Register it in `default_detectors()`. Keep it deterministic (fixed seed, fixed feature order) and make the model file load offline.
**Definition of done:** tests pass; dev and blind scores do not get worse (PII recall, precision, medical kept, link precision); diagnosis classes in
a 1500-patient run drop from about 227 strings to under 100; exact-age-kept goes up with unique-match rate not worse than 2x today's (0.8% at 1500 patients);
CRF raises recall on the hand probes for unlabeled lowercase/Devanagari names (ask the lead for `probe2`); PR text has the numbers.

**Ready-to-paste prompt for your AI tool (Friend A):**
```
You are helping on the Secret Wards repo (hackathon Track 3: offline, LLM-free de-identification and record linkage for English/Hindi/Hinglish hospital
records). Read CLAUDE.md, README.md and docs-wt/FRIEND_TASKS.md section 5 first. I am Friend A (detection). Work only on branch feat/detection.
Rules: no LLMs or generative models, no model above 50M parameters, no network at run time, deterministic output, synthetic data only, no PII in logs/tests/docs,
no hardcoding to our synthetic names or templates, never edit gold data to improve a score, never commit keys/ data/ out/ .venv/. Do not change
src/secretwards/contracts.py, pipeline.py, link/, export/, security/, detect/rules.py, detect/merge.py, detect/names.py. Do these in order, one small commit each:
(1) detect/diagnosis.py canonical diagnosis mapping used by privacy/generalize.py grouping; (2) privacy/attack.py stronger re-identification attack
implementing contracts.RiskAttack, reported in report.json; (3) tune k-anonymity trade-off; (4) last, a CRF name detector behind contracts.Detector
(ask me before adding sklearn-crfsuite). After each step run: python -m pytest -q and the scorer on dev and blind
(python -m synth --split blind --seed 7 --n 300; python -m secretwards run --in data/synth/blind/in --out out/blind --emit-spans;
python -m eval --gold data/synth/blind/gold.json --out out/blind), and show me the numbers before and after. Stop and ask if a design choice is unclear
or a bug survives two attempts.
```

## 6. Friend B: FHIR R4, encryption wiring, audit trail, report, demo
**Why it matters:** the brief requires FHIR R4 output (Patient, Encounter, Observation, MedicationRequest), encryption at rest, an audit trail and a short technical
report. None exist yet; they are worth points in "Output quality" and the security part of the deliverables.

**Files you may touch:** new `src/secretwards/export/fhir.py` and `export/__init__.py`; `src/secretwards/security/vault.py`, new
`security/audit.py`, `security/safe_log.py`; new tests `tests/test_fhir.py`, `tests/test_vault.py`, `tests/test_audit.py`; `README.md` (setup/demo parts only);
new `scripts/demo.sh` / `scripts/demo.ps1`; on the docs branch: `docs-wt/REPORT.md` (the technical report) and your part of PROGRESS.md.
`pipeline.py`: only AFTER the lead merges the "atomic output" change; then add one clearly marked block that calls your exporter and audit log.
**Files NOT to touch:** `contracts.py`, `detect/*`, `link/*`, `privacy/*`, `ingest/*`, `normalize/*`, `eval/*`.

**Steps in order:**
1. **FHIR R4.** Implement `contracts.Exporter` in `export/fhir.py`. Input is `RedactedRecord` (it has `pseudonym`, `fields`, `text`, and `meta` with age band, sex,
   PIN prefix). Produce Patient, Encounter, Observation and MedicationRequest bundles. Parse vitals, labs, drugs, dose, frequency and duration from the
   already-redacted text/fields with regexes (similar patterns exist in `detect/medical_guard.py`; you may import them). Use only the pseudonym as identifier.
   Validate with `fhir.resources` (ask the lead before adding it; pin the version) and add a test that validates a sample bundle. Output goes to `OUT/fhir/`.
2. **Encryption wiring.** `AesGcmVault` exists but nothing uses it. Use it for: optional encrypted copies of quarantined input files (config switch), and
   document exactly what is on disk and what is encrypted. Keys come from `keys/enc.key` (separate file per purpose, never printed). Add key-rotation notes.
   Test: round trip, wrong key fails, tamper fails, no plaintext of a planted fake value in the encrypted file.
3. **Audit trail.** Add `security/audit.py`: an append-only log of events (run start, file quarantined, counts, leak-gate repairs) with only ids, counts and
   reason codes, never values. Chain entries with HMAC so tampering is detectable. Test that a planted fake value never appears.
4. **Technical report** `docs-wt/REPORT.md` (about 2-3 pages): detection engine, linkage and pseudonyms, privacy layer with the measured risk, output formats,
   security architecture (be honest about what is not encrypted), limits. Use the real numbers from `PROGRESS.md`.
5. **Demo.** A script that generates fake data, runs the pipeline, shows the before/after of one record (fake data only), the report, and the attack numbers.
**Definition of done:** `python -m pytest -q` passes; `OUT/fhir/` bundles validate; a test proves vault and audit work; the audit log and encrypted files contain no
planted fake value; README demo steps work from a fresh clone on Windows and Linux; REPORT.md merged on the `docs` branch.

**Ready-to-paste prompt for your AI tool (Friend B):**
```
You are helping on the Secret Wards repo (hackathon Track 3: offline, LLM-free de-identification and record linkage for English/Hindi/Hinglish hospital
records). Read CLAUDE.md, README.md and docs-wt/FRIEND_TASKS.md section 6 first. I am Friend B (output and security). Work only on branch feat/output-security.
Rules: no LLMs, no network at run time, deterministic output, synthetic data only, no PII in logs/tests/docs, never commit keys/ data/ out/ .venv/. Do not change
src/secretwards/contracts.py, detect/, link/, privacy/, ingest/, normalize/, eval/. Do these in order, one small commit each: (1) export/fhir.py implementing
contracts.Exporter, producing valid FHIR R4 Patient, Encounter, Observation and MedicationRequest from RedactedRecord (use only the pseudonym as identifier; ask me before
adding fhir.resources and pin its version); (2) wire security/vault.py (AES-GCM) for optional encrypted quarantine copies and document what is on disk;
(3) security/audit.py append-only HMAC-chained audit log with ids/counts/codes only; (4) docs-wt/REPORT.md technical report using real numbers; (5) a demo script.
Each step needs tests. Edit pipeline.py only after I tell you the atomic-output change is merged, and only add one marked block. Run python -m pytest -q after
each step. Stop and ask if a design choice is unclear or a bug survives two attempts.
```

## 7. Lead (Saiteja) task list, in order
1. Fix gate over-quarantine (`detect/rules.py`, `security/leak_gate.py`). 2. Fix quadratic merge (`detect/merge.py`) and add a perf test.
3. Atomic output (`pipeline.py`). 4. Phone / ID pattern gaps (`detect/rules.py`). 5. Stop same-name merges when phones differ (`link/compare.py`).
6. Review and merge PRs; keep `PROGRESS.md` current. Decisions still open: age accuracy versus attack resistance (`qi_include_dx`), keys folder outside the project for the real run.

## 8. Quick checks before you push
`git status` shows only your files; `git diff --stat main` is small; `python -m pytest -q` is green; no key, data, out or personal path in the diff.
