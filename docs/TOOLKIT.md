# TOOLKIT.md: the official Track 3 kit and what it means for us (READ THIS FIRST)

Source: https://github.com/Reinforce-SST/Secret-Wards-ToolKit (MIT, commit 6c0a85a of 2026-11-26). A copy of its docs, scripts and starter is in `toolkit/`
(without its practice data, answer key and attacker files: those must never be committed). **The kit's `docs/SPEC.md`, `docs/SCORING.md` and
`docs/PROBLEM_STATEMENT.md` are now the authority.** Where they differ from `PROBLEM_ORIGINAL.md`, `PROBLEM_STATEMENT.md`, `ARCHITECTURE.md` or our code, the kit wins.
The local file `secret-wards-kit.zip` is NOT the official kit; it is our own starter pack (CLAUDE.md, AGENTS.md, KICKOFF.md, old docs).

Rules for every person and every AI tool:
- Never hardcode a name, number or value taken from the practice data or its answer key. The hidden data has new patients, and at least one hidden dataset has
  names, labels, identifier formats, date formats and column names we have never seen.
- Never commit `dev/` (practice input, truth, attacker). Keep the kit in a folder NEXT TO this repo, not inside it.
- Never write `RAKSHA_SECRET` anywhere (files, logs, stdout, stderr, temp files, reports).

## 1. How to set up the kit (each teammate)
```
cd ..                                                    # the folder that CONTAINS secret-wards/
git clone https://github.com/Reinforce-SST/Secret-Wards-ToolKit.git
# layout:  hackathon/Secret-Wards-ToolKit   and   hackathon/secret-wards
```
Read `Secret-Wards-ToolKit/START_HERE.md` (15 minutes). The kit itself uses only the Python standard library (3.10+).
Windows (PowerShell): `$env:RAKSHA_SECRET="practice"` before running; Linux/macOS: `RAKSHA_SECRET=practice python3 ...`. If `python3` is missing on Windows use `python`.

## 2. What the organisers give us
`dev/input/` practice data: 200 files, 48 patients, 4 hospital systems (a UTF-8-BOM CSV with a duplicate copy, a UTF-16 TSV with Hindi headers, a cp1252 legacy CSV with
ragged rows and month-first dates, nested JSON with a misspelled key holding a number), folders `registration opd discharge notes prescriptions fhir lab billing clean misc`.
`dev/truth/truth.json` practice answer key. `dev/attacker/` the attacker's voter-style registry and known facts. The hidden evaluation uses 3 hidden datasets (new patients,
larger; at least one with unseen names, labels, formats), then runs us twice more (same secret: must be byte-identical; different secret: pseudonyms and date shifts must change).

Measured from the practice answer key (counts only): 192 files must be sanitized, 8 may be either sanitized or quarantined. Entities: PATIENT_NAME 962, MRN 850, PHONE 308,
RELATIVE_NAME 232, VILLAGE 150, HOUSE 136, PIN 136, DOB 111, LOCALITY 103, AADHAAR 71, LANDMARK 64, ABHA_NUMBER 46, PAN 22, INSURANCE_ID 22, AADHAAR_MASKED 16, CANARY 4, EMAIL 1.
Hiding places: content 3115, filename 48, metadata 40, key 12, base64 11, header 8. Scripts: latin 2980, deva 143, hinglish 111.

## 3. Input formats
CSV, TSV, nested JSON, FHIR R4 Bundles, TXT; encodings UTF-8, UTF-8 with BOM, UTF-16, cp1252; unsupported or broken files: XML, PDF, JPEG, truncated JSON, invalid UTF-8,
zero-byte file, a 1,500-level-deep JSON, JSON behind a `.csv` extension, base64 "scanned" forms. File names contain PII (names, phone numbers, UHIDs). PII also hides in JSON keys,
CSV headers, export metadata such as `source_path`, FHIR narrative text and base64 attachments. The input is a read-only copy and is re-hashed after the run.

