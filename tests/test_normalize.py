import pytest

from secretwards.normalize.dates import find_dates, render, shift
from secretwards.normalize.text import normalize, ocr_digit_view
from secretwards.normalize.translit import skeleton, to_latin


@pytest.mark.parametrize("text", [
    "Mohd  Rajesh\t\tKumar", "  leading and trailing  ", "फोन: ९८७६५४३२१०", "a​b‍c", "line1  \n  line2", "“quoted” – dash",
])
def test_offset_map_points_back_to_the_same_characters(text):
    n = normalize(text)
    assert len(n.starts) == len(n.text) == len(n.ends)
    for i, ch in enumerate(n.text):
        orig = text[n.starts[i]:n.ends[i]]
        assert orig, "every normalized char maps to at least one original char"
        if ch.isalnum() and orig.isascii():
            assert orig.lower() == ch.lower()


def test_span_roundtrip_on_devanagari_digits():
    t = "फोन ९८७६५४३२१० है"
    n = normalize(t)
    i = n.text.index("9876543210")
    a, b = n.to_orig(i, i + 10)
    assert t[a:b] == "९८७६५४३२१०"


def test_fast_path_equals_slow_path():
    from secretwards.normalize.text import _normalize_slow

    for t in ["abc def", "Hello 12/03/2021.", "a\nb c", "", "x  y", " lead", "tab\there"]:
        assert normalize(t) == _normalize_slow(t)


def test_ocr_digit_view_keeps_length_and_fixes_digit_tokens():
    s = "call 98765432lO now, WBC 11200 and O.K."
    v = ocr_digit_view(s)
    assert len(v) == len(s)
    assert "9876543210" in v
    assert v.endswith("O.K.")


@pytest.mark.parametrize("a,b", [
    ("Rajesh", "राजेश"), ("Mohammad", "मोहम्मद"), ("Mohd", "Mohammad"), ("Singh", "सिंह"), ("Shyam", "श्याम"),
    ("Srivastava", "श्रीवास्तव"), ("Lakshmi", "लक्ष्मी"), ("Bansal", "Bnsal"),
])
def test_skeleton_matches_across_scripts_and_spellings(a, b):
    assert skeleton(a) == skeleton(b)


def test_skeleton_separates_different_names():
    assert skeleton("Rajesh") != skeleton("Suresh")
    assert to_latin("कुमार").startswith("kum")


def test_dates_find_shift_and_render_same_style():
    text = "Admitted 12/03/2021, DOB 5.7.45, on 12th March, 2021 and 7 Jan 2016, भर्ती 20 नवंबर 2019, 2021-03-18."
    ms = find_dates(normalize(text).text)
    assert len(ms) == 6
    for m in ms:
        y, mo, d = shift(m, 40)
        out = render(m, y, mo, d)
        # re-parsing the rendered date gives the shifted date
        again = find_dates(out)
        assert again and (again[0].y, again[0].m, again[0].d) == (y, mo, d)


def test_intervals_survive_a_shift():
    import datetime as dt

    a, b = find_dates("01/03/2021")[0], find_dates("11/03/2021")[0]
    ya, ma, da = shift(a, -100)
    yb, mb, db = shift(b, -100)
    assert (dt.date(yb, mb, db) - dt.date(ya, ma, da)).days == 10
