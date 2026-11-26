"""Stand-in attacker (privacy/attack.py) on an invented population. No practice data."""
import datetime as dt

import pytest

from secretwards.privacy import attack as A

REG_CSV = """rid,name,relation,relative_name,gender,age,house_no,mohalla,village,tehsil,district,pin,phone,email,aadhaar_last4
R1,Tejbir Tiklani,S/o,Harbans Tiklani,M,44,87,Neem Tola,Kesarpura,Bhaironpur,Fatehganj,201301,9871234560,,4821
R2,Navjot Tiklani,W/o,Tejbir Tiklani,F,41,87,Neem Tola,Kesarpura,Bhaironpur,Fatehganj,201301,,,
R3,Sushila Lohani,D/o,Harbhajan Lohani,F,29,12,,Lakhanpur,Bhaironpur,Fatehganj,201302,9812345670,sushila.l77@example.org,5038
R4,Bhupinder Bhandari,S/o,Tulsi Bhandari,M,62,739,,Sundarpur,Kotdwar,Pauriwal,246149,,,
R5,Bhupinder Bisht,S/o,Harbhajan Bisht,M,64,22,,Sundarpur,Kotdwar,Pauriwal,246149,9934567810,,
R6,Hemlata Chhabra,W/o,Jaswant Chhabra,F,35,5,,Lakhanpur,Bhaironpur,Fatehganj,201302,,,
R7,Jaswant Chhabra,S/o,Gurmeet Chhabra,M,38,5,,Lakhanpur,Bhaironpur,Fatehganj,201302,,,
R8,Vimla Negi,W/o,Naveen Negi,F,70,9,,Sundarpur,Kotdwar,Pauriwal,246149,,,
"""


@pytest.fixture()
def reg(tmp_path):
    p = tmp_path / "registry.csv"
    p.write_text(REG_CSV, encoding="utf-8")
    return A.Registry.load(p)


def top(probs):
    return max(probs.items(), key=lambda kv: kv[1])


# ---------------------------------------------------------------- extraction
@pytest.mark.parametrize("pairs,ages", [
    ([("", "Pt 53/M seen in OPD")], [(53, 53)]),
    ([("age", "40-44")], [(40, 44)]),
    ([("", "45-49 Yrs/F")], [(45, 49)]),
    ([("", "आयु: 62 वर्ष")], [(62, 62)]),
    ([("", "85+ yrs")], [(85, 120)]),
])
def test_age_forms(reg, pairs, ages):
    assert A.extract(pairs, reg).ages == ages


@pytest.mark.parametrize("text", ["K/C/O HTN x 9 yrs", "smoker since 7 yrs", "FBS 65-115 mg/dL"])
def test_durations_and_lab_ranges_are_not_ages(reg, text):
    assert A.extract([("", text)], reg).ages == []


def test_band_is_a_range_not_its_upper_end(reg):
    # reading "40-44 Yrs/F" as exactly 44 would filter out a 41-year-old
    ev = A.extract([("", "40-44 Yrs/F")], reg)
    probs, _ = A.link(ev, reg, 2025)
    assert "R2" in probs


def test_places_only_inside_an_address(reg):
    letterhead = A.extract([("", "Fatehganj Zila Aspatal, OPD slip")], reg)
    assert not letterhead.districts
    addr = A.extract([("", "Address: H.No. 87, Neem Tola, Kesarpura, Distt. Fatehganj")], reg)
    assert {"fatehganj"} <= addr.districts and {"kesarpura"} <= addr.villages and "87" in addr.houses


def test_contacts_and_relatives(reg):
    ev = A.extract([("", "S/o Harbans Tiklani, Mob 98712-34560, Aadhaar XXXX XXXX 4821, e: sushila.l77@example.org, 98XXXXXX70")], reg)
    assert "9871234560" in ev.phones and "4821" in ev.last4s and ("98", "70") in ev.masked_phones
    assert "sushila.l77@example.org" in ev.emails and ev.rels and "M" in ev.genders


def test_doctor_names_are_skipped(reg):
    ev = A.extract([("", "Seen by Dr. Bhupinder Bhandari today")], reg)
    assert not ev.names


