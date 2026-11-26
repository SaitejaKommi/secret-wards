# Architecture (as built)

```
ingest -> normalize -> detect -> name memory -> link -> pseudonymize -> generalize -> render -> leak gate -> export
   |                                                                                     |
   +---------------------------- quarantine (codes only, never content) <----------------+
```

## Layout (main branch)
```
src/secretwards/
  contracts.py        typed records + teammate interfaces (Detector, Exporter, Vault, RiskAttack). Unchanged since M2.
  config.py           all knobs (TOML or JSON); keys come from files, never from config values
  ingest/             csv tsv json jsonl txt xlsx adapters; any failure -> Quarantine(reason code)
  normalize/          text.py (offset map), translit.py (Devanagari <-> Latin skeleton), dates.py (find / shift / re-render)
  detect/             rules.py (phone, e-mail, ABHA, insurance, MRN, dates, PIN), names.py, address.py, headers.py,
                      lexicon.py (+ gazetteer/data/*.txt), medical_guard.py, merge.py, learned.py (dataset name memory)
  link/               names.py, mention.py, compare.py, blocking.py, cluster.py
  privacy/            pseudonym.py, render.py, generalize.py, risk.py
  export/             csv_json.py (CSV / JSON / TXT writers, header sanitiser)
  security/           keys.py, vault.py (AES-GCM, not yet wired), safe_log.py, leak_gate.py
  pipeline.py         orchestration only
  cli.py              run | keygen
synth/                generator with gold labels: dev, heldout, blind
eval/                 scorer
tests/                97+ tests
```

## Contracts
`Document` (one record: row, JSON object or text file) -> `Unit` (one field with its `NormText` offset map) -> `Span` / `MedSpan`
(offsets always in the ORIGINAL text) -> `Mention` (linkage evidence) -> `Cluster` (pseudonym + doc ids) -> `RedactedRecord` (+ `meta`).
`field is None` means free text. JSON leaves are named by path, table overflow cells `_extraN`.

## Design decisions (and why)
- **Offset map:** match on normalized text, redact on original text. ASCII fast path + cache; OCR digit repair (O/l/S inside digit-heavy tokens) works on a same-length view.
- **Detection ensemble:** validator rules first (phones validated by Indian number rules, dates parsed, IDs by pattern + cue), address anchors (house, locality suffix, landmarks in English / Hinglish / Devanagari, village / post / district, city gazetteer, PIN), names (label cues, relation cues s/o d/o w/o, honorifics, header hints, gazetteers matched across scripts by phonetic skeleton, kin terms "X bhaiya", capital-run heuristic). The medical guard (drugs, doses, frequencies, vitals, labs, ages) vetoes names/addresses that are mostly medical text and numeric IDs inside lab/dose text. Ambiguous overlaps keep the direct identifier.
- **Header hints only raise priors.** Exported tables have shifted columns, so content validators always run; typed columns fail closed (a malformed phone in a phone column is still redacted).
- **Dataset-level name memory:** names found with strong evidence anywhere in the run are flagged everywhere else (lowercase Hinglish, Devanagari spelling). Learned at run time, nothing hardcoded, order independent.
- **Linkage:** evidence weights (ABHA 10, MRN 6, e-mail 5, DOB 4, relative name 3.5, phone 3, insurance 3, name similarity up to 4, PIN 1, age 1). A merge needs score >= 6 AND at least one strong non-name agreement. Relative-name evidence only counts when a compatible birth year or the same DOB backs it. Hard vetoes: different ABHA, different DOB, different sex, contradicting names (an exactly equal ABHA overrides soft vetoes). Clustering is best-first and refuses a merge if any cross pair of members is vetoed (no transitive over-merging).
- **Pseudonyms:** HMAC-SHA256 of the cluster anchor (strongest identifier present), key in `keys/pseudonym.key`. Different keys give unrelated pseudonyms. Known limit: adding a stronger id later changes the anchor.
- **Dates:** one shift per patient, 30-365 days, sign and size from HMAC(date key, pseudonym). Same shift for table cells and free-text dates, re-rendered in the original style (numeric, ISO, "12th March, 2021", Hindi month names). Unparseable dates become `[DATE]`, never guessed.
- **Generalization ladder (per record, only where k=5 needs it):** PIN prefix 3 -> 2 -> removed, then exact age -> 5-year -> 10-year band, then rare diagnosis (<= 1 patient) suppressed, then coarse age groups. Ages >= 90 are always "90+". Location is given up before age because age matters medically. `qi_include_dx` decides whether diagnosis counts in the k-anonymity tuple (see PROGRESS: this is the privacy-vs-utility switch).
- **Risk:** our own linkage attack (exact age, sex, PIN, diagnosis; optionally LOS) run on raw data and on the release; k, l-diversity, share of patients in classes below k.
- **Leak gate (two independent checks per output record):** (A) every raw value detected anywhere in the run (name words, phones, e-mails, ABHA / insurance / MRN) must not appear in any output; (B) detector-independent patterns (mobile numbers, e-mails, ABHA) over the output text. Hits are repaired, re-checked, and the record is quarantined if it still leaks. Header names, JSON keys and sheet names are kept only if every word is in a header vocabulary; otherwise replaced by a keyed hash.
- **Security (what is true today):** no plaintext temp files, no raw intermediates on disk; logs carry codes, counts and exception class names only; CLI errors print the exception type only; quarantine stores reason codes and keyed refs, no copies; output file names do not derive from input names; keys are separate files per purpose. NOT done: encryption of anything at rest, audit trail, access separation.
- **Determinism:** no randomness, sorted iteration, keys from files; the test suite runs the CLI in two processes with different `PYTHONHASHSEED` and compares output hashes.

## Evaluation without organiser data
`synth/` makes records with gold spans, gold patient ids and gold medical values with OCR noise, shifted columns, preamble rows, code-mixing, same-name different people, canaries in odd places, and unreadable files. Three splits with disjoint names: `dev`, `heldout` (inspected, so a second dev set), `blind` (frozen code, scored once). Metrics: span recall / precision per type, leak rate, medical retention, pairwise linkage P/R, same-name merges, canary leaks, quarantine, attack and k. These numbers measure our own synthetic data, not the hidden set. Say so in the report.

## Simple first, scale later
Single process, in memory. Later: per-file multiprocessing, DuckDB-backed linkage, a bounded-memory leak gate (it keeps all detected raw values in RAM).