## 4. Exact output contract (docs/SPEC.md)
```
{output}/
  sanitized/       REQUIRED  mirror of the input tree: SAME relative paths, SAME format, UTF-8
  report.json      REQUIRED  schema "raksha-report/1": files[] (input_sha256, output, status, reason), counts{...9 keys}, entities{}, timing.seconds, resources.peak_rss_mb
  records.jsonl    REQUIRED for identity credit: one line per patient-bearing record: {"file","loc","patient"[, "out","status"]}
  logs/            optional, scanned for PII
  quarantine/      optional, NOT scanned, NOT part of the release
```
- `raksha.toml` at the REPO ROOT: `[submission] name, setup (optional, network allowed, 30 min), run (required, NO network, contains {input} and {output})`.
- Rules for `sanitized/`: same relative path (rename a file only if its name has PII, and declare it in `report.json` under its `input_sha256`); CSV keeps delimiter, header
  (rename a header only if it has PII) and row count; JSON keeps structure and value types; FHIR stays a valid R4 Bundle whose references resolve; never copy a file you could not
  process (quarantine it instead).
- `report.json`: every input file listed by SHA-256 (never by name); status `sanitized | quarantined | suppressed`; counts are cross-checked against what was really exported.
- `records.jsonl` locators: CSV/TSV `row:N` (0-based, header excluded); JSON an RFC 6901 pointer such as `/visits/3`; text, FHIR bundle and single-object JSON `doc`.
  `patient` is our pseudonym, or `null` when we deliberately do not link. The pseudonym must also appear INSIDE that exported record (e.g. a `patient_ref` column or a `Patient:` line),
  otherwise no consistency credit and the attacker does not see it.
- Environment: `RAKSHA_INPUT`, `RAKSHA_OUTPUT`, `RAKSHA_SECRET` (per-release secret for pseudonyms and date shifts), `RAKSHA_CPUS`; offline flags for model hubs.
- Limits: Linux, 2 CPUs, 4,096 MB peak RSS (whole process tree), 15 minutes wall time per run, no network (connection attempts are logged for the judges and are grounds for
  disqualification). `TMPDIR` and `HOME` are private and scanned for PII after the run. Sandbox hides truth, attacker data, seeds, other teams.

## 5. Scoring (docs/SCORING.md, scoring.toml)
`total = 100 x sum(weight x score) - penalties` (not floored at 0).
| Category | Pts | Score in [0,1] | Notes |
|---|---:|---|---|
| Detection | 20 | F2 (recall weighted 2x) of contextual precision and recall; recall = 0.5 x macro by type + 0.5 x macro by script (latin, deva, hinglish) | meaning traps: doctors, `C/O fever`, `K/C/O`, `h/o`, wards, doses, `1-0-1`, eponyms, ASHA must survive |
| Identity | 15 | 0.4 pairwise F0.5 + 0.3 B-cubed F1 + 0.1 language trap + 0.1 fragmented trap + 0.1 homonym separation | no pseudonyms in `records.jsonl` = 0 for the whole category |
| Privacy | 25 | (1 - attack risk) x min(1, utility / 0.40) | attacks A1 direct exposure, A2/A3 registry linkage, A4 profile re-identification, A5 targeted (known visit dates, rare disease, length of stay; recovers a GLOBAL date shift), A6 pseudonym inversion (unkeyed hashes), A7 cross-release linkability (needs different shifts for a different secret) |
| Utility | 20 | probes 0.35, temporal 0.20 (all intervals and LOS exact), generalization 0.10 (age exact 1.0, 5-year band 0.9, 10-year 0.8; a band that excludes the true age = 0), statistics 0.15, token retention 0.10, record retention 0.10 | over-redaction and dropping records are punished |
| Integrity | 10 | format validity 0.15, schema preservation 0.20, FHIR validity 0.15, pseudonym consistency 0.10, channel hygiene 0.15 (7 side channels), quarantine handling 0.15, report quality 0.10 | |
| Performance | 10 | reliability 0.30, wall time 0.30 (60 s good, 900 s limit), peak memory 0.20 (512 MB good, 4,096 MB limit), determinism 0.20, scaling 0.15 | |
Penalties: each unique direct identifier or full name surviving anywhere -1 (cap -25); each canary found anywhere (content, filenames, report, logs, stdout/stderr, temp) -3 (cap -15);
each unsupported/malformed PII file copied raw into `sanitized/` -5 (cap -20); exit 0 with missing report or silently dropped inputs -10; modifying the input -5.
Reference points: delete everything about 20; starter about 8; copy everything below 0; organisers' reference about 79 on practice data and about 50 on an unseen-format dataset.
Ties: a team ranks above another only if it is more than 1 point higher on every hidden dataset.