def test_lab_reference_columns_do_not_join_patients(reg):
    a = A.extract([("ref range", "65-115"), ("patient_ref", "QX-1234")], reg)
    b = A.extract([("ref range", "65-115"), ("patient_ref", "QX-9876")], reg)
    assert len(A.profiles([a, b])) == 2


# ---------------------------------------------------------------- linkage
def test_filter_that_would_empty_the_set_is_skipped(reg):
    ev = A.extract([("district", "Pauriwal"), ("", "Mob 9000000001"), ("sex", "F"), ("age", "70")], reg)
    probs, used = A.link(ev, reg, 2025)
    assert top(probs)[0] == "R8" and "phone" not in used


def test_name_weights_break_ties(reg):
    ev = A.extract([("district", "Pauriwal"), ("sex", "M"), ("", "Bhupinder Bisht")], reg)
    probs, _ = A.link(ev, reg, 2025)
    assert top(probs)[0] == "R5" and probs["R5"] > 0.8   # full name x60 against the other Bhupinder's given name x8


# ---------------------------------------------------------------- profiles
def test_pooling_intersects_ages_and_joins_by_pseudonym(reg):
    psn = frozenset({"PSN-AAAA1111"})
    a = A.extract([("", "PSN-AAAA1111"), ("age", "60-64"), ("district", "Pauriwal")], reg, psn)
    b = A.extract([("", "Patient: PSN-AAAA1111"), ("sex", "M"), ("age", "62")], reg, psn)
    groups = A.profiles([a, b])
    assert groups == [[0, 1]]
    pooled = A.pool([a, b])
    assert pooled.ages == [(62, 62)]
    probs, _ = A.link(pooled, reg, 2025)
    assert top(probs)[0] == "R4"   # alone, neither record singles anyone out


# ---------------------------------------------------------------- targeted attack and shift recovery
def _profile(reg, rid_text, dates):
    return A.extract([("", rid_text)] + [("", d.strftime("%d/%m/%Y")) for d in dates], reg)


def test_global_shift_is_recovered_but_per_patient_shifts_are_not(reg):
    facts = [A.Fact("R4", [dt.date(2025, 3, 10)], "", "", None), A.Fact("R5", [dt.date(2025, 4, 2)], "", "", None)]
    shift = dt.timedelta(days=17)
    evs = [_profile(reg, "Bhupinder Bhandari S/o Tulsi Bhandari", [dt.date(2025, 3, 10) + shift]),
           _profile(reg, "Bhupinder Bisht S/o Harbhajan Bisht", [dt.date(2025, 4, 2) + shift])]
    tops = [top(A.link(e, reg, 2025)[0]) for e in evs]
    assert A.recover_global_shift(evs, tops, facts) == 17
    evs2 = [_profile(reg, "Bhupinder Bhandari S/o Tulsi Bhandari", [dt.date(2025, 3, 10) + dt.timedelta(days=17)]),
            _profile(reg, "Bhupinder Bisht S/o Harbhajan Bisht", [dt.date(2025, 4, 2) + dt.timedelta(days=-23)])]
    tops2 = [top(A.link(e, reg, 2025)[0]) for e in evs2]
    assert A.recover_global_shift(evs2, tops2, facts) is None


def test_targeted_uses_rare_condition_and_ignores_contradicted_profiles(reg):
    facts = [A.Fact("R8", [dt.date(2025, 5, 1)], "", "acute porphyria", None),
             A.Fact("R0-decoy", [dt.date(2025, 5, 1)], "", "", None)]
    evs = [A.extract([("", "Dx: acute porphyria"), ("sex", "F"), ("age", "70")], reg),
           A.extract([("", "01/05/2025 review"), ("sex", "M"), ("age", "29")], reg)]
    out = A.targeted(facts, evs, reg, 2025, None)
    assert out["R8"] == {0: 1.0}          # the second profile's evidence rules R8 out
    assert out["R0-decoy"]                # a decoy can still be "claimed": reported as a false positive


def test_deterministic(reg):
    ev = A.extract([("", "Address: H.No. 87, Neem Tola, Distt. Fatehganj, 53/M")], reg)
    assert A.link(ev, reg, 2025) == A.link(ev, reg, 2025)
