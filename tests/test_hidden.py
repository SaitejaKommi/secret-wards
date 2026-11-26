"""Hidden places: file names, path-like metadata, JSON keys / headers, encoded runs, homoglyphs. Invented values only."""
import base64
import binascii
import html

import pytest

from secretwards.contracts import PIIType
from secretwards.detect import default_detectors, detect_unit
from secretwards.detect.hidden import (clean_encoded, encoded_runs, fold_homoglyphs, label_has_pii, safe_label,
                                       sanitize_path)
from secretwards.pipeline import make_unit

DETS = default_detectors()
KEY = b"t" * 32


def _spans(text, field=None):
    s, _ = detect_unit(make_unit("d", field, text), DETS)
    return s


def covered(text, value, field=None):
    i = text.index(value)
    j = i + len(value)
    return any(x.start <= i and j <= x.end for x in _spans(text, field))


def untouched(text, value, field=None):
    i = text.index(value)
    j = i + len(value)
    return not any(x.start < j and i < x.end for x in _spans(text, field))


# ---------------------------------------------------------------- file names
@pytest.mark.parametrize("path", [
    "discharge/Discharge_Summary_Hemlata_Chhabra_KMC-25-073318.txt",
    "notes/nursing_ipd-2025-00412.txt",
    "notes/nursing_adm004417.txt",
    "lab/9876501234_report_0047.json",
    "lab/gurmeet_bhatia_cbc.json",
    "reports/RGH2025-007731/summary.txt",
])
def test_pii_paths_are_renamed(path):
    new = sanitize_path(path, KEY)
    assert new != path
    assert new.rsplit(".", 1)[-1] == path.rsplit(".", 1)[-1]  # extension kept
    for bad in ("Hemlata", "gurmeet", "bhatia", "073318", "00412", "004417", "9876501234", "007731"):
        assert bad not in new


@pytest.mark.xfail(reason="known limit of detect/names.py: an unseen lowercase name with no cue is not found")
def test_unseen_lowercase_name_in_file_name():
    assert sanitize_path("lab/hemlata_chhabra_cbc.json", KEY) != "lab/hemlata_chhabra_cbc.json"


@pytest.mark.parametrize("path", [
    "prescriptions/rx_citycare_00053.txt", "lab/report_00047.json", "lab/whatsapp_forward_0012.txt",
    "opd/citycare_opd_2025_01.json", "fhir/bundle_a1b2c3d4.json", "clean/drug_formulary.csv",
    "lab/pathcare_results.csv", "registration/citycare_registration (1).csv", "notes/visitor_log_ward3.txt",
    "discharge/note_0004.txt", "misc/scanned_consent_form.json",
])
def test_clean_paths_are_kept(path):
    # the contract allows a rename only when the name holds PII
    assert sanitize_path(path, KEY) == path


def test_rename_is_keyed_deterministic_and_unique():
    a = "discharge/Discharge_Summary_Hemlata_Chhabra_KMC-25-073318.txt"
    b = "discharge/Discharge_Summary_Jaswant_Kalra_KMC-25-073319.txt"
    assert sanitize_path(a, KEY) == sanitize_path(a, KEY)
    assert sanitize_path(a, KEY) != sanitize_path(a, b"u" * 32)  # a different secret changes names (A7)
    assert sanitize_path(a, KEY) != sanitize_path(b, KEY)  # no collisions between patients


# ---------------------------------------------------------------- JSON keys / column headers
@pytest.mark.parametrize("label", ["Hemlata Chhabra", "9876501234", "KMC-0073318 Temp", "uhid_KMC-0073318", "Jaswant Kalra"])
def test_pii_labels(label):
    assert label_has_pii(label)
    new = safe_label(label, KEY)
    assert new.startswith("field_") and new == safe_label(label, KEY)


@pytest.mark.parametrize("label", ["visit_id", "patient_ref", "temp_f", "spo2", "Janm Tithi", "Gaon", "Pita/Pati ka Naam",
                                   "Pin Code", "Reg No", "Mobile No", "Registration Date", "जन्म तिथि", "नाम", "exported_by",
                                   "source_path", "by_name", "weight_kg", "Umar", "Ling"])
