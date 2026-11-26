def edit(path, pairs):
    s = open(path, encoding="utf-8").read()
    for old, new in pairs:
        assert old in s, (path, old[:80])
        s = s.replace(old, new, 1)
    open(path, "w", encoding="utf-8", newline="\n").write(s)


CL_OLD = "git clone https://github.com/Reinforce-SST/Secret-Wards-ToolKit.git\n# layout:"
CL_NEW = ("git clone -c core.autocrlf=false https://github.com/Reinforce-SST/Secret-Wards-ToolKit.git\n"
          "# -c core.autocrlf=false is REQUIRED on Windows: a CRLF checkout changes the practice files' bytes, their SHA-256 no longer matches\n"
          "# the answer key and check_dev under-counts. Verify: all 200 files in dev/input must hash to the sha256 in dev/truth/truth.json.\n# layout:")

# ------------------------------------------------------------------ PROGRESS.md
edit("docs/PROGRESS.md", [
    ("""**Our code does not meet it yet** (measured: `validate_output.py` crashes on our report; `check_submission.py` fails on
missing `raksha.toml`; our leak gate quarantined 382 of 1,209 records on the practice data). Plan P0-P7 and every conflict are in `TOOLKIT.md`. Official numbers on the practice data (kit starter): CONTRACT OK, 84.1% leaked.
Status of the plan (lead OK needed before code changes): P0 contract adapter [ ], P1 gate + quadratic merge [ ], P2 India IDs / address fields / hidden places [ ] (Jaisheel), P3 FHIR-aware sanitizer [ ] (Jaisheel),
P4 stand-in attacker + tuning [ ] (Jaisheel), P5 identity in `records.jsonl` [ ] (Saiteja), P6 channel hygiene + security design [ ] (Saiteja), P7 README + 2-page brief + public repo [ ] (Saiteja). Team is two people now (Saiteja, Jaisheel); the third friend is busy.""",
     """**P0 is done (branch `feat/contract`): `python main.py --input DIR --output DIR` with `RAKSHA_SECRET` now writes the contract output and the kit's `validate_output.py` prints CONTRACT OK.**
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
`check_dev.py` does NOT measure: the organisers' attacker (privacy is 25 points), date-interval and age-band truthfulness, FHIR validity, determinism, side channels. Still open: hospital names in FHIR (19 of 19 lost) and FHIR validity, 5 house-number leaks, linking recall 0.61, coarse age bands ("18-59") that cost utility, one large text file takes quadratic time."""),
    ("- [ ] Audit fixes (all still OPEN, verified by re-running on 2026-11-26): gate over-quarantine, quadratic merge, atomic output, phone/ID gaps, same-name merges",
     "- [x] P0 contract adapter (2026-11-26, `feat/contract`): `main.py`, `raksha.toml`, `contract/` (readers, writers, renamer, run), keys from `RAKSHA_SECRET`, atomic cleanup, 11 contract tests\n"
     "- [x] Audit fix: gate over-quarantine (id-shaped values only, repair-only mode, doctors exempt, weak guesses never become dataset-wide rules); medical history, lab tests, departments, district kept (general rules, `tests/test_meaning_traps.py`)\n"
     "- [ ] Audit fixes still open: quadratic merge on one big text file, same-name merges when phones differ (none seen on the practice data), non-atomic legacy output (the contract path is atomic)"),
    ("- [ ] Jaisheel (branches `feat/detection`, `feat/fhir`, `feat/attacker`):", "- [ ] Jaisheel (steps 1 and 2 DONE and merged: PR #1, PR #2/#3; branches `feat/detection`, `feat/hidden`; next `feat/fhir`, `feat/attacker`):"),
    ("- [ ] Saiteja (branches `feat/contract`, `feat/identity`, `feat/hygiene`):", "- [ ] Saiteja (P0 and P1-gate DONE on `feat/contract`; next `feat/identity`, `feat/hygiene`):"),
    ("## What is NOT done\nThe whole output contract (see top); FHIR-aware sanitizing (the kit needs valid FHIR in place, not an export);",
     "## What is NOT done\nFHIR-aware sanitizing (the kit needs valid FHIR in place, not an export; hospital names in bundles are still lost);"),
])
s = open("docs/PROGRESS.md", encoding="utf-8").read()
s = s.rstrip("\n") + """
**2026-11-26 P0 + merges.** Built the contract path (`python main.py`), reviewed and merged Jaisheel's PR #1 (India ids, address fields) and PR #2 (hidden places; it was stacked, so it needed a second PR #3 to reach `main`). Review caught practice ids quoted in a comment (replaced with invented ones) and one practice date in a test. Found that this machine's `core.autocrlf=true` had rewritten 172 of the kit's 200 files (hashes no longer matched the key): re-cloned with `-c core.autocrlf=false`. The answer key then showed real over-redaction (history `K/C/O ...` read as a relative, `x 9 yrs` rewritten as an age band, "Test Name" columns read as person names, specialties as names, districts redacted, a stray low-confidence name poisoning the leak gate): fixed with general rules, medical kept 89.7% -> 98.0%. Combined with Jaisheel's detectors: 0.2% leaked, 0 of 4 canaries, CONTRACT OK, 6.5 s.
"""
open("docs/PROGRESS.md", "w", encoding="utf-8", newline="\n").write(s)

