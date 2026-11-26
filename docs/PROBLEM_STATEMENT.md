# Problem, in plain words

`PROBLEM_ORIGINAL.md` wins if anything here differs.

Five hospitals merge 10 years of messy records for research. Build a pipeline that removes who the patient is and keeps what happened medically.

## Jobs
1. Detect and remove PII (names in any order, s/o d/o w/o, transliterations, nicknames, addresses with landmarks, phones, dates, ABHA-style / insurance / MRN IDs, emails), in structured columns and free text.
2. Preserve medicines, dosages, frequencies, vitals, lab values with units, diagnoses, procedures, length of stay. Ages stay accurate unless privacy needs generalising.
3. One stable pseudonym per real patient across records, languages, hospitals. Never merge different people.
4. Resist re-identification through quasi-identifiers (age, pin code, admission dates, rare diagnoses, ward). Justify the privacy/utility trade-off and measure the risk.
5. Security: encrypt raw and intermediate data, keys apart from data, key handling, access separation, PII-free logs, audit trail, quarantine.

## Deliverables
Runnable pipeline; outputs as CSV, JSON, FHIR R4 (Patient, Encounter, Observation, MedicationRequest); processing report (counts, quarantined files, risk metrics); short technical report; repository.

## Traps
- "Dolo 650 BD x 5 days" is not a phone number.
- "Dr. Paracetamol" is not a person.
- Canary PII is planted in hidden data. Any appearance anywhere counts as a leak.
- Evaluation data is hidden and differs from practice data.

## Scoring (track rubric)
Privacy against attacks 25, PII detection 20, medical preservation 20, identity consistency 15, output quality and validity 10, speed and reliability 10.

## Unknown until organisers answer
Practice data and answers; input formats; output schema and run command; attack method; whether the general DevForge criteria also apply (innovation, technical complexity, feasibility, impact, presentation).
