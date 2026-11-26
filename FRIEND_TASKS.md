# Secret Wards: team guide (read this first)

Track 3 of DevForge. Repo: https://github.com/SaitejaKommi/secret-wards. Lead: Saiteja Kommi. Friend A: detection and attack. Friend B: FHIR, security, report, brief.

**STEP 0 for every person and every AI tool: read `docs-wt/TOOLKIT.md` before anything else.** The organisers released an official kit with a strict output contract
(`raksha.toml`, `main.py`, `RAKSHA_SECRET`, `sanitized/`, `report.json`, `records.jsonl`). Our code does not meet it yet. TOOLKIT.md lists every conflict and the plan (P0-P7).
Never hardcode names or values from the practice data or its answer key. Never commit the kit's `dev/` folder (practice data, truth, attacker).

## 1. What the project does (5 lines)
1. It reads messy hospital files (CSV, TSV, JSON, FHIR bundles, TXT; UTF-8, BOM, UTF-16, cp1252) in English, Hindi and Hinglish. Broken files are quarantined, never copied raw.
2. It finds personal data (names, relatives, phones, Aadhaar, PAN, ABHA, MRN, addresses, dates) in cells, keys, headers, file names, metadata and free text, and removes it, but keeps medicines, doses, vitals, labs and diagnoses exactly.
3. It decides which records are the same patient (never by name alone) and gives each patient one keyed pseudonym (from `RAKSHA_SECRET`).
4. It shifts dates per patient, generalizes age and place only where needed, and checks risk against an attacker that holds a voter-style registry.
5. It writes `sanitized/` (same paths and formats as the input), `report.json` and `records.jsonl`. No LLMs, no network, 2 CPUs, 4 GB, 15 minutes, same input and secret give the same bytes.

**Data flow today (our code):** `ingest -> normalize -> detect -> name memory -> link -> pseudonymize -> generalize -> render -> leak gate -> export`.
**Data flow needed (contract):** the same stages, then a *contract writer* that mirrors the input tree into `sanitized/`, redacts in place (no dropped rows, no new columns), writes SHA-256 `report.json` and `records.jsonl`.
Stages talk only through `src/secretwards/contracts.py` (ask the lead before changing it).

## 2. Setup from a fresh clone (Python 3.11 needed)
Windows (PowerShell):
```
git clone https://github.com/SaitejaKommi/secret-wards.git
cd secret-wards
python -m venv .venv          # must be Python 3.11; if you have the py launcher: py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
python -m secretwards keygen
python -m synth --split dev --seed 1 --n 150
python -m secretwards run --in data/synth/dev/in --out out/dev --emit-spans
python -m eval --gold data/synth/dev/gold.json --out out/dev
python -m pytest -q
```
Linux / macOS: same, but `python3.11 -m venv .venv`, `source .venv/bin/activate`.
**Official kit (next to the repo, not inside):**
```
cd ..                                             # folder that contains secret-wards/
git clone https://github.com/Reinforce-SST/Secret-Wards-ToolKit.git
$env:RAKSHA_SECRET="practice"                     # PowerShell;  Linux: export RAKSHA_SECRET=practice
python Secret-Wards-ToolKit/starter/main.py --input Secret-Wards-ToolKit/dev/input --output secret-wards/out/starter
python Secret-Wards-ToolKit/validate_output.py --input Secret-Wards-ToolKit/dev/input --output secret-wards/out/starter   # CONTRACT OK
python Secret-Wards-ToolKit/check_dev.py --output secret-wards/out/starter                                                # about 84% leaked: expected
```
Once the lead merges P0, our own run is `RAKSHA_SECRET=practice python main.py --input ../Secret-Wards-ToolKit/dev/input --output out/ours` followed by the same two checkers.
Docs worktree: `git worktree add docs-wt docs`. Always run on an input folder, never on the folder holding answer keys. Expected: `100 passed`.

## 3. Real status (measured 2026-11-26; details in TOOLKIT.md section 7)
- Our synthetic data (own generator, does NOT predict the hidden set): PII recall 0.995-0.997, precision 0.977-0.996, medical kept 0.988-0.992, link precision 0.98-1.0, link recall 0.60-0.96, canaries 0/23.
- Official practice data, kit starter: CONTRACT OK, 84.1% leaked, 4/4 canaries, score about 8.
- Official practice data, our pipeline: **contract NOT met** (no `sanitized/`, no SHA-256 report, no `records.jsonl`, no `raksha.toml`); the leak gate quarantined 382 of 1,209 records.
  Through a measurement-only adapter our detection leaked 4.7% (PAN 95%, Aadhaar 31%, MRN 9%, village 12%, metadata 38%) and kept 77.8% of medical values (lost to quarantine). Linking not measured.
