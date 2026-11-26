"""Regression tests for the three problems reported on PR #4 (synthetic values only)."""
import pytest

from secretwards.contracts import PIIType
from secretwards.detect import default_detectors, detect_unit
from secretwards.detect.headers import hint_for
from secretwards.pipeline import make_unit

DETS = default_detectors()


def spans(text, field=None):
    s, _ = detect_unit(make_unit("d", field, text), DETS)
    return s


def untouched(text, value, field=None):
    i = text.index(value)
    j = i + len(value)
    return not any(x.start < j and i < x.end for x in spans(text, field))


# 1. a "Registration Date" column is a date, and FHIR references are not patient numbers
@pytest.mark.parametrize("header", ["Registration Date", "registration_date", "Admission Date", "Date of Registration"])
def test_registration_date_header_is_a_date(header):
    assert hint_for(make_unit("d", header, "x").header).kind in ("date", "dob")


@pytest.mark.parametrize("header", ["Registration No", "Patient ID", "UHID", "MRN"])
def test_id_headers_are_still_ids(header):
    assert hint_for(make_unit("d", header, "x").header).kind == "id"


def test_date_cell_in_a_registration_date_column_is_a_date_not_an_mrn():
    got = {s.type for s in spans("12/03/2024", "Registration Date")}
    assert PIIType.DATE in got and PIIType.MRN not in got


@pytest.mark.parametrize("value", ["urn:uuid:3f2b8c1e-5d4a-4e6f-9a1b-7c8d9e0f1a2b", "Patient/3f2b8c1e-5d4a-4e6f-9a1b-7c8d9e0f1a2b"])
def test_fhir_reference_is_not_typed_as_mrn(value):
    assert PIIType.MRN not in {s.type for s in spans(value, "subject.reference id")}


def test_a_real_id_column_value_is_still_an_mrn():
    assert PIIType.MRN in {s.type for s in spans("KP-88213", "Patient ID")}


# 2. district / zila / jila columns are kept
@pytest.mark.parametrize("header,value", [("District", "Pune"), ("Jila", "Jaipur Rural"), ("District Name", "Nashik"), ("Zila", "Sagar Kheda")])
def test_district_columns_are_not_redacted(header, value):
    assert not spans(value, header)


def test_city_column_is_still_redacted():
    assert spans("Ravet Chowk", "City")


# 3. "ASHA worker" is a role
@pytest.mark.parametrize("text", ["ASHA worker visited the home", "Referred by ASHA didi", "ASHA workers attended the camp"])
def test_asha_worker_is_not_a_name(text):
    assert untouched(text, "ASHA")


def test_asha_as_a_real_name_still_found():
    assert not untouched("Patient Name: Asha Verma", "Asha")
