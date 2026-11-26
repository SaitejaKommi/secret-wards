Track 3: "Secret Wards"
Domain: Privacy Engineering, Multilingual Information Extraction, Record Linkage & Data Security
Environment: Synthetic Indian hospital records dump (English, Hindi & Hinglish), provided by organisers. No real patient data is used anywhere in this track.

What happens in the ward stays in the ward.

1. Mission Brief
Five hospitals in Yugaantar Pradesh are merging ten years of patient records into one research database for public health studies. What arrives is chaos: OCR'd discharge summaries, transcribed handwritten prescriptions, WhatsApp-forwarded lab reports, Excel exports with shifted columns, and clinic notes that jump between English, Devanagari Hindi and Hinglish in the same sentence.

The same patient shows up as "Kumar Rajesh", "Rajesh K.", "राजेश कुमार", "R. Kumar s/o Shyam Lal" and "rajesh bhaiya", each with a different phone format and a half-written address.

Your challenge is to build an offline, LLM-free de-identification pipeline that strips every piece of personal information, keeps every medically useful value intact, recognises the same patient across languages and formats without merging different people, and keeps the whole dataset secure so that even a breach of your system leaks nothing usable.

Removing names is the easy part. The real test: can an attacker holding a voter list, who knows "a 47-year-old woman from Ward 12 was admitted for 9 days with dengue", still find her in your output?

2. Core Challenge Objectives
Your system must handle real-world mess, not clean tables. A successful pipeline must contend with:

Messy Multilingual PII Detection: Names in any order (surname first, initials, s/o, d/o, w/o), transliteration variants (Mohammad / Mohd / मोहम्मद), Indian addresses with landmarks ("near Hanuman mandir, behind SBI"), phone numbers in every format, dates, ID numbers (ABHA-style, insurance, hospital MRN), emails, and PII buried inside free-text clinical notes.
Medical Data Preservation: Medicines, dosages, frequencies, vitals, lab values with units, diagnoses, procedures and length of stay must survive exactly. Ages must stay accurate unless generalising them is needed for privacy. "Dolo 650 BD x 5 days" is not a phone number, and "Dr. Paracetamol" is not a person.
Patient Identity Consistency: Every real patient gets one stable pseudonym across all records, languages and hospitals. Correctly linking the same person is rewarded; merging two different people who share a name is penalised.
Re-identification Resistance: Removing direct identifiers is not enough. Quasi-identifiers (age, pin code, admission dates, rare diagnoses) can still single someone out. You decide what to generalise, shift or suppress, and justify the privacy-vs-utility trade-off.
Breach & Leak Protection: Your pipeline handles raw PII while it works. Encrypt data at rest, keep keys away from data, keep logs clean, and quarantine any file you cannot safely process instead of passing it through half-cleaned.
3. Deliverables & System Architecture
Your final submission must include a runnable pipeline, its outputs and a short technical report covering the following core areas:

Detection Engine: How PII is found in structured columns and in free text across three scripts and languages: rules, gazetteers, transliteration, classical ML models, and how they are combined.
Linkage & Pseudonymisation: How records of the same patient are clustered (blocking, fuzzy and phonetic matching, cross-script comparison) and how stable pseudonyms are issued so that outsiders cannot reverse them.
Privacy Layer: How quasi-identifiers are treated (date shifting, age banding, location generalisation, rare-value suppression) and the measured re-identification risk of your final output.
Output Formats: De-identified data as CSV, JSON and FHIR R4 resources (Patient, Encounter, Observation, MedicationRequest), plus a processing report with counts, quarantined files and risk metrics.
Security Architecture: Encryption at rest for raw and intermediate data, key handling, access separation, PII-free logging, audit trail, and quarantine design.
Note on Innovation: Wrapping an off-the-shelf PII tool with default settings will score poorly. Those tools miss Hindi and Hinglish, break on Indian name structures, and do nothing against linkage attacks. We are looking for engineered solutions: cross-script identity matching, smart quasi-identifier handling, measurable privacy guarantees, and a security design that assumes your server will one day be compromised.

4. Prerequisites & Recommended Libraries
Core Libraries
regex, phonenumbers, dateparser: patterns and formats for Indian phones, dates and IDs
indic-transliteration / indic-nlp-library: Devanagari ↔ Latin transliteration and normalisation
rapidfuzz, jellyfish: fuzzy and phonetic string matching
sklearn-crfsuite / spaCy (rule-based Matcher, small non-LLM pipelines): classical NER
splink / recordlinkage: probabilistic record linkage (Fellegi–Sunter)
fhir.resources, pydantic, jsonschema: valid FHIR R4 and JSON outputs
cryptography: AES-GCM / Fernet encryption, HMAC-based keyed pseudonyms
anonymeter, pycanon: measuring re-identification risk, k-anonymity and l-diversity
Faker (en_IN, hi_IN locales): generating your own extra training and test data
Key Concepts to Research
Indian Name Structures: patronymics, initials, honorifics, cross-script spelling variants and nicknames
Quasi-identifiers & Linkage Attacks: k-anonymity, l-diversity, date shifting, generalisation hierarchies
Record Linkage: blocking, Fellegi–Sunter models, clustering without transitive over-merging
De-identification Standards: HIPAA Safe Harbor's 18 identifiers, India's DPDP Act 2023, ABDM health data guidelines
Secure Data Handling: envelope encryption, keyed hashing (HMAC) vs plain hashing, canary tokens, log hygiene
5. Ground Rules
No LLMs: No GPT, Llama, Gemini, Claude, Mistral or any other large language model, whether hosted, local or distilled. No generative models, and no pretrained transformer models above 50M parameters. Rules, gazetteers, CRFs, classical ML and small models you train yourself are allowed.
Fully Offline: Final evaluation runs on organiser machines, CPU only, with no internet. Any network call means disqualification.
Synthetic Data Only: All data comes from the organisers or is generated by your team. Using real patient records in any form is strictly prohibited.
No Hardcoding: The evaluation set is hidden and different from the practice set. Pipelines tuned to memorised practice names or files will fail.
Zero Leaks: Organisers plant canary PII in the hidden data. If a canary shows up anywhere (outputs, logs, temp files, error messages or your report), it counts as a leak and is heavily penalised.
Original Work: Your repository must be created during the hackathon. Open-source libraries are permitted, but your core pipeline, linkage logic and privacy layer must be built during the event.
Reproducible: The same input must always produce the same output. Pseudonym keys and random seeds come from config, not hidden state.
Team Evaluation & Scoring Criteria
Total: 100 Points

1. Privacy Against Attacks — 25 Points
Resistance to patient re-identification using external records and known medical information.

2. Personal Data Detection — 20 Points
Accurate detection and removal of sensitive information across English, Hindi and Hinglish.

3. Medical Data Preservation — 20 Points
Preserving medicines, dosages, vitals, lab values, hospital stays and age accuracy.

4. Patient Identity Consistency — 15 Points
Correctly linking the same patient across languages without merging different individuals.

5. Output Quality & Validity — 10 Points
Valid CSV, JSON and FHIR outputs, accurate reports, no data leaks and proper file quarantine.

6. Speed & Reliability — 10 Points
Processing speed, system stability, reproducibility and resource efficiency.

Evaluation Principle: Build a system that protects patient privacy without compromising the accuracy, integrity or medical usefulness of healthcare data.