- Known bugs (lead): gate over-quarantine, quadratic time on one big text file, non-atomic output, a few phone/ID misses, same-name merges when phones differ.

## 4. Git workflow (everyone)
- Never commit to `main` directly. Friend A: branch `feat/detection`. Friend B: branch `feat/output-security`. Lead: `feat/contract` for P0.
- Commit from your OWN GitHub account (check `git config user.name` and `user.email` before the first commit; use your GitHub noreply email). Small commits, honest messages. Never rewrite or force-push shared history.
- Before every PR: `python -m pytest -q` green; run the scorer on dev and blind; once P0 is merged also run the kit's `validate_output.py` and `check_dev.py`; paste the numbers in the PR text.
- Update your rows in `docs-wt/PROGRESS.md` on the `docs` branch after each finished task (`cd docs-wt && git add -A && git commit && git push`).
- NEVER commit: `keys/`, `*.key`, `data/`, `out/`, `.venv/`, caches, the kit's `dev/`, any answer key or attacker file, anything that holds `RAKSHA_SECRET`. `.gitignore` covers most of it; read `git status` before every commit.

### Pull request steps (copy these)
```
git fetch origin
git checkout -b feat/detection origin/main        # Friend B: feat/output-security
# ... work, small commits ...
python -m pytest -q
git push -u origin feat/detection
gh pr create --base main --head feat/detection --title "short title" --body "what changed; test result; scorer numbers before/after"
```
- The lead adds you as a collaborator (GitHub repo, Settings, Collaborators). Accept the invitation, then clone.
- Keep your branch current with `git fetch origin && git merge origin/main`. Do not rebase or force-push anything already pushed.
- One topic per PR (under about 400 changed lines). Do not edit files owned by someone else (section 8). If you must, ask in the PR first. Only the lead merges to `main`.
- A PR that touches `src/secretwards/contracts.py` is not merged without the lead's explicit OK.
- Rules that cannot be broken: no LLMs or generative models, no model over 50M parameters (declare any model in README), no network at run time, deterministic output, fake data only,
  no PII or `RAKSHA_SECRET` in logs, errors, tests or docs, no hardcoding to our own or the practice names/values, fail closed (quarantine whole files you cannot clean; never drop records silently).
- New dependency: ask the lead, pin the exact version in `requirements.txt` and `pyproject.toml`. The run environment is Linux; check wheels exist.

## 5. Friend A: detection and attack (plan steps P2 and P4)
**Why:** detection is 20 points and every surviving identifier costs -1 (canary -3); privacy is 25 points and is judged by the organisers' attacker.
**Files you own (new files, to avoid conflicts):** `src/secretwards/detect/india_ids.py` (Aadhaar 12 digits with any separators/Devanagari digits, masked Aadhaar, PAN, ABHA, UHID/MRN styles, insurance),
`detect/address_fields.py` (village, locality/mohalla, house, landmark, PIN, tehsil/district, by context and by column meaning), `detect/hidden.py` (base64/hex/entity decoding, metadata and `source_path` rules, JSON keys, file-name PII),
`detect/diagnosis.py` (canonical diagnosis key), `privacy/attack.py` (stand-in attacker), `privacy/generalize.py` and `privacy/risk.py` (you own these), later `detect/crf/`. Register detectors only in `detect/__init__.py` `default_detectors()`. Tests: `tests/test_india_ids.py`, `tests/test_address_fields.py`, `tests/test_hidden.py`, `tests/test_attack.py`.
**Files NOT to touch:** `contracts.py`, `pipeline.py`, `main.py`, `contract/*`, `link/*`, `export/*`, `fhir/*`, `security/*`, `detect/rules.py`, `detect/merge.py`, `detect/names.py` (lead), `eval/*`.
**Steps in order:**
1. **Indian IDs and address fields** (biggest leaks today: PAN, Aadhaar, MRN, village, locality, metadata). Use `check_dev.py` per-type rows to prioritise. Write rules that understand *context* (a label, a column meaning), not lists of practice values: hidden data has unseen labels, column names and formats.
2. **Hidden places:** base64 attachments (decode, clean, re-encode), JSON keys, metadata, file names. Leak scoring decodes base64, hex, `\uXXXX`, entities and folds homoglyphs, so do the same when detecting.
3. **Meaning traps:** keep `Dr. <name>`, `C/O fever`, `K/C/O`, `h/o`, wards, doses, `1-0-1`, eponyms; remove relatives (S/o, W/o, C/O <name>).
4. **Stand-in attacker** in `privacy/attack.py` from the kit's `docs/ATTACKS.md` and `dev/attacker/` (registry linkage A2/A3, profile A4, targeted A5 with global-shift recovery, pseudonym inversion A6). Report risk raw vs sanitized in `report.json` under `privacy`.
5. **Tune generalization** against that attacker and the kit's utility formulas (5-year bands 0.9, village to tehsil/district 0.7-0.8, rare-value suppression only for rare combinations); diagnosis canonical key so groups stop fragmenting.
6. **CRF last** (`sklearn-crfsuite`, ask the lead first) for names with no cue; train only on our synthetic `dev` data and never on practice answers you will test on.
**Definition of done:** tests pass; on practice data PAN and Aadhaar leaks under 2%, village/locality/house/landmark under 5%, metadata and base64 under 5%, name leaks do not rise; medical values kept does not fall; the stand-in attacker shows a lower success than raw; numbers in the PR.

