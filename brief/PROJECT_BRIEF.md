# Secret Wards: offline, LLM-free de-identification that links patients without merging people

**Track 3 · Secret Wards** · Members: Saiteja Kommi (`SaitejaKommi`), Jaisheel (`jaisheel15`) · Repo: https://github.com/SaitejaKommi/secret-wards

## 1. In one paragraph
Secret Wards turns messy English / Hindi / Hinglish hospital exports into a research release: personal data is removed, medical content is kept, and records of the same patient share a keyed pseudonym. The idea that makes it better than a plain PII tool is that **identity is treated as evidence, not as a name**: a merge needs a strong non-name identifier (patient number, Aadhaar, phone, ABHA, e-mail) and survives hard vetoes, so two people with the same name stay apart. No LLM, no network, CPU only, deterministic for a given secret.

## 2. Architecture
```
input tree (csv tsv json txt, FHIR bundles, broken files)
  -> ingest (encodings, BOM, format sniffing; unreadable file -> quarantined whole, reason code only)
  -> normalize (Unicode, Devanagari digits, OCR-style digits, dates)
  -> detect: rules + validators | names + gazetteers + transliteration | address, India ids | hidden places | medical guard
  -> name memory (names learned from this run, found again in lowercase / Devanagari)
  -> link (blocking on strong ids, evidence scoring, vetoes, clustering) -> keyed HMAC pseudonyms
  -> privacy layer (per-patient date shift, age / PIN generalization ladder, rare-diagnosis suppression)
  -> render in place -> leak gate (re-scan, blank never drop) -> rebuild each file in its own format
  -> sanitized/ (mirror)  +  records.jsonl (record -> pseudonym)  +  report.json (hashes, counts, quarantine)
```

## 3. How it works
- **Ingestion:** CSV / TSV / JSON / FHIR / TXT in UTF-8, UTF-8-BOM, UTF-16 and cp1252; delimiter and header sniffed; JSON lists, single objects and Bundles each map to the contract's `row:N` / JSON-pointer / `doc` locators. A file that cannot be parsed or decoded is quarantined whole with a reason code; it is never copied raw and the run never exits successfully with a file silently missing.
- **Detection:** layered, so a miss in one layer is caught by another. Validated rules (phones, e-mail, dates, ABHA, Aadhaar, PAN, insurance and patient numbers by shape and label), gazetteers with consonant-skeleton transliteration for Latin, Devanagari and Hinglish names, label / relation / honorific cues (S/o, W/o, C/O), address parts (village, locality, house, landmark, PIN), and a **name memory** that learns names from the data at run time instead of hard-coding them. File names, JSON keys, headers and base64 / hex payloads are scanned too. A **medical guard** keeps drugs, doses, vitals, labs and durations, so "1-0-1", "x 9 yrs" and "C/O fever" are not mistaken for ids, ages or relatives, and "Dr. X" stays.
- **Linkage and pseudonyms:** candidate pairs come only from strong identifiers; pairs are scored with hand-set log-odds weights (cross-script name similarity, relative name, DOB / age, sex, PIN) and rejected by hard vetoes (different ABHA, DOB, sex, or contradicting names). Clustering is constrained so a cluster cannot absorb conflicting members. Pseudonyms are `PSN-` plus bits of an HMAC-SHA256 under `RAKSHA_SECRET`, written into a record only when we also claim it in `records.jsonl`.
- **Privacy layer:** dates shift by a per-patient keyed offset (interval lengths survive); age and PIN are generalized one step at a time, only for records whose (age, sex, PIN prefix, diagnosis) class holds fewer than *k* distinct patients; a diagnosis held by very few patients is suppressed whole, ICD code included. Medical values are never touched. FHIR ids are replaced by keyed valid UUIDs so references still resolve.
- **Security:** see section 6.

## 4. USP
- **Safe linking:** precision 1.00 with 0 wrong merges on the practice data, and the pairs we leave unlinked are the ones that would merge different people (a shared phone with a relative's name; records with no identifier).
- **Hidden-channel hygiene:** file names, keys, headers and encoded payloads are cleaned, and a subprocess test scans all seven side channels the kit lists. Writing nothing sensitive to disk removes the "intermediate data at rest" problem instead of encrypting it.
- **Fail closed with a last gate:** every rendered field is re-scanned against the values found in the run; leaks are blanked, never dropped, and a file we cannot handle is quarantined.

## 5. Privacy-utility trade-off (practice data, kit's `check_dev.py`, 2026-11-26)

| Measure | Value |
|---|---|
| personal data leaked (overall / Hindi / Hinglish) | 0.0% (0 of 3,230) / 0.0% / 0.0%; hiding places (names, metadata, base64, keys, headers) 0.0% |
| medical values kept | 99.2% (4,816 of 4,855) |
| linking precision / recall / F0.5 | 1.00 / 0.91 / 0.98, 0 wrong merges |
| re-identification risk (own attack, synthetic data) | exact age + sex + PIN + diagnosis known: raw data 99-100% unique; release 11-15% at 100-250 patients, 0.8% at 1,500; not measured against the organisers' attacker |
| run time / peak memory | 5.2 s / 64 MB for 200 files (limits 15 min / 4 GB) |
| on data we did not tune on (own synthetic held-out / blind pools) | PII recall 0.997 / 0.995, medical kept 0.989 / 0.992, link recall 0.857 / 0.597 |

We give up location precision first, then age precision (exact age to 5- and 10-year bands only where a group is too small), and keep every medical value. The practice numbers are optimistic: we used its answer key to fix bugs, which is why the held-out row is quoted.

## 6. Security design (assume the server is breached one day)
The contract run writes **no raw or intermediate data** (input is read-only; only redacted outputs are written), so there is nothing at rest to encrypt; a test runs it with a private TMPDIR / HOME and checks both stay empty. The only key is `RAKSHA_SECRET` from the environment, never written anywhere (tested); pseudonyms, date shifts, file-name replacements and ids are keyed HMACs with one label per purpose, so a breached release cannot be inverted or linked to another release without the secret. Logs hold counts and exception types only. Quarantine reports a reason code and a file hash, never content.

## 7. Known limitations
Not run on Linux yet (the evaluator is Linux; a static check found nothing Windows-only). No stand-in for the organisers' attacker, and generalization is decided per record while an attacker can join records by pseudonym. FHIR is sanitized generically: hospital names inside bundles are lost and a patient name outside the gazetteer under `name.family` survives. Hand probes with invented values still leak an unseen lowercase or Devanagari name with no cue, phones written "9 8 7 6 5 …", and "policy no X" without a colon. No audit trail or key rotation. Next: resource-aware FHIR, a stand-in attacker to tune age bands, and the Linux run.
