"""Canonical diagnosis key and whole-entry suppression extent. Invented text; standard ICD-10 titles not used in the practice data."""
import pytest

from secretwards.contracts import Document, Mention
from secretwards.detect.diagnosis import dx_entry_end, dx_key
from secretwards.pipeline import make_unit
from secretwards.privacy.generalize import extract_facts


@pytest.mark.parametrize("a,b", [
    ("Migraine, unspecified (G43.9)", "माइग्रेन (G43.9)"),
    ("Gout, unspecified (M10.9)", "गठिया (M10.9)"),
    ("Mumps without complication (B26.9)", "गलसुआ (B26.9)"),
])
def test_same_code_same_key_across_languages(a, b):
    assert dx_key(a) == dx_key(b)


def test_key_without_code_is_normalized_text():
    assert dx_key("  Viral   Fever ") == dx_key("viral fever") == "viral fever"


def test_different_codes_differ():
    assert dx_key("Migraine (G43.9)") != dx_key("Gout (M10.9)")


@pytest.mark.parametrize("text,entry", [
    ("Diagnosis: Gout, unspecified (M10.9); Cholera (A00.9)", "Gout, unspecified (M10.9)"),
    ("Diagnosis: Cushing's syndrome, unspecified (E24.9); Acute pharyngitis (J02.9)", "Cushing's syndrome, unspecified (E24.9)"),
    ("Diagnosis: Viral fever. Tab. Cetirizine 10 mg 0-0-1 x 3 days.", "Viral fever"),
    ("निदान: माइग्रेन (G43.9); गठिया (M10.9)", "माइग्रेन (G43.9)"),
    ("Dx: Calculus of kidney, left side (N20.0)\nAdvice: review", "Calculus of kidney, left side (N20.0)"),
    ("Dx: Viral fever, Tab Cetirizine 10 mg 0-0-1", "Viral fever"),
    ("Dx: Allergic rhinitis (J30.4), Tab Montelukast 10 mg 0-0-1", "Allergic rhinitis (J30.4)"),
])
def test_entry_extent_keeps_commas_and_codes(text, entry):
    start = text.index(":") + 2
    assert text[start:dx_entry_end(text, start)] == entry


def _facts(text):
    doc = Document("d", "h", "txt", 0, text, {})
    u = make_unit("d", None, text)
    return extract_facts(doc, [u], {None: []}, {None: []}, Mention("d", "h"))


def test_suppression_span_covers_the_code():
    # suppressing "Gout" but leaving "(M10.9)" would still name the disease
    text = "Diagnosis: Gout, unspecified (M10.9); \nBP 120/80"
    f = _facts(text)
    (fld, a, b), = f.dx_spans
    assert text[a:b] == "Gout, unspecified (M10.9)"
    assert f.dx == "M10.9"
