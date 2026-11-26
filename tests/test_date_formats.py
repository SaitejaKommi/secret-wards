"""Dates in every common written form are found, shifted, and keep their interval (invented values).

Regression for: "15-Jul-1958", "15/Jul/1958", "15Jul1958", "Nov-15-1958" were left unshifted because the date finder only ran on the
OCR digit view (which turns the letters of a month name into digits), and "JAN-05-1958" was typed as a hospital number.
"""
import datetime as dt

import pytest

from secretwards.contract.run import run_contract
from secretwards.contracts import PIIType
from secretwards.detect import default_detectors, detect_unit
from secretwards.normalize.dates import find_dates
from secretwards.pipeline import make_unit

DETS = default_detectors()
EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
HI = ["जनवरी", "फरवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"]


def date_covered(text, date):
    i = text.index(date)
    spans, _ = detect_unit(make_unit("d", None, text), DETS)
    return any(s.type == PIIType.DATE and s.start <= i and s.end >= i + len(date) for s in spans)


def test_every_month_in_every_common_layout_is_found():
    """All 12 months x abbreviated / full / upper-case / Hindi x the usual separators x 2- and 4-digit years, day-first and month-first."""
    missed = []
    for mi in range(12):
        for mon in (EN[mi][:3], EN[mi], EN[mi][:3].upper(), HI[mi]):
            for sep in ("-", "/", ".", " "):
                for yr in ("1958", "58"):
                    for day in ("5", "23"):
                        forms = [f"{day}{sep}{mon}{sep}{yr}"]
                        if mon != HI[mi] and len(yr) == 4:
                            forms.append(f"{mon}{sep}{day}{', ' if sep == ' ' else sep}{yr}")
                        for d in forms:
                            if not date_covered(f"Admitted on {d}. BP 120/80 mmHg.", d):
                                missed.append(d)
    assert not missed, f"{len(missed)} formats missed, e.g. {missed[:8]}"


@pytest.mark.parametrize("admit,discharge", [
    ("15-Jul-1958", "24-Jul-1958"), ("15/Jul/1958", "24/Jul/1958"), ("15Jul1958", "24Jul1958"), ("15-Jul-58", "24-Jul-58"),
    ("Nov-15-1958", "Nov-24-1958"), ("15-Sep-1958", "24-Sep-1958"), ("15-Oct-1958", "24-Oct-1958"), ("15-Nov-1958", "24-Nov-1958"),
    ("JAN-05-1958", "JAN-14-1958"), ("15 Jul 1958", "24 Jul 1958"), ("15.07.1958", "24.07.1958"), ("15 जुलाई 1958", "24 जुलाई 1958"),
])
def test_dates_are_shifted_and_the_stay_keeps_its_length(tmp_path, admit, discharge):
    inp, out = tmp_path / "in", tmp_path / "out"
    inp.mkdir()
    (inp / "n.txt").write_text(f"Patient seen. Admitted on {admit}. Discharged on {discharge}. BP 120/80 mmHg. Tab Metformin 500 mg 1-0-1.\n", encoding="utf-8", newline="")
    assert run_contract(inp, out, b"date-test-secret") == 0
    text = (out / "sanitized" / "n.txt").read_text(encoding="utf-8")
    assert admit not in text and discharge not in text, text
    ms = find_dates(text)
    assert len(ms) == 2, text
    a, b = (dt.date(m.y, m.m, m.d) for m in ms)
    assert (b - a).days == 9  # length of stay unchanged
    assert "120/80 mmHg" in text and "Metformin 500 mg 1-0-1" in text


def test_exact_date_of_birth_in_a_table_cell_is_shifted(tmp_path):
    inp, out = tmp_path / "in", tmp_path / "out"
    inp.mkdir()
    rows = "\n".join(f"UH/25/{1000 + i};Patient {i};15-{m}-1958;M" for i, m in enumerate(["Jan", "Jul", "Sep", "Oct", "Nov", "Dec"]))
    (inp / "r.csv").write_text("Reg No;Pt Nm;Janm Tithi;Ling\n" + rows + "\n", encoding="utf-8", newline="")
    assert run_contract(inp, out, b"date-test-secret") == 0
    lines = (out / "sanitized" / "r.csv").read_text(encoding="utf-8").splitlines()[1:]
    for m, line in zip(["Jan", "Jul", "Sep", "Oct", "Nov", "Dec"], lines):
        assert f"15-{m}-1958" not in line, line
