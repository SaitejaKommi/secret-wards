# Progress

Newest log entry on top. Repo: https://github.com/SaitejaKommi/secret-wards (public). Single branch `main`; these docs live in `docs/` (to be deleted after the hackathon).
Team tasks and setup: see `FRIEND_TASKS.md`. Figures below were measured by running the code on synthetic data; they do not predict the hidden set.

## READ FIRST: official kit changes the target (2026-11-26)
The organisers' kit (https://github.com/Reinforce-SST/Secret-Wards-ToolKit, copy of its docs in `toolkit/`, analysis in `TOOLKIT.md`) defines a strict contract: `raksha.toml`, `main.py`,
`RAKSHA_SECRET`, `sanitized/` mirror, `report.json` with SHA-256 per input file, `records.jsonl`. **P0 is done (branch `feat/contract`): `python main.py --input DIR --output DIR` with `RAKSHA_SECRET` now writes the contract output and the kit's `validate_output.py` prints CONTRACT OK.**
Plan P0-P7 and every conflict are in `TOOLKIT.md`. Status: P0 contract adapter [x]; P1 gate over-quarantine [x], quadratic merge on one big file [ ]; P2 India IDs + address fields [x] (Jaisheel, PR #1), hidden places [x] (PR #2/#3);
P3 FHIR-aware sanitizer [ ] (Jaisheel; hospital names in FHIR bundles are still redacted, 19 of 19 lost); P4 stand-in attacker + tuning [ ] (Jaisheel); P5 identity in `records.jsonl` [ ] (Saiteja; recall 0.61);
P6 channel hygiene + security design [ ] (Saiteja); P7 README + 2-page brief [ ] (Saiteja; repo is already public). Team is two people (Saiteja, Jaisheel).

### Official practice data, kit checkers (`RAKSHA_SECRET=practice`; kit cloned with LF endings: all 200 files match the key hashes)
| Run | validate_output | Leaked | Hiding places leaked (filename / metadata / base64 / key / header) | Canaries | Medical kept | Link P / R / F0.5 | Wrong merges | Time / RAM |
|---|---|---|---|---|---|---|---|---|
| Kit starter as shipped | OK | 84.1% | 100 / 100 / 100 / 100 / 100% | 4 of 4 | 100% | 0 / 0 / 0 | 0 | - |
| Ours, P0 alone (`main` code of PR #3 absent) | OK | 6.4% | 42 / 38 / 100 / 0 / 0% | 1 of 4 | 89.9% | 1.00 / 0.37 / 0.74 | 1 | - |
| + Jaisheel PR #1 (India ids, address fields) + my rule fixes | OK | 1.6% | 0 / 50 / 100 / 0 / 0% | 1 of 4 | 98.0% | 1.00 / 0.61 / 0.89 | 0 | - |
| **+ Jaisheel PR #2/#3 (hidden places)** | **OK** | **0.2% (5 of 3,230; all HOUSE)** | **0 / 0 / 0 / 0 / 0%** | **0 of 4** | **98.0%** (4758 of 4855) | **1.00 / 0.61 / 0.89** | **0** | **6.5 s / 63 MB** |
7 files quarantined (all marked "either" in the key); 817 records; our locators cover 812 of the key's 815 record units. Tests: 343 passed, 7 expected failures.
`check_dev.py` does NOT measure: the organisers' attacker (privacy is 25 points), date-interval and age-band truthfulness, FHIR validity, determinism, side channels. Still open: hospital names in FHIR (19 of 19 lost) and FHIR validity, 5 house-number leaks, linking recall 0.61, coarse age bands ("18-59") that cost utility, one large text file takes quadratic time.

## Core (Saiteja)
- [x] M0 Skeleton, contracts (unchanged since M2), config, key handling, git repo (`main` @ 3e900b3)
- [x] M1 Synthetic generator (dev / heldout / blind splits) with gold labels; scorer
- [x] M2 End-to-end slice: CSV / TSV / JSON / JSONL / TXT / XLSX in; CSV / JSON / TXT out; report; quarantine
- [x] M3 Normalization with offset map, transliteration, gazetteers, medical guard, dataset-level name memory
- [x] M4 Linkage and keyed pseudonyms
- [x] M5 Date shift, generalization, own attack, leak gate
- [x] P0 contract adapter (2026-11-26, `feat/contract`): `main.py`, `raksha.toml`, `contract/` (readers, writers, renamer, run), keys from `RAKSHA_SECRET`, atomic cleanup, 11 contract tests
- [x] Audit fix: gate over-quarantine (id-shaped values only, repair-only mode, doctors exempt, weak guesses never become dataset-wide rules); medical history, lab tests, departments, district kept (general rules, `tests/test_meaning_traps.py`)
- [ ] Audit fixes still open: quadratic merge on one big text file, same-name merges when phones differ (none seen on the practice data), non-atomic legacy output (the contract path is atomic)

## Teammates
- [ ] Jaisheel (steps 1 and 2 DONE and merged: PR #1, PR #2/#3; branches `feat/detection`, `feat/hidden`; next `feat/fhir`, `feat/attacker`): India ID / address-field / hidden-place detectors, FHIR sanitizer, stand-in attacker and tuning, diagnosis key, CRF last (docs/FRIEND_TASKS.md section 5)
  - [x] Step 1 (2026-11-26, `feat/detection`): `detect/india_ids.py` (Aadhaar full/masked, PAN, hospital numbers by shape + label; only patient-id cues outside doctor/facility context are typed MRN, everything else ID so it is redacted but never links) and `detect/address_fields.py` (village/locality/house/landmark by column meaning and label; municipal vs hospital ward). Practice data via `adapt_for_checkdev.py`: leaked 152 -> 69 of 3230 (4.7% -> 2.1%); Aadhaar 31% -> 0, PAN 95.5% -> 0, MRN 8.6% -> 6.4% (all remaining MRN leaks are filename/metadata, step 2), village 12% -> 0 (14.7% between the two commits: records the gate no longer quarantines became visible), locality 2.9% -> 0; content channel 2.8% -> 0.0%; deva 7.0% -> 0. Medical kept 78.1% (3532/4521) -> 78.6% (3566/4537; denominator grows because 2 more files are mirrored); records out 825 -> 852 of 1209; `clean/` placeholders 6 -> 6; largest cluster 24 -> 33 (largest true patient 36). Synthetic dev and blind unchanged. Link vs truth on the same 75 files / 322 units (own measurement script): precision 1.000 -> 1.000, recall 0.457 -> 0.708, wrong merges 0. Run time on practice data 4.6 s -> 5.1 s. Tests 100 -> 247 (+5 strict xfail recording pre-existing false positives in the lead's `detect/address.py` and `detect/rules.py`).
  - [x] Step 2 (2026-11-26, `feat/hidden`, stacked on step 1): `detect/hidden.py`: path-like metadata (whole PII component), encoded runs (base64/hex/\u/entities, decoded then redacted if PII), homoglyph folding; helpers for the contract writer `sanitize_path`, `safe_label`, `clean_encoded` (keeps base64 valid). Practice data via `adapt_for_checkdev.py` (now renames paths and declares every file): leaked 69 -> 0 of 3230; filename 100% -> 0, metadata 50% -> 0, base64 10% -> 0; canaries 1/4 -> 0/4. This 0 does NOT count the 357 records our gate quarantines, so also measured WITHOUT the gate (all detectors on every record of 194 ingested files): leaks main 212/3173 (6.7%) -> step 1 72 (2.3%) -> step 2 22 (0.7%: names 15, house 5, relatives 2, all running text); canaries 1 -> 0. Rename precision vs truth: 39/39 files with PII renamed, 0 unneeded renames; labels 16 flagged, 0 false, 20/20 key/header entities caught (keys/headers read 0% today only because the pipeline hashes all unknown headers). Medical kept 3566/4537 unchanged; `clean/` placeholders 6 -> 6; link precision 1.000; synthetic dev unchanged; run time 5.1 s -> 5.5 s; tests 247 -> 326 (+7 xfail; non-strict ones: an unseen lowercase name in a file name, a known limit of `detect/names.py`, and an eponymous hospital name in a file name read as a person). Probed with invented unseen shapes: First.Last.txt, IPD.2025.00412.txt, hyphen and camelCase names renamed; city/district stems, dated backup folders, .tar.gz kept.
  - [x] Step 3 (2026-11-26, `feat/traps`, stacked on Saiteja's P0 PR #4; measured with the real contract run `main.py` + kit checkers): Hindi/Hinglish house numbers without a colon (`Makan No. N`, `मकान नं. N`) in `detect/address_fields.py`; new `detect/diagnosis.py` canonical diagnosis key (ICD-10 code when written, so English and Hindi names of one disease group together) and whole-entry extent, used by `privacy/generalize.py` so a suppressed diagnosis no longer leaves its ICD code (`[RARE DIAGNOSIS].1)`, `[RARE DIAGNOSIS], unspecified (D..)`). Practice data: CONTRACT OK; leaked 5 -> 0 of 3230 (HOUSE 3.7% -> 0); canaries 0/4; medical kept 4758 -> 4757 of 4855 (98.0%; whole-entry suppression now also hides the code of a truly rare diagnosis); `[RARE DIAGNOSIS]` 11 -> 9; linking P 1.00 R 0.61, 0 wrong merges; `clean/` placeholders 2 -> 2; deterministic rerun identical; 5.6 s, 57 MB. Synthetic dev and blind identical to PR #4. Tests 343 -> 361 (+7 xfail). Remaining 98 lost medical values, by cause: 52 gate blanks whole text fields because a 'Registration Date' column is typed MRN (`rules.py`/`headers.py`, reported on PR #4), 19 FHIR (step 4), 18 rare-diagnosis suppression (step 6), 7 district columns (`address.py`/`names.py`, reported), 2 ASHA -> NAME (`names.py`, reported).
  - [ ] Step 4 FHIR sanitizer, steps 5-7.
- [ ] Saiteja (P0 and P1-gate DONE on `feat/contract`; next `feat/identity`, `feat/hygiene`): contract adapter, gate and merge fixes, identity in records.jsonl, hygiene and security, README, brief (section 6)

## Metrics (synthetic; fresh seeds 991 / 992 / 993, audit of 2026-11-26)
Leak = share of gold PII strings still in the same record's output. Medical kept counts a generalized age as kept when its band holds the true age.

| Date | Commit | Set (records) | PII recall | PII precision | Leak rate | Medical kept | Exact age kept | Link P | Link R | Same-name pairs merged | Canary leaks |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-11-26 | 3e900b3 | dev (1013) | 0.997 | 0.995 | 0.11% | 0.988 | 0.13 | 0.983 | 0.962 | 2/36 | 0/23 |
| 2026-11-26 | 3e900b3 | heldout (1008) | 0.997 | 0.996 | 0.16% | 0.989 | 0.26 | 1.000 | 0.857 | 0/34 | 0/23 |
| 2026-11-26 | 3e900b3 | blind (1390) | 0.995 | 0.977 | 0.32% | 0.992 | 0.42 | 0.996 | 0.597 | 0/48 | 0/23 |

Own attack (exact age, sex, PIN, diagnosis known): raw 99-100% uniquely matched; release 11-15% (100-250 patients), 0.8% at 1500 patients; blind figure rests on 24 patients, ignore it.
Scale: 5,200 records in about 22 s; 15,000 records in 215 s on a Windows machine where file opens cost about 10 ms; peak RAM about 250 MB for 8,400 records.
Tests: 100 passed.

## Hand probes (adversarial, made-up values; 22 cases): 17 passed, 5 failed
Leaked: unseen lowercase name without cue; unseen Devanagari name without cue; phone "9 8 7 6 5 0 1 2 4"; phone "(98765) 01240"; "policy no X" without a colon.
Removed correctly: Title Case unseen names, names after Mr / bed-list / kin terms, 8 other phone formats, e-mails incl. "at/dot", unusual dates, villages and society addresses, ABHA and short reg numbers.

## What is NOT done
FHIR-aware sanitizing (the kit needs valid FHIR in place, not an export; hospital names in bundles are still lost); encryption at rest (key and vault exist, unused; the pipeline writes no raw or intermediate data to disk, only redacted outputs); audit trail; access separation;
technical report; CRF; stronger attack. Exact ages kept for only 13-42% of records (diagnosis spelling variants fragment the privacy groups).

## History of bad numbers (kept on purpose)
- First M2 slice, held-out names: name recall 0.877, name leak 10.2%, 2 canary leaks.
- M4 at 1500 patients: link precision 0.927 (7 of 161 same-name pairs merged) before the relative-name rule; now 1 of 161.
- A canary leaked through our own debug file `eval_spans.json` (raw column headers); now keyed by hash.
- Leak gate erased the word "continue" 512 times (detector false positive amplified by the gate); lexicon extended.
- Audit 2026-11-26: leak gate quarantined 20 of 1034 records on fresh dev seed 991; 3 wrong clusters (2 same-name twins, 1 coincidence); a 106 KB text file takes about 15 s.

## Generator gold corrections (labelling bugs, not score tuning)
1. TXT gold offsets: Windows `write_text` added `\r\n`; files are now written as exact bytes.
2. WhatsApp timestamps were dates but unlabelled: now `DATE`.
3. Lab "Sample ID" is an identifier but was unlabelled: now `ID`.

## Decisions waiting for Saiteja
1. Age accuracy versus attack resistance: `qi_include_dx` (true: exact age 38%, unique-match 0.8%; false: exact age 82%, unique-match 59%, at 1500 patients).
2. Real run: put `keys_dir` outside the project folder.

## Log
**2026-11-26 audit + first commit.** Re-ran everything on fresh seeds, wrote adversarial probes, found the issues above; created the git repo (docs later merged into `main` under `docs/`); wrote `FRIEND_TASKS.md`; README matches reality.
**2026-11-26 M5 / M4 / M3 / M2 / M1 / M0.** See `ARCHITECTURE.md` for the design as built.
**2026-11-26 toolkit.** Cloned the official kit next to the repo and read all of its docs and code before running anything. Ran the starter (CONTRACT OK, 84.1% leaked), our pipeline (no crash, wrong layout, 382 records quarantined by our own gate), `validate_output.py` (crashes on our report), `check_submission.py` static (raksha.toml missing), and `check_dev.py` through a measurement-only adapter (4.7% leaked, 77.8% medical kept, linking not measurable). Wrote `TOOLKIT.md`, copied the kit docs to `toolkit/` (no data/truth/attacker), re-split `FRIEND_TASKS.md` around the contract. No source code changed.
**2026-11-26 P0 + merges.** Built the contract path (`python main.py`), reviewed and merged Jaisheel's PR #1 (India ids, address fields) and PR #2 (hidden places; it was stacked, so it needed a second PR #3 to reach `main`). Review caught practice ids quoted in a comment (replaced with invented ones) and one practice date in a test. Found that this machine's `core.autocrlf=true` had rewritten 172 of the kit's 200 files (hashes no longer matched the key): re-cloned with `-c core.autocrlf=false`. The answer key then showed real over-redaction (history `K/C/O ...` read as a relative, `x 9 yrs` rewritten as an age band, "Test Name" columns read as person names, specialties as names, districts redacted, a stray low-confidence name poisoning the leak gate): fixed with general rules, medical kept 89.7% -> 98.0%. Combined with Jaisheel's detectors: 0.2% leaked, 0 of 4 canaries, CONTRACT OK, 6.5 s.
