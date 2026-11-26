"""Two wrong merges found by the stress test, and the general rules that prevent them (invented values only):
1. "Surname, Given" names lost the given name, so a different first name could not veto a match (and an unseen given name leaked).
2. A document that lists many patients (ward log) bridged two different people who share a name.
"""
import json

import pytest

from secretwards.config import Config
from secretwards.contract.run import run_contract
from secretwards.contracts import Mention, PIIType
from secretwards.detect import default_detectors, detect_unit
from secretwards.link import link_documents
from secretwards.link.compare import evaluate
from secretwards.link.mention import build_mention
from secretwards.pipeline import make_unit, process_doc
from secretwards.contracts import Document
from secretwards.security.keys import keys_from_secret

DETS = default_detectors()


def names_in(field, text):
    s, _ = detect_unit(make_unit("d", field, text), DETS)
    return [text[x.start:x.end] for x in s if x.type == PIIType.NAME]


# ---- 1. "Surname, Given" is one name in a name context
@pytest.mark.parametrize("field,text,expected", [
    ("Pt Nm", "Pillai, Thiruvengadam", "Pillai, Thiruvengadam"),
    ("Pt Nm", "Subramaniam, S. Kumar", "Subramaniam, S. Kumar"),
    ("Pt Nm", "Kulkarni, Mallikarjun Rao", "Kulkarni, Mallikarjun Rao"),
    (None, "Name: Pillai, Thiruvengadam. Age 40", "Pillai, Thiruvengadam"),
    (None, "Patient Name: Qureshi, Ibrahim", "Qureshi, Ibrahim"),
])
def test_surname_comma_given_is_one_name(field, text, expected):
    assert expected in names_in(field, text)


@pytest.mark.parametrize("text,expected", [
    ("Patient: Ramesh, Tab Metformin 500 mg", ["Ramesh"]),        # a drug after the comma is not a given name
    ("Name: Ramesh, Age 40", ["Ramesh"]),
    ("Patient: Ramesh Verma, Thiruvengadam Pillai accompanied", ["Ramesh Verma", "Thiruvengadam Pillai"]),  # two people, not one
])
def test_comma_does_not_join_unrelated_words_or_two_people(text, expected):
    assert names_in(None, text) == expected


def test_mention_keeps_both_parts_of_a_comma_name():
    doc = Document("d1", "h", "csv", 0, "", {"Pt Nm": "Pillai, Thiruvengadam", "Mobile": "9871110001"})
    r = process_doc(doc, DETS)
    m = build_mention(doc, r.units, r.spans, r.meds)
    assert set(m.name_tokens) == {"Pillai", "Thiruvengadam"}


# ---- 2. two different national ids are two different people
def M(doc, **kw):
    return Mention(doc, kw.pop("hosp", "H"), **kw)


def test_different_aadhaar_is_a_hard_veto():
    a = M("a", name_tokens=("Asha", "Verma"), mrn=("AADHAAR412345678901",), phones=("9871110001",))
    b = M("b", name_tokens=("Asha", "Verma"), mrn=("AADHAAR512345678902",), phones=("9871110001",))
    assert evaluate(a, b).veto == "national_id_differs"


def test_one_typo_in_an_aadhaar_is_not_a_veto_and_different_pan_is():
    a = M("a", name_tokens=("Asha", "Verma"), mrn=("AADHAAR412345678901",))
    b = M("b", name_tokens=("Asha", "Verma"), mrn=("AADHAAR412345678911",))
    assert evaluate(a, b).veto == ""
    p1 = M("p1", mrn=("PANABCDE1234F",))
    p2 = M("p2", mrn=("PANPQRST6789K",))
    assert evaluate(p1, p2).veto == "national_id_differs"


def test_a_record_that_bridges_two_clusters_cannot_glue_two_patients():
    """P and Q share a name; L mentions both hospital numbers. L may join one of them, never both."""
    keys, cfg = keys_from_secret(b"k"), Config()
    p = M("p", name_tokens=("Asha", "Verma"), mrn=("AADHAAR412345678901", "UH10001"), phones=("9871110001",))
    q = M("q", name_tokens=("Asha", "Verma"), mrn=("AADHAAR512345678902", "UH10002"), phones=("9871110002",))
    bridge = M("l", name_tokens=("Asha", "Verma"), mrn=("UH10001", "UH10002"))
    clusters = link_documents([p, q, bridge], keys, cfg)
    which = {d: i for i, c in enumerate(clusters) for d in c.doc_ids}
    assert which["p"] != which["q"]


