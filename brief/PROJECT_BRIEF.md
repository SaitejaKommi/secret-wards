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
- **Privacy layer:** dates shift by a per-patient keyed offset (interval lengths survive); age, PIN, tehsil and date of birth are generalized per patient (all of a pseudonym's records share one level, so pooling them gives an attacker no finer detail) until a group holds enough patients; a date of birth becomes a truthful birth-year band; a diagnosis held by very few patients is suppressed whole, ICD code included. Medical values are never touched. FHIR bundles are handled resource by resource (hospital and doctor names stay; patient and relative names, phones, ids and addresses go) and their ids become keyed valid UUIDs so references still resolve.
- **Security:** see section 6.

## 4. USP
- **Safe linking:** precision 1.00 with 0 wrong merges on the practice data, and the pairs we leave unlinked are the ones that would merge different people (a shared phone with a relative's name; records with no identifier).
- **Hidden-channel hygiene:** file names, keys, headers and encoded payloads are cleaned, and a subprocess test scans all seven side channels the kit lists. Writing nothing sensitive to disk removes the "intermediate data at rest" problem instead of encrypting it.
- **Fail closed with a last gate:** every rendered field is re-scanned against the values found in the run; leaks are blanked, never dropped, and a file we cannot handle is quarantined.

## 5. Privacy-utility trade-off (practice data, kit's `check_dev.py`, 2026-11-26)

| Measure | Value |
|---|---|
| personal data leaked (overall / Hindi / Hinglish) | 0.0% (0 of 3,230) / 0.0% / 0.0%; hiding places (names, metadata, base64, keys, headers) 0.0% |
| medical values kept | 99.6% (4,835 of 4,855) |
| linking precision / recall / F0.5 | 1.00 / 0.91 / 0.98, 0 wrong merges |
| re-identification risk (our stand-in for the organisers' attacker, A2-A5) | patients re-identified by profile linking 4 of 48 (raw data 47 of 48); registry linkage 0.04 (raw 0.71); targeted attack 0.61 (raw 0.93); 0 of 48 pseudonyms inverted |
| run time / peak memory | 5.3 s / 55 MB on Linux, 2 CPUs, no network (limits 15 min / 4 GB); about 150 records/s |
| on data we did not tune on (own synthetic held-out / blind pools) | PII recall 0.997 / 0.995, medical kept 0.989 / 0.992, link recall 0.857 / 0.597 |

We give up precision on location and age first and keep every medical value. The cost is real: inside a 48-patient release most patients end up in coarse age groups (18-59, 60-89); our proxy of the kit's age score falls from 0.54 to 0.28 (about -0.4 of 20 utility points) while re-identified patients fall from 40 to 4 of 48. Uniform 10-year bands would leave 19 of 48 re-identified, 5-year bands 28 of 48. The practice numbers are optimistic: we used its answer key to fix bugs, which is why the held-out row is quoted.

## 6. Security design (assume the server is breached one day)
**Data at rest.** The contract run stores nothing sensitive, so there is nothing to encrypt: the input is read-only, no raw or intermediate copy, temp file or log is written, and records live only in process memory (a test runs it with a private TMPDIR / HOME and checks both stay empty). The released `sanitized/` tree holds no direct identifiers and is not encrypted, because it is meant to be shared; it is protected by the de-identification itself, measured with the stand-in attacker. We do not encrypt or manage the raw input (the operator's disk protection) and cannot control host swapping; an earlier unused AES-GCM stub was removed rather than claimed. **Keys.** The only secret is `RAKSHA_SECRET`, read from the environment and never written (tested); pseudonyms, date shifts and aliases use three HMAC-SHA256 sub-keys, one label per purpose, so a breached release cannot be inverted or linked to another release without the secret. **Logs and quarantine.** stdout holds counts only, errors print an exception type, and a subprocess test scans all seven side channels the kit lists; an unprocessable file is quarantined whole with a reason code, never copied raw. No audit trail or key rotation.

## 7. Known limitations
Tuned on the practice data (a stress test with invented layouts found more problems than it did); hand probes still leak an unseen lowercase or Devanagari name with no cue, odd phone spellings ("9 8 7 6 5 …", hex) and "policy no X" without a colon. Coarse age groups cost utility; counting the group size against the population an attacker searches would keep finer bands. An age stored as a JSON number gets a keyed surrogate, not a band. The organisers' FHIR validator is hidden. One process: about 150 records/s, so roughly 120,000 records fit in 15 minutes. Next: finer bands, a multi-process run, label-aware span limits.