# ------------------------------------------------------------------ TOOLKIT.md
edit("docs/TOOLKIT.md", [
    ("git clone https://github.com/Reinforce-SST/Secret-Wards-ToolKit.git\n# layout:", CL_NEW),
    ("Caveats found by reading and running them: `check_submission.py` looks for `.venv/bin` (Linux layout), so on Windows it will not put our venv first on PATH;",
     "Caveats found by reading and running them: on WINDOWS `check_submission.py --run` cannot work (it quotes paths with POSIX `shlex.quote`, so our run fails with 'input directory not found'; it also looks for `.venv/bin`); the same three checks (contract, identical repeat run, different secret, secret never written, input untouched) are covered by `tests/test_contract.py`, and a Linux run needs WSL, Docker or CI;"),
])
s = open("docs/TOOLKIT.md", encoding="utf-8").read()
marker = "## 8. Conflicts between the kit and our docs / code"
add = """### 7b. After P0 (2026-11-26): the contract path exists (`python main.py`)
Measured on `dev/input` with the kit checkers (kit cloned with LF endings; all 200 files match the key's hashes). See the table in `docs/PROGRESS.md` for the progression.
Final state with Jaisheel's PR #1-#3 merged: `validate_output.py` **CONTRACT OK**; 193 files sanitized, 7 quarantined (all "either" in the key); 817 records; `check_dev.py`: **0.2% leaked (5 of 3,230, all house numbers)**,
filename / metadata / base64 / key / header **0%**, **canaries 0 of 4**, **medical values kept 98.0%** (4758 of 4855), **linking precision 1.00, recall 0.61, F0.5 0.89, 0 wrong merges**, 0 raw copies; 6.5 s, 63 MB.
Still lost: hospital names inside FHIR bundles (19 of 19; FHIR sanitizer, Jaisheel step 4), 17 district values (1 TSV, see PROGRESS), and ~80 other medical strings (diagnosis wording, medication lines in discharge notes).

"""
assert marker in s
open("docs/TOOLKIT.md", "w", encoding="utf-8", newline="\n").write(s.replace(marker, add + marker, 1))