# ---- 3. a document naming many people carries no identity evidence
def test_a_ward_log_gives_no_evidence():
    lines = "\n".join(f"{i} Patient: {n} UH/25/{20000 + i} ph 98711100{i:02d}" for i, n in enumerate(
        ["Asha Verma", "Ravi Kulkarni", "Meena Pillai", "Sunil Hosamani", "Farida Qureshi", "Gurmeet Sidhu", "Lalitha Gowda", "Ibrahim Naskar"]))
    doc = Document("log", "h", "txt", 0, lines, {})
    r = process_doc(doc, DETS)
    m = build_mention(doc, r.units, r.spans, r.meds)
    assert not m.phones and not m.mrn and not m.name_tokens


def test_an_ordinary_note_still_gives_evidence():
    doc = Document("n", "h", "txt", 0, "Patient: Asha Verma, UHID UH/25/10001, ph 9871110001. Attendant: Ravi Kulkarni ph 9871110002.", {})
    r = process_doc(doc, DETS)
    m = build_mention(doc, r.units, r.spans, r.meds)
    assert m.phones and m.mrn and m.name_tokens


# ---- end to end: the two cases from the audit
def test_homonyms_and_brothers_stay_apart_end_to_end(tmp_path):
    inp, out = tmp_path / "in", tmp_path / "out"
    (inp / "reg").mkdir(parents=True)
    (inp / "opd").mkdir()
    (inp / "notes").mkdir()
    # patients 0 and 1 share a name; patients 2 and 3 are brothers (same phone, same father, different first names)
    reg = ("Reg No;Pt Nm;Sampark;Aadhaar;Rishtedar\n"
           "UH/25/10001;Zephyrine Quillfeather;9871110001;4123 4567 8901;S/o Nagabhushan Quillfeather\n"
           "UH/25/10002;Zephyrine Quillfeather;9871110002;5123 4567 8902;S/o Ibrahim Quillfeather\n"
           "UH/25/10003;Kuldeep Pillai;9871110003;6123 4567 8903;S/o Nagabhushan Pillai\n"
           "UH/25/10004;Pillai, Thiruvengadam;9871110003;7123 4567 8904;S/o Nagabhushan Pillai\n")
    (inp / "reg" / "reg.csv").write_text(reg, encoding="utf-8", newline="")
    enc = [{"pt": {"nm": nm, "uid": uid}, "note": "BP 120/80 mmHg"} for nm, uid in [
        ("Zephyrine Quillfeather", "UH/25/10001"), ("Zephyrine Quillfeather", "UH/25/10002"),
        ("Kuldeep Pillai", "UH/25/10003"), ("Pillai, Thiruvengadam", "UH/25/10004")]]
    (inp / "opd" / "visits.json").write_text(json.dumps({"encounters": enc}), encoding="utf-8")
    log = "\n".join(f"{i} {n} UH/25/{10001 + i % 4} ph 98711100{i:02d}" for i, n in enumerate(
        ["Zephyrine Quillfeather", "Kuldeep Pillai", "Ravi Hosamani", "Sunil Gowda", "Farida Naskar", "Gurmeet Sidhu", "Lalitha Deshpande", "Ibrahim Subramaniam"])) + "\n"
    (inp / "notes" / "ward_log.txt").write_text(log, encoding="utf-8", newline="")
    assert run_contract(inp, out, b"merge-secret") == 0
    rep = json.loads((out / "report.json").read_text(encoding="utf-8"))
    ps = {}
    for line in (out / "records.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        ps[(r["file"].rsplit("/", 1)[-1][:3], r["loc"])] = r["patient"]
    # find the output names for reg / visits (not renamed here, but do not assume)
    reg_ps = [v for (f, loc), v in ps.items() if loc.startswith("row:")]
    opd_ps = [v for (f, loc), v in ps.items() if loc.startswith("/encounters/")]
    assert len(reg_ps) == 4 and len(opd_ps) == 4
    # each patient's two records agree (recall), the four patients are all different (no wrong merge)
    for a, b in zip(reg_ps, opd_ps):
        assert a is not None and a == b
    assert len(set(reg_ps)) == 4
    # the ward log claims nobody
    assert [v for (f, loc), v in ps.items() if loc == "doc"] == [None]
