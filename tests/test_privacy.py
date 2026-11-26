import datetime as dt

from secretwards.config import Config
from secretwards.contracts import PIIType, Span
from secretwards.normalize.dates import find_dates
from secretwards.privacy.generalize import Facts, age_text, apply_age, pin_text, plan_levels, qi_key
from secretwards.privacy.pseudonym import make_pseudonym, shift_days
from secretwards.privacy.render import redact


def test_date_shift_is_per_patient_stable_nonzero_and_in_range(keys):
    cfg = Config()
    p1, p2 = make_pseudonym(keys, "x"), make_pseudonym(keys, "y")
    assert shift_days(keys, cfg, p1) == shift_days(keys, cfg, p1)
    shifts = {shift_days(keys, cfg, make_pseudonym(keys, str(i))) for i in range(50)}
    assert len(shifts) > 25  # different patients get different shifts
    for i in range(200):
        d = shift_days(keys, cfg, make_pseudonym(keys, str(i)))
        assert cfg.date_shift_min_days <= abs(d) <= cfg.date_shift_max_days


def test_free_text_and_structured_dates_shift_together(keys):
    text = "Admitted 01/03/2021 and discharged on 11 March 2021."
    ms = find_dates(text)
    spans = [Span("d", None, m.start, m.end, PIIType.DATE, "t", 1.0) for m in ms]
    out = redact(text, spans, 100)
    again = find_dates(out)
    a = dt.date(again[0].y, again[0].m, again[0].d)
    b = dt.date(again[1].y, again[1].m, again[1].d)
    assert (b - a).days == 10  # length of stay preserved
    assert a != dt.date(2021, 3, 1)


def test_unparseable_date_is_redacted_not_guessed():
    out = redact("on Jan-16", [Span("d", None, 3, 9, PIIType.DATE, "t", 1.0)], 40)
    assert out == "on [DATE]"


def test_age_generalization_and_top_coding():
    cfg = Config()
    assert age_text(47, 0, cfg) == "47"
    assert age_text(47, 3, cfg) == "45-49"
    assert age_text(47, 4, cfg) == "40-49"
    assert age_text(93, 0, cfg) == "90+"
    assert apply_age("47 years", 47, 3, cfg) == "45-49 years"
    assert apply_age("47Y", 47, 3, cfg) == "45-49Y"
    assert apply_age("47 years", 47, 0, cfg) == "47 years"


def test_pin_is_reduced_then_removed():
    cfg = Config()
    assert pin_text("560034", 0, cfg) == "560XXX"
    assert pin_text("560034", 1, cfg) == "56XXXX"
    assert pin_text("560034", 2, cfg) == "[PIN]"


def test_only_records_that_violate_k_are_generalized():
    cfg = Config()
    cfg.k_target = 3
    facts, pseud = {}, {}
    # 4 patients share (age 30, F, 5600xx, flu); one patient is unique (age 71, M, 1100xx, rare disease)
    for i in range(4):
        facts[f"d{i}"] = Facts(f"d{i}", age=30, sex="F", pin="560001", dx="flu")
        pseud[f"d{i}"] = f"p{i}"
    facts["u"] = Facts("u", age=71, sex="M", pin="110001", dx="wilson disease")
    pseud["u"] = "pu"
    levels, suppress, rare = plan_levels(facts, pseud, cfg)
    assert all(levels[f"d{i}"] == 0 for i in range(4))  # the common group keeps exact age and PIN prefix
    assert levels["u"] > 0
    assert "wilson disease" in rare


def test_pseudonym_is_not_reversible_without_key(keys):
    ps = make_pseudonym(keys, "phone:9876543210")
    assert ps.startswith("PT-") and "9876543210" not in ps and len(ps) > 12
