# Progress

Newest log entry on top. Repo: https://github.com/SaitejaKommi/secret-wards (public). Single branch `main`; these docs live in `docs/` (to be deleted after the hackathon).
Team tasks and setup: see `FRIEND_TASKS.md`. Figures below were measured by running the code on synthetic data; they do not predict the hidden set.

## READ FIRST: official kit changes the target (2026-11-26)
The organisers' kit (https://github.com/Reinforce-SST/Secret-Wards-ToolKit, copy of its docs in `toolkit/`, analysis in `TOOLKIT.md`) defines a strict contract: `raksha.toml`, `main.py`,
`RAKSHA_SECRET`, `sanitized/` mirror, `report.json` with SHA-256 per input file, `records.jsonl`. **Our code does not meet it yet** (measured: `validate_output.py` crashes on our report; `check_submission.py` fails on
missing `raksha.toml`; our leak gate quarantined 382 of 1,209 records on the practice data). Plan P0-P7 and every conflict are in `TOOLKIT.md`. Official numbers on the practice data (kit starter): CONTRACT OK, 84.1% leaked.
Status of the plan (lead OK needed before code changes): P0 contract adapter [ ], P1 gate + quadratic merge [ ], P2 India IDs / address fields / hidden places [ ] (Jaisheel), P3 FHIR-aware sanitizer [ ] (Jaisheel),
P4 stand-in attacker + tuning [ ] (Jaisheel), P5 identity in `records.jsonl` [ ] (Saiteja), P6 channel hygiene + security design [ ] (Saiteja), P7 README + 2-page brief + public repo [ ] (Saiteja). Team is two people now (Saiteja, Jaisheel); the third friend is busy.

## Core (Saiteja)
- [x] M0 Skeleton, contracts (unchanged since M2), config, key handling, git repo (`main` @ 3e900b3)
- [x] M1 Synthetic generator (dev / heldout / blind splits) with gold labels; scorer
- [x] M2 End-to-end slice: CSV / TSV / JSON / JSONL / TXT / XLSX in; CSV / JSON / TXT out; report; quarantine
- [x] M3 Normalization with offset map, transliteration, gazetteers, medical guard, dataset-level name memory
- [x] M4 Linkage and keyed pseudonyms
- [x] M5 Date shift, generalization, own attack, leak gate
- [ ] Audit fixes (all still OPEN, verified by re-running on 2026-11-26): gate over-quarantine, quadratic merge, atomic output, phone/ID gaps, same-name merges

## Teammates
- [ ] Jaisheel (branches `feat/detection`, `feat/fhir`, `feat/attacker`): India ID / address-field / hidden-place detectors, FHIR sanitizer, stand-in attacker and tuning, diagnosis key, CRF last (docs/FRIEND_TASKS.md section 5)
- [ ] Saiteja (branches `feat/contract`, `feat/identity`, `feat/hygiene`): contract adapter, gate and merge fixes, identity in records.jsonl, hygiene and security, README, brief (section 6)

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
The whole output contract (see top); FHIR-aware sanitizing (the kit needs valid FHIR in place, not an export); encryption at rest (key and vault exist, unused; the pipeline writes no raw or intermediate data to disk, only redacted outputs); audit trail; access separation;
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