# ------------------------------------------------------------------ FRIEND_TASKS.md
edit("docs/FRIEND_TASKS.md", [
    ("git clone https://github.com/Reinforce-SST/Secret-Wards-ToolKit.git\n$env:RAKSHA_SECRET",
     "git clone -c core.autocrlf=false https://github.com/Reinforce-SST/Secret-Wards-ToolKit.git   # -c core.autocrlf=false is REQUIRED on Windows\n$env:RAKSHA_SECRET"),
    ("**Measure our detection on the practice data BEFORE the contract adapter (P0) exists** (temporary helper):",
     "**The contract path is now on `main` (after Saiteja's PR). Measure with the real run:**\n```\ncd secret-wards\n$env:RAKSHA_SECRET=\"practice\"         # Linux: export RAKSHA_SECRET=practice\npython main.py --input ../Secret-Wards-ToolKit/dev/input --output out/ours\npython ../Secret-Wards-ToolKit/validate_output.py --input ../Secret-Wards-ToolKit/dev/input --output out/ours   # CONTRACT OK\npython ../Secret-Wards-ToolKit/check_dev.py --output out/ours\n```\nFirst check the kit is intact: all 200 files in `dev/input` must hash to the sha256 values in `dev/truth/truth.json` (a CRLF checkout breaks this).\nOld helper, for the legacy pipeline only:"),
    ("After P0 is merged, the real command is `RAKSHA_SECRET=practice python main.py --input ../Secret-Wards-ToolKit/dev/input --output out/ours`, then the kit's two checkers on `out/ours`.\n", ""),
    ("- Official practice data, our pipeline: **contract NOT met**; the leak gate quarantined 382 of 1,209 records; detection leaked 4.7% (via the helper); linking not measurable.",
     "- Official practice data, our contract path (P0 + Jaisheel PR #1-#3): **CONTRACT OK**; 0.2% leaked (5 house numbers), hiding places 0%, canaries 0/4, medical kept 98.0%, linking P 1.00 / R 0.61 / 0 wrong merges, 6.5 s.\n- Still open: FHIR sanitizing (hospital names in bundles lost), linking recall, coarse age bands, the stand-in attacker, one slow big-file case."),
    ("1. Day 1: Jaisheel starts steps 1-3 (independent, measured with the helper); Saiteja does P0 and merges it as early as possible.\n2. When P0 is merged: Jaisheel switches to measuring with the real contract run and does the FHIR sanitizer against Saiteja's `ctx`; Saiteja does P1 and P5.",
     "1. DONE: Jaisheel steps 1-2 (merged), Saiteja P0 + gate fixes (PR). Everyone measures with `python main.py` + the kit checkers.\n2. NEXT: Jaisheel step 3 (meaning traps, 5 house numbers), then the FHIR sanitizer (step 4) and the stand-in attacker; Saiteja P5 identity, P1 speed, the FHIR `ctx` hook, P6 and the README. Jaisheel: use `hidden.safe_label` / `sanitize_path` / `clean_encoded` from your own PR #2 when wiring FHIR; Saiteja's writer already renames paths and headers itself."),
])
edit("docs/FRIEND_TASKS.md", [
    ("3. Clone the organisers' kit NEXT TO the repo (not inside): git clone https://github.com/Reinforce-SST/Secret-Wards-ToolKit.git ../Secret-Wards-ToolKit. Read its START_HERE.md and its scripts before running them. Run the baseline from docs/FRIEND_TASKS.md section 2 (\"Measure our detection ...\") and show me the check_dev numbers.",
     "3. Clone the organisers' kit NEXT TO the repo (not inside), with line endings untouched: git clone -c core.autocrlf=false https://github.com/Reinforce-SST/Secret-Wards-ToolKit.git ../Secret-Wards-ToolKit. Verify all 200 files in ../Secret-Wards-ToolKit/dev/input hash to the sha256 in dev/truth/truth.json (if not, re-clone with autocrlf off). Read its START_HERE.md and scripts before running them. Then run the real contract path from docs/FRIEND_TASKS.md section 2 (RAKSHA_SECRET=practice python main.py --input ../Secret-Wards-ToolKit/dev/input --output out/ours; validate_output.py; check_dev.py) and show me the numbers."),
    ("and the kit check_dev.py via scripts/adapt_for_checkdev.py. Show me the numbers", "and the kit's validate_output.py and check_dev.py on the real contract run. Show me the numbers"),
])

# ------------------------------------------------------------------ README.md
edit("README.md", [
    ("## Run (same commands on both systems;", "## Official contract run (what the organisers execute)\n```\nRAKSHA_SECRET=practice python main.py --input INPUT_DIR --output OUT_DIR      # PowerShell: $env:RAKSHA_SECRET=\"practice\"\n```\nWrites `OUT_DIR/sanitized/` (same paths and formats as the input; names holding personal data are renamed and declared), `report.json` (written last) and `records.jsonl`.\nExit 0 only for a complete release. `RAKSHA_SECRET` keys every pseudonym and date shift and is never written. Details: [`docs/TOOLKIT.md`](docs/TOOLKIT.md).\n\n## Our own development run (same commands on both systems;"),
    ("- Leak gate can quarantine many records because of one misclassified cell (20 of 1034 on one fresh dev set).\n", ""),
])
print("docs updated")
