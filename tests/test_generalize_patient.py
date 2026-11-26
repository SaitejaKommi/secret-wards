"""Per-patient generalization, birth-year bands, tehsil placeholder, DOB override in rendering. Invented values only."""
from secretwards.config import Config
from secretwards.contracts import Document, Mention, PIIType, Span
from secretwards.pipeline import make_unit
from secretwards.privacy.generalize import Facts, dob_text, extract_facts, overrides, plan_levels, qi_key
from secretwards.privacy.render import redact


def test_one_level_per_patient_the_coarsest_needed():
    cfg = Config()
    cfg.k_target = 2
    facts, pseud = {}, {}
    # patient P has two records: one would be fine at level 0 alone, the other is unique; both must get P's level
    facts["p1"] = Facts("p1", age=40, sex="F", district="fatehganj")
    facts["p2"] = Facts("p2", age=40, sex="F", district="fatehganj", tehsil="bhaironpur", birth_year=1985)
    pseud["p1"] = pseud["p2"] = "P"
    facts["q1"] = Facts("q1", age=40, sex="F", district="fatehganj")
    pseud["q1"] = "Q"
    levels, _sup, _rare = plan_levels(facts, pseud, cfg)
    assert levels["p1"] == levels["p2"] >= 3       # pooled: P's birth year and tehsil force a band for every record


def test_qi_key_hides_birth_year_and_tehsil_from_level_3():
    cfg = Config()
    f = Facts("d", age=47, sex="M", birth_year=1943, district="fatehganj", tehsil="bhaironpur")
    k0, k3 = qi_key(f, 0, cfg), qi_key(f, 3, cfg)
    assert 1943 in k0 and "bhaironpur" in k0
    assert 1943 not in k3 and "bhaironpur" not in k3 and "1940-1944" in k3


def test_dob_text_is_a_truthful_band():
    assert dob_text(1943, 2, False) is None            # exact ages: the day-shifted date stays
    assert dob_text(1943, 3, False) == "1940-1944"
    assert dob_text(1943, 4, False) == "1940-1949"
    assert dob_text(1943, 6, False) == "1940-1959"
    assert dob_text(1943, 3, True) == "1940"           # FHIR birthDate must stay a valid date


def _facts_for(text, field=None):
    doc = Document("d", "h", "txt" if field is None else "csv", 0, text if field is None else "", {} if field is None else {field: text})
    u = make_unit("d", field, text)
    spans = {u.field: [Span("d", u.field, s, e, PIIType.DATE, "rules", 0.9) for s, e in _dates(text)]}
    return extract_facts(doc, [u], spans, {u.field: []}, Mention("d", "h")), u, spans


def _dates(text):
    from secretwards.normalize.dates import find_dates
    return [(m.start, m.end) for m in find_dates(text)]


def test_dob_label_in_text_and_dob_column_are_found():
    f, _u, _s = _facts_for("Name: X\nDOB: 14/06/1943\nAdmitted 02/03/2025")
    assert f.birth_year == 1943 and len(f.dob_spans) == 1
    g, _u, _s = _facts_for("14/06/1943", field="Janm Tithi")
    assert g.birth_year == 1943


def test_tehsil_column_and_label():
    f, _u, _s = _facts_for("Bhaironpur", field="Tehsil")
    assert f.tehsil == "bhaironpur" and f.tehsil_spans
    g, _u, _s = _facts_for("H.No. 9, Tehsil Bhaironpur, Distt. Fatehganj")
    assert g.tehsil == "bhaironpur" and g.district == "fatehganj"


def test_overrides_band_the_dob_and_hide_tehsil_at_level_3():
    text = "DOB: 14/06/1943, Tehsil Bhaironpur, Distt. Fatehganj"
    f, u, spans = _facts_for(text)
    ov = overrides(f, {None: text}, 3, False, Config())
    out = redact(text, spans[None], 40, ov[None])
    assert "1940-1944" in out and "14/06/1943" not in out
    assert "[TEHSIL]" in out and "Bhaironpur" not in out and "Fatehganj" in out


def test_low_level_keeps_the_shifted_date():
    text = "DOB: 14/06/1943"
    f, u, spans = _facts_for(text)
    ov = overrides(f, {None: text}, 0, False, Config())
    out = redact(text, spans[None], 40, ov[None])
    assert "1943" in out and "14/06/1943" not in out   # day-shifted, same format


def test_age_from_the_record_when_the_linker_found_none():
    text = "48"
    doc = Document("d", "h", "json", 0, "", {"age": text})
    u = make_unit("d", "age", text)
    f = extract_facts(doc, [u], {"age": []}, {"age": []}, Mention("d", "h"))
    assert f.age == 48 and f.age_spans