def test_schema_labels_kept(label):
    assert safe_label(label, KEY) == label


# ---------------------------------------------------------------- path-like metadata
def test_folder_named_after_patient_is_removed_with_its_digits():
    text = "D:\\HIS\\exports\\opd\\Hemlata_Chhabra_020311\\visits_2025_01.json"
    assert covered(text, "Hemlata_Chhabra_020311", field="source_path")
    assert untouched(text, "visits_2025_01", field="source_path")
    assert untouched(text, "exports", field="source_path")


def test_folder_with_first_name_and_initials():
    text = "D:\\HIS\\exports\\opd\\Hemlata_HC_020311\\visits_2025_01.json"
    assert covered(text, "Hemlata_HC_020311", field="source_path")
    assert untouched(text, "visits_2025_01", field="source_path")


def test_unix_path_with_id_component():
    text = "/data/export/KMC-25-073318/notes.txt"
    assert covered(text, "KMC-25-073318", field="meta.file")


@pytest.mark.parametrize("text,keep", [("K/C/O diabetes", "K/C/O"), ("S/o Gurmeet", "S/o"), ("C/O fever 3 days", "fever"),
                                       ("1-0-1 x 5 days", "1-0-1"), ("BP 120/80", "120/80")])
def test_slashes_in_clinical_text_are_not_paths(text, keep):
    assert untouched(text, keep)


def test_mrn_is_not_doubled_by_path_rule():
    s = _spans("IP/25/00321")
    assert len(s) == 1 and s[0].type == PIIType.MRN


# ---------------------------------------------------------------- encoded runs
def _b64(s):
    return base64.b64encode(s.encode()).decode()


def test_base64_with_pii_is_removed():
    blob = _b64("Consent given by Hemlata Chhabra, mobile 9876501234")
    assert covered(f"attachment: {blob}", blob)


def test_base64_without_pii_is_kept():
    blob = _b64("Informed consent form, version 3, standard template text")
    assert untouched(f"attachment: {blob}", blob)


def test_ids_and_hashes_are_not_decoded_as_text():
    for tok in ["3f9a1c2e7b4d4e0a9c1f2b3d4e5f6a7b", "ZmY4ZTk0YmMtMTIzNC00NTY3LWFiY2QtZWY5ODc2NTQzMjEw"[:24] + "x" * 8]:
        assert all(not d or not any(c.isalpha() for c in d) for _, _, d in encoded_runs(tok)) or not encoded_runs(tok)


@pytest.mark.parametrize("enc", [
    lambda s: s.encode().hex(),
    lambda s: "".join(f"\\u{ord(c):04x}" for c in s),
    lambda s: "".join(f"&#{ord(c)};" for c in s),
])
def test_other_encodings_with_pii_are_removed(enc):
    run = enc("Mobile 9876501234")
    assert covered(f"x {run} y", run)


def test_clean_encoded_keeps_valid_base64():
    blob = _b64("Consent by Hemlata Chhabra, mobile 9876501234")
    out = clean_encoded(f"data={blob}", lambda s: s.replace("9876501234", "[PHONE]"))
    new = out.split("=", 1)[1]
    decoded = base64.b64decode(new, validate=True).decode()
    assert "9876501234" not in decoded and "[PHONE]" in decoded and "Consent by" in decoded


def test_clean_encoded_leaves_untouched_runs_byte_identical():
    blob = _b64("standard consent template text only")
    assert clean_encoded(blob, lambda s: s) == blob


# ---------------------------------------------------------------- homoglyphs
def test_fold_is_one_to_one():
    s = "Hеmlаtа Chhаbrа"  # Cyrillic а / е
    f = fold_homoglyphs(s)
    assert len(f) == len(s) and f == "Hemlata Chhabra"


def test_devanagari_is_not_folded():
    assert fold_homoglyphs("कमला देवी") == "कमला देवी"


def test_homoglyph_disguised_phone_label_and_name():
    text = "Patient: Hеmlаtа Chhаbrа, Mоbile 9876501234"
    assert covered(text, "Hеmlаtа Chhаbrа")