**Ready-to-paste prompt (Friend A):**
```
You are helping on the Secret Wards repo (hackathon Track 3: offline, LLM-free de-identification and record linkage for English/Hindi/Hinglish hospital records).
FIRST read CLAUDE.md, then docs-wt/TOOLKIT.md (the official kit and output contract), then docs-wt/FRIEND_TASKS.md section 5. I am Friend A (detection and attack). Work only on branch feat/detection.
Rules: no LLMs or generative models, no model above 50M parameters, no network at run time, deterministic output, fake data only, never hardcode names or values from the practice data or its answer key,
never commit keys/ data/ out/ .venv/ or the kit's dev/ folder, no PII or RAKSHA_SECRET in logs/tests/docs. Do not change contracts.py, pipeline.py, main.py, contract/, link/, export/, fhir/, security/,
detect/rules.py, detect/merge.py, detect/names.py. Add new detector files (detect/india_ids.py, detect/address_fields.py, detect/hidden.py, detect/diagnosis.py) and register them only in detect/__init__.py.
Do these in order, one small commit each: (1) Aadhaar/PAN/MRN/village/locality/house/landmark/DOB detection by context; (2) hidden places (base64, metadata, JSON keys, file names);
(3) meaning traps; (4) privacy/attack.py stand-in attacker from the kit's docs/ATTACKS.md; (5) tune generalization against it; (6) last, a CRF (ask me before adding sklearn-crfsuite).
After each step run python -m pytest -q, the synthetic scorer, and the kit checkers on the practice data (python ../Secret-Wards-ToolKit/check_dev.py --output <out>) and show me numbers before and after.
Stop and ask if a design choice is unclear or a bug survives two attempts.
```

## 6. Friend B: FHIR-aware sanitizer, security, report, brief (plan steps P3, P6, P7)
**Why:** the kit gives integrity 10 points (format, schema, FHIR validity, report honesty, channel hygiene) and every JSON/FHIR file must stay valid. Note the change: we need a FHIR-aware *sanitizer* that edits the input Bundle in place, not a new FHIR exporter.
**Files you own:** new package `src/secretwards/fhir/` (`sanitize.py`, `validate.py`), `src/secretwards/security/vault.py`, `security/audit.py`, `security/safe_log.py`, tests `tests/test_fhir.py`, `tests/test_vault.py`, `tests/test_audit.py`, `tests/test_contract_hygiene.py`, `README.md` (setup/architecture/limitations parts), `docs/brief.pdf` plus its source `docs-wt/BRIEF.md`, `scripts/demo.*`, `.github/workflows/ci.yml` (Linux CI running pytest, the kit starter checks and our contract path).
**Files NOT to touch:** `contracts.py`, `pipeline.py`, `main.py`, `contract/*`, `detect/*`, `link/*`, `privacy/*`, `ingest/*`, `normalize/*`, `eval/*`.
**Interface (agree with the lead before coding):** `fhir/sanitize.py` exposes `sanitize_bundle(bundle: dict, ctx) -> dict`, where `ctx.redact(text, field_hint) -> str`, `ctx.shift_date(value: str) -> str` (same syntax: date, dateTime, instant), `ctx.pseudonym(key) -> str` are supplied by the lead's contract writer. The function must keep resource ids and every `reference` resolvable inside the Bundle, keep value types and valid R4 syntax, clean `meta.source`, `identifier`, narrative `text.div`, extensions and base64 attachments, and never add or drop entries.
**Steps in order:**
1. **FHIR sanitizer** with a structural validator in `fhir/validate.py` (resource types, ids, required elements, references resolve, date syntax, base64) mirroring the kit's description in `toolkit/docs/SCORING.md` (section 5). Test on synthetic bundles you write yourself, plus the kit's 19 practice bundles locally (never committed).
2. **Security design that is true:** the pipeline writes no raw or intermediate data, so document that and keep `RAKSHA_SECRET` handling safe (never written). If we later write any spill file, encrypt it with `AesGcmVault` using a key derived from the secret. Add `security/audit.py` (HMAC-chained event log: ids, counts, codes only) only if time allows; the brief needs an honest security section more than code.
3. **Channel hygiene tests** on the contract path: stdout, stderr, `logs/`, report, records, output file names, TMPDIR/HOME contain no planted canary or secret (`tests/test_contract_hygiene.py`).
4. **CI on Linux** (`.github/workflows/ci.yml`): install from `requirements.txt`, run pytest, run the kit starter checks, run our contract path twice (determinism) and with a different secret (must differ). The run environment is Linux, and we only develop on Windows.
5. **README and the 2-page Project Brief PDF** (`toolkit/brief/PROJECT_BRIEF_TEMPLATE.md`; at most 2 pages A4, 10 pt or larger) with measured numbers from `check_dev.py` and the stand-in attacker; keep limitations honest.
**Definition of done:** tests and CI green; bundles validate and references resolve after sanitising; the dates in sanitised FHIR parse as valid R4; hygiene tests pass; `docs/brief.pdf` is 2 pages and uses real measured numbers.