## 6. How to run each checker
From `hackathon/` (kit and our repo side by side):
```
# 1) the contract (needs our run to have produced OUT)
python Secret-Wards-ToolKit/validate_output.py --input Secret-Wards-ToolKit/dev/input --output OUT       # must print CONTRACT OK
# 2) how good is it (uses the practice answer key; --show N prints N leak examples: they are synthetic but do not paste them into docs)
python Secret-Wards-ToolKit/check_dev.py --output OUT
# 3) pre-submit: raksha.toml, README, PDF, requirements; --run runs our command 3 times (contract, identical repeat, different secret, secret never written, input untouched)
python Secret-Wards-ToolKit/check_submission.py --repo secret-wards --run
```
Caveats found by reading and running them: `check_submission.py` looks for `.venv/bin` (Linux layout), so on Windows it will not put our venv first on PATH; its PDF check scans the whole repo
folder including ignored `data/` (a stray PDF there gives a false "found"); `validate_output.py` crashes with a Python error if `report.json["files"]` is not a list; `check_dev.py` counts a
record we never exported as "not leaked", so heavy quarantining looks good there but is punished officially (record retention, schema preservation).

## 7. Real results today (2026-11-26, measured by running; commit `main` a0d5254)
| Run on `dev/input` | Result |
|---|---|
| Kit starter as shipped | exit 0; `validate_output.py`: CONTRACT OK; `check_dev.py`: 84.1% of 3230 entities leaked (names 94.7%, MRN 96.1%, relatives/village/house/PIN/DOB/locality/landmark 100%), 4 of 4 canaries found, medical values kept 100%, linking 0, raw copies 0. Matches the kit's "about 8/100". |
| Our current pipeline (`python -m secretwards run`) | runs in 8 s, no crash; 6 files quarantined (1 empty, 2 unreadable, 3 unsupported); **leak gate quarantined 382 of 1,209 records (32%)**; writes `deidentified/`, `deidentified.json`, its own `report.json`: NOT the contract layout. |
| `validate_output.py` on our output | **fails** (Python error: our `report.json["files"]` is an object, not a list). The contract is NOT met: no `sanitized/` tree, no per-file SHA-256 report, no `records.jsonl`, no `raksha.toml`. |
| `check_submission.py` (static) on our repo | **FAIL: raksha.toml missing.** README ok, requirements ok, no `config/policy.yaml`. |
| `check_dev.py` on a throwaway adapter that mirrors our per-file outputs into `sanitized/` (measurement only, 173 of 200 files mirrored) | 153 of 3230 entities leaked (4.7%): PAN 95.5% (we have no PAN detector), AADHAAR 31%, MRN 8.7%, VILLAGE 12%, PATIENT_NAME 0.9%, PHONE 1.9%, LOCALITY 2.9%, everything else 0%. By place: filename 100% (artefact of the mirror using input names), metadata 37.5%, base64 10%. Canaries 1 of 4 (may be the filename artefact). **Medical values kept 77.8% (3532 of 4542)** because quarantined records vanish. Linking not measurable (no `records.jsonl`). |
Official score today: not computable. With the contract missing the organisers' run would score us as a failed/false-success run. After the contract adapter (plan below) the expected range on practice data is a guess, not a measurement.

