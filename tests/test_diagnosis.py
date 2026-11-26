"""Canonical diagnosis key and whole-entry suppression extent. Invented text only."""
import pytest

from secretwards.contracts import Document, Mention
from secretwards.detect.diagnosis import dx_entry_end, dx_key
from secretwards.pipeline import make_unit
from secretwards.privacy.generalize import extract_facts


@pytest.mark.parametrize("a,b", [
    ("Pneumonia, unspecified organism (J18.9)", "निमोनिया (J18.9)"),
    ("Type 2 diabetes mellitus (E11.9)", "टाइप 2 डायबिटीज़ (E11.9)"),
    ("COVID-19, virus identified (U07.1)", "कोविड-19 (U07.1)"),
])
def test_same_code_same_key_across_languages(a, b):
    assert dx_key(a) == dx_key(b)


def test_key_without_code_is_normalized_text():
    assert dx_key("  Dengue   Fever ") == dx_key("dengue fever") == "dengue fever"


def test_different_codes_differ():
    assert dx_key("Asthma (J45.9)") != dx_key("COPD (J44.9)")


@pytest.mark.parametrize("text,entry", [
    ("Diagnosis: Anaemia, unspecified (D64.9); Malaria (B54)", "Anaemia, unspecified (D64.9)"),
    ("Diagnosis: Addison's disease (E27.1); Typhoid fever (A01.0)", "Addison's disease (E27.1)"),
    ("Diagnosis: Dengue fever. Tab. Dolo 650 BD x 5 days.", "Dengue fever"),
    ("निदान: दमा (J45.9); रेबीज़ (A82.9)", "दमा (J45.9)"),
    ("Dx: Chronic kidney disease, stage 3 (N18.3)\nAdvice: review", "Chronic kidney disease, stage 3 (N18.3)"),
    ("Dx: Viral fever, Tab Paracetamol 500 mg 1-0-1", "Viral fever"),
    ("Dx: Asthma (J45.9), Tab Montelukast 10 mg 0-0-1", "Asthma (J45.9)"),
])
def test_entry_extent_keeps_commas_and_codes(text, entry):
    start = text.index(":") + 2
    assert text[start:dx_entry_end(text, start)] == entry


def _facts(text):
    doc = Document("d", "h", "txt", 0, text, {})
    u = make_unit("d", None, text)
    return extract_facts(doc, [u], {None: []}, {None: []}, Mention("d", "h"))


def test_suppression_span_covers_the_code():
    # suppressing "Anaemia" but leaving "(D64.9)" would still name the disease
    text = "Diagnosis: Anaemia, unspecified (D64.9); \nBP 120/80"
    f = _facts(text)
    (fld, a, b), = f.dx_spans
    assert text[a:b] == "Anaemia, unspecified (D64.9)"
    assert f.dx == "D64.9"
