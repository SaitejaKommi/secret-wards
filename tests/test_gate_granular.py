"""The leak gate removes an identifier it knows from elsewhere, and a field that still leaks loses only the leaking lines (invented values)."""
from secretwards.contract.run import run_contract
from secretwards.security.leak_gate import RawValues, _blank_leaking_lines, _repair, scan


def rv(**kw):
    r = RawValues()
    for k, v in kw.items():
        if k == "alnum":
            for x in v:
                r.alnum[len(x)].add(x)
        else:
            getattr(r, k).update(v)
    return r


# ---- repair now removes identifiers
def test_repair_removes_a_known_identifier_in_any_spelling():
    r = rv(alnum=["181497926497", "UH2570827"])
    for text in ("Aadhaar 1814-9792-6497.", "Aadhaar 1814 9792 6497.", "Aadhaar 181497926497.", "uhid UH/25/70827 seen"):
        out = _repair(r, text)
        assert "[ID]" in out and not scan(r, out), (text, out)


def test_repair_leaves_the_text_around_the_identifier_alone():
    r = rv(alnum=["181497926497"])
    out = _repair(r, "BP 119/86 mmHg. Aadhaar 1814-9792-6497. Tab Metformin 500 mg 1-0-1.")
    assert out == "BP 119/86 mmHg. Aadhaar [ID]. Tab Metformin 500 mg 1-0-1." or ("119/86 mmHg" in out and "500 mg 1-0-1" in out and "1814" not in out)


# ---- the last resort blanks lines, not documents
def test_only_the_leaking_line_is_blanked():
    r = rv(names=["quillfeather"])
    text = "WARD NOTE\nBP 119/86 mmHg\nSeen: quillfeather today\nTab Metformin 500 mg 1-0-1\n"
    out = _blank_leaking_lines(r, text)
    assert out == "WARD NOTE\nBP 119/86 mmHg\n[REDACTED]\nTab Metformin 500 mg 1-0-1\n"


def test_crlf_line_endings_are_kept():
    r = rv(names=["quillfeather"])
    assert _blank_leaking_lines(r, "a\r\nquillfeather\r\nb\r\n") == "a\r\n[REDACTED]\r\nb\r\n"


def test_a_leak_that_spans_lines_still_fails_closed():
    r = rv(phones=["9871234560"])
    text = "ok line\nphone 98712\n34560 end\nBP 120/80 mmHg\n"   # one number split over two lines: no single line holds it
    out = _blank_leaking_lines(r, text)
    assert not scan(r, out)                                       # never leaves the leak
    assert out == "[REDACTED]" or "98712" not in out or "34560" not in out


def test_a_single_line_field_is_blanked_whole_as_before():
    r = rv(names=["quillfeather"])
    assert _blank_leaking_lines(r, "Zephyrine quillfeather") == "[REDACTED]"


def test_clean_text_is_untouched():
    assert _blank_leaking_lines(rv(names=["quillfeather"]), "BP 120/80 mmHg\n") == "BP 120/80 mmHg\n"


# ---- end to end: an identifier the detectors miss in one note but see in another file
def test_note_with_an_identifier_found_elsewhere_keeps_its_medical_content(tmp_path):
    inp, out = tmp_path / "in", tmp_path / "out"
    inp.mkdir()
    (inp / "reg.csv").write_text("Reg No,Pt Nm,Aadhaar\nUH/25/70827,Zephyrine Quillfeather,1814 9792 6497\n", encoding="utf-8", newline="")
    (inp / "note.txt").write_text(
        "WARD NOTE\nPatient: Zephyrine Quillfeather (68y/M)\nBP 119/86 mmHg, SpO2 92 %. Tab Omeprazole 20 mg 1-0-0 x 10 days continue.\n"
        "Consultant: Dr. Rao. Aadhaar 1814-9792-6497. Ward 4 bed 5.\n", encoding="utf-8", newline="")
    assert run_contract(inp, out, b"gate-secret") == 0
    text = (out / "sanitized" / "note.txt").read_text(encoding="utf-8")
    assert text.strip() != "[REDACTED]"
    assert "1814" not in text and "6497" not in text and "Quillfeather" not in text
    assert "119/86 mmHg" in text and "SpO2 92 %" in text and "Omeprazole 20 mg 1-0-0 x 10 days" in text and "Dr. Rao" in text and "Ward 4 bed 5" in text