**Ready-to-paste prompt (Friend B):**
```
You are helping on the Secret Wards repo (hackathon Track 3: offline, LLM-free de-identification and record linkage for English/Hindi/Hinglish hospital records).
FIRST read CLAUDE.md, then docs-wt/TOOLKIT.md (the official kit and output contract), then docs-wt/FRIEND_TASKS.md section 6. I am Friend B (FHIR, security, report, brief). Work only on branch feat/output-security.
Rules: no LLMs, no network at run time, deterministic output, fake data only, never hardcode names or values from the practice data or its answer key, never commit keys/ data/ out/ .venv/ or the kit's dev/ folder,
no PII or RAKSHA_SECRET in logs/tests/docs. Do not change contracts.py, pipeline.py, main.py, contract/, detect/, link/, privacy/, ingest/, normalize/, eval/.
Do these in order, one small commit each: (1) fhir/sanitize.py + fhir/validate.py: sanitize a FHIR R4 Bundle IN PLACE (ids, references, meta.source, identifiers, narrative, attachments; shift dates in valid syntax through ctx.shift_date) per the interface in section 6;
(2) honest security design and, only if needed, AES-GCM for any spill file; (3) tests that no canary or secret appears in stdout/stderr/logs/report/records/file names/TMPDIR; (4) Linux CI workflow; (5) README and the 2-page brief PDF with measured numbers.
Each step needs tests. Run python -m pytest -q after each step. Stop and ask if a design choice is unclear or a bug survives two attempts.
```

## 7. Lead (Saiteja): plan steps P0, P1, P5
- **P0 contract adapter (`feat/contract`):** `raksha.toml`, root `main.py`, new package `src/secretwards/contract/` (keys derived from `RAKSHA_SECRET` by HKDF, mirror writer, in-place redaction, SHA-256 report, `records.jsonl`, atomic output, exit codes), changes to `pipeline.py`, `ingest/*`, `export/*`. Stop quarantining records; keep quarantining whole unprocessable files.
- **P1:** gate over-quarantine (`detect/rules.py`, `security/leak_gate.py`), quadratic merge (`detect/merge.py`), perf test, atomic output.
- **P5 identity:** pseudonym inside the record, `records.jsonl` locators, `null` when evidence is weak, homonym tests (`link/*`).
- Review and merge PRs; keep `PROGRESS.md` current; decisions open: age accuracy vs attack resistance (`qi_include_dx`), public repo timing, who writes which part of the brief.

## 8. Who owns which file (avoid conflicts)
| Area | Owner |
|---|---|
| `contracts.py` | frozen; lead only |
| `pipeline.py`, `main.py`, `raksha.toml`, `contract/*`, `ingest/*`, `export/*` | Lead |
| `detect/rules.py`, `detect/merge.py`, `detect/names.py`, `detect/address.py`, `detect/lexicon.py`, `security/leak_gate.py`, `link/*` | Lead |
| `detect/india_ids.py`, `detect/address_fields.py`, `detect/hidden.py`, `detect/diagnosis.py`, `detect/crf/*`, `privacy/*` | Friend A |
| `fhir/*`, `security/vault.py`, `security/audit.py`, `security/safe_log.py`, CI workflow, README, brief | Friend B |
| `synth/*`, `eval/*`, `tests/*` | each owner for their own new test files; lead for existing ones |
| `docs-wt/*` | lead; everyone updates their own rows in PROGRESS.md |

## 9. Quick checks before you push
`git status` shows only your files; `git diff --stat main` is small; `python -m pytest -q` is green; no key, data, out, kit `dev/`, answer key or personal path in the diff; the kit checkers do not get worse.