## 8. Conflicts between the kit and our docs / code (each needs a decision or a fix)
| # | Kit says | We have | Impact |
|---|---|---|---|
| 1 | Run via `raksha.toml` `run` with `{input}` `{output}`; secret in `RAKSHA_SECRET` | `python -m secretwards run --in --out --config`; keys read from `keys/*.key` made by `keygen` | On the organiser machine there is no `keys/`: we must derive all four sub-keys from `RAKSHA_SECRET` (HKDF) and drop `keygen` for the run |
| 2 | `sanitized/` mirrors input paths and formats | `deidentified/fNNNN.*` with hashed names; XLSX becomes CSV per sheet | Contract fails; paths must be kept (rename only PII names, declare in report) |
| 3 | CSV: same header, columns and row count | we add a `pseudonym` column, hash "unknown" headers, drop quarantined rows | schema preservation and record retention lose points; use an existing id column or a `Patient:` line instead; never drop rows |
| 4 | JSON: same structure and value types | we add a `pseudonym` key, hash unknown keys, replace values with `[NAME]` | key-path Jaccard and type checks; typed fields (ints, dates) must stay valid |
| 5 | FHIR stays a valid R4 Bundle, references resolve, dates valid | we flatten JSON and write placeholders like `[DATE]`, `[ID]` | FHIR validity 1.5 pts and utility; we need a FHIR-aware sanitizer (not an exporter): keep ids and references consistent, shift dates in valid syntax |
| 6 | `report.json` with `files[]` by SHA-256, `counts` (9 keys), `entities`, timing, resources | ours is a different shape with no hashes | report quality, and `validate_output.py` crashes |
| 7 | `records.jsonl` with `row:N`, JSON pointers, `doc` | none | identity credit (15 pts) is 0 until written; our `ordinal` counts a preamble row, JSON pointers are not tracked |
| 8 | Unlinked records may be `null`; wrong merges cost most | every record gets a pseudonym (singletons too) | fine for false merges; but the pseudonym must be present inside the record |
| 9 | Hidden places: file names, headers, keys, metadata (`source_path`), FHIR narrative, base64 attachments | we hash names/keys; no base64 decoding; no metadata rules | metadata leaked 37.5%, base64 10% on the practice mirror |
| 10 | Entity types include AADHAAR (12 digits, masked), PAN, VILLAGE, LOCALITY, HOUSE, LANDMARK, DOB, relative names | no PAN, partial Aadhaar, weak village/locality | PAN 95% and Aadhaar 31% leaked |
| 11 | Dropping records or files is punished (record retention, schema, silent drop -10) | the leak gate quarantines whole records | must redact in place; quarantine only whole unprocessable files |
| 12 | Privacy is judged by THEIR attacker (registry + known facts, A1-A7), relative to the raw data | our own self-made attack | build a stand-in attacker from `dev/attacker/` (Jaisheel) and tune against it |
| 13 | A7: a different `RAKSHA_SECRET` must change pseudonyms AND date shifts | pseudonyms and shifts come from key files | fine once keys derive from the secret; add a test |
| 14 | Generalization utility: age 5-year band 0.9, exact 1.0; village to tehsil/district 0.7-0.8 | k-anonymity ladder often gives "18-59" | utility vs privacy re-tuned against their formulas |
| 15 | Leak counting normalises homoglyphs, zero-width, Indic digits, decodes base64/hex/entities | we normalise Indic digits and zero-width only | a disguised name still counts as a leak |
| 16 | Submission = PUBLIC GitHub repo + 2-page PDF brief; last commit at the deadline is frozen | our repo is private; no brief | make the repo public before the deadline; write the brief (template in `toolkit/brief/`) |
| 17 | Official statement: "hospitals in Yugaantar Pradesh", 4 hospital systems, attacker; our PROBLEM_ORIGINAL says "five hospitals", ten years, no attacker/contract | | `PROBLEM_ORIGINAL.md` is superseded for contract questions; do not edit it |
| 18 | Linux 2 CPUs, 15 min, 4 GB; `setup` with network, `run` offline | developed and tested on Windows, single process, 100 tests | must run the contract path on Linux (CI) and re-time on hidden-size data; fix the quadratic large-file bug first |
| 19 | Synthetic data generator unknown/sealed | our `synth/` models our own guesses | keep `synth/` for regression only; tune on practice data without hardcoding, test on renamed/varied copies |
| 20 | `python main.py` at repo root is the template | package `src/secretwards` | add a thin `main.py` + `raksha.toml` that call the package; keep `src/` layout |

## 9. Submission checklist (from START_HERE section 8 and check_submission.py)
- [ ] `check_submission.py --repo . --run` prints READY TO SUBMIT  - [ ] `raksha.toml` at repo root, real team name, `run` has `{input}` and `{output}`
- [ ] `validate_output.py` prints CONTRACT OK  - [ ] same secret twice gives byte-identical `sanitized/` and `records.jsonl`; a different secret changes pseudonyms and dates
- [ ] nothing personal in stdout, stderr, logs, temp files, `report.json`; `RAKSHA_SECRET` never written  - [ ] finishes within 15 minutes on 2 CPUs and 4 GB
- [ ] no LLMs, no model above 50M parameters, any model declared in README  - [ ] README: setup, architecture diagram, how each part works, security design, limitations
- [ ] 2-page Project Brief PDF committed (e.g. `docs/brief.pdf`) with measured numbers  - [ ] tested on data we did not tune on (renamed columns, new names, new date formats)
- [ ] repo is PUBLIC and the last commit before the deadline is the one we want judged

## 10. Where each fact lives
`toolkit/START_HERE.md` (plain-words guide), `toolkit/docs/SPEC.md` (contract), `SCORING.md` + `scoring.toml` (every formula), `ATTACKS.md`, `DATASET.md`, `SANDBOX.md`, `FAIRNESS.md`, `FAQ.md`, `PROJECT_BRIEF.md`.

## 11. Plan to meet the contract (ordered by points and penalties). WAITING FOR THE LEAD'S OK before any code change
| Step | What | Why first | Owner | Hours |
|---|---|---|---|---|
| P0 | Contract adapter: `raksha.toml`, root `main.py`, keys derived from `RAKSHA_SECRET`, mirror writer for `sanitized/`, in-place redaction (no dropped rows, no hashed headers), SHA-256 `report.json`, `records.jsonl`, exit codes, atomic output; stop quarantining records | without it every category is 0 and the -10 false-success and -20 raw-copy penalties are live | Saiteja | 8 |
| P1 | Fix gate over-quarantine and quadratic merge; Linux run in CI | penalties, reliability, time | Saiteja | 4 |
| P2 | New detectors from the practice types: Aadhaar (12 digits, masked), PAN, village/locality/house/landmark by context and by column, DOB; base64 decode and clean; metadata and key rules; file-name sanitising; Devanagari/Hinglish relatives | detection 20 + leaks -1 each + canaries -3 each | Jaisheel | 12 |
| P3 | FHIR-aware sanitizer (valid R4, references resolve, valid dateTime after shifting) and JSON type preservation | integrity 10 and every JSON/FHIR file | Jaisheel | 6 |
| P4 | Stand-in attacker from `dev/attacker/` (A1-A5), tune generalization and rare-value suppression against it; shift defence against global-shift recovery | privacy 25 + utility coupling | Jaisheel | 8 |
| P5 | Identity: write pseudonym inside records, link through ids/name+relative, null when weak; homonym tests from `truth.traps` | identity 15 | Saiteja | 5 |
| P6 | Security and honesty: no side-channel leaks, report cross-checks, encryption of any intermediate (we write none), PII-free logs test on the contract path | integrity, canaries | Saiteja | 5 |
| P7 | README, 2-page PDF brief with measured numbers, public repo, `check_submission.py --run` green on Linux | submission eligibility | Saiteja | 5 |
Total about 53 hours across two people: Saiteja about 27 hours (P0, P1, P5, P6, P7), Jaisheel about 26 hours (P2, P3, P4). Estimates, not measurements. Details: `docs/FRIEND_TASKS.md`.
