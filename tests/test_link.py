from secretwards.config import Config
from secretwards.contracts import Mention
from secretwards.link import link_documents
from secretwards.link.compare import evaluate
from secretwards.link import names as N


def M(doc, name=(), rel=(), phones=(), abha=(), dob=None, age=None, ref_year=None, sex=None, pin=None, hosp="H1", mrn=(), emails=(), ins=()):
    return Mention(doc, hosp, name_tokens=tuple(name), rel_tokens=tuple(tuple(r) for r in rel), phones=tuple(phones), abha=tuple(abha),
                   dob=dob, age=age, ref_year=ref_year, sex=sex, pin=pin, mrn=tuple(mrn), emails=tuple(emails), insurance=tuple(ins))


def clusters(ms, keys):
    cfg = Config()
    out = link_documents(ms, keys, cfg)
    return {frozenset(c.doc_ids) for c in out}, {d: c.pseudonym for c in out for d in c.doc_ids}


def test_names_match_across_scripts_orders_and_initials():
    p = lambda s: N.parse(s.split())  # noqa: E731
    assert N.compare(p("Rajesh Kumar"), p("राजेश कुमार"))[0] == 1.0
    assert N.compare(p("Kumar Rajesh"), p("Rajesh Kumar"))[0] == 1.0
    assert N.compare(p("Mohd Imran"), p("मोहम्मद इमरान"))[0] == 1.0
    sim, conflict = N.compare(p("R. Kumar"), p("Rajesh Kumar"))
    assert sim > 0.6 and conflict == 0
    assert N.compare(p("Rajesh Kumar"), p("Suresh Kumar"))[1] == 2  # same surname, different person
    assert N.compare(p("R. Kumar"), p("Suresh Kumar"))[1] == 2  # initial contradicts


def test_same_phone_and_name_across_scripts_links(keys):
    a = M("a", ["Rajesh", "Kumar"], phones=["9876543210"], sex="M")
    b = M("b", ["राजेश", "कुमार"], phones=["9876543210"], sex="M", hosp="H2")
    groups, _ = clusters([a, b], keys)
    assert groups == {frozenset("ab")}


def test_name_alone_never_merges(keys):
    a = M("a", ["Rajesh", "Kumar"], age=47, ref_year=2020, sex="M", pin="226001")
    b = M("b", ["Rajesh", "Kumar"], age=47, ref_year=2020, sex="M", pin="226001", hosp="H2")
    groups, _ = clusters([a, b], keys)
    assert groups == {frozenset("a"), frozenset("b")}


def test_shared_family_phone_with_different_people_does_not_merge(keys):
    a = M("a", ["Rajesh", "Kumar"], phones=["9876543210"], sex="M")
    b = M("b", ["Sunita", "Devi"], phones=["9876543210"], sex="F")
    groups, _ = clusters([a, b], keys)
    assert len(groups) == 2


def test_conflicting_abha_vetoes_even_with_same_phone_and_name(keys):
    a = M("a", ["Rajesh", "Kumar"], phones=["9876543210"], abha=["12345678901234"])
    b = M("b", ["Rajesh", "Kumar"], phones=["9876543210"], abha=["99999999999999"])
    assert evaluate(a, b).veto == "abha_differs"
    groups, _ = clusters([a, b], keys)
    assert len(groups) == 2


def test_different_dob_or_sex_vetoes(keys):
    a = M("a", ["Rajesh", "Kumar"], phones=["9876543210"], dob="1980-01-02")
    b = M("b", ["Rajesh", "Kumar"], phones=["9876543210"], dob="1975-01-02")
    assert evaluate(a, b).veto == "dob_differs"
    c = M("c", ["Rajesh", "Kumar"], phones=["9876543210"], sex="M")
    d = M("d", ["Rajesh", "Kumar"], phones=["9876543210"], sex="F")
    assert evaluate(c, d).veto == "sex_differs"


def test_father_and_son_with_same_name_do_not_merge(keys):
    a = M("a", ["Rajesh", "Kumar"], rel=[["Shyam", "Lal"]], age=30, ref_year=2020, sex="M")
    b = M("b", ["Rajesh", "Kumar"], rel=[["Shyam", "Lal"]], age=62, ref_year=2020, sex="M", hosp="H2")
    groups, _ = clusters([a, b], keys)
    assert len(groups) == 2


def test_relative_name_alone_is_not_enough_but_with_birth_year_it_links(keys):
    a = M("a", ["Rajesh", "Kumar"], rel=[["Shyam", "Lal"]])
    b = M("b", ["राजेश", "कुमार"], rel=[["श्याम", "लाल"]], hosp="H2")
    assert len(clusters([a, b], keys)[0]) == 2
    a2 = M("a", ["Rajesh", "Kumar"], rel=[["Shyam", "Lal"]], age=40, ref_year=2020)
    b2 = M("b", ["राजेश", "कुमार"], rel=[["श्याम", "लाल"]], age=44, ref_year=2024, hosp="H2")
    assert len(clusters([a2, b2], keys)[0]) == 1


def test_no_transitive_overmerge(keys):
    # a~b via phone, b~c via a second phone, but a and c contradict each other (different DOB)
    a = M("a", ["Rajesh", "Kumar"], phones=["9111111111"], dob="1980-01-02")
    b = M("b", ["Rajesh", "Kumar"], phones=["9111111111", "9222222222"])
    c = M("c", ["Rajesh", "Kumar"], phones=["9222222222"], dob="1971-05-09")
    groups, _ = clusters([a, b, c], keys)
    assert not any({"a", "c"} <= g for g in groups)


def test_pseudonyms_are_stable_and_keyed(keys, tmp_path):
    from secretwards.security.keys import generate_keys, load_keys

    a = M("a", ["Rajesh", "Kumar"], phones=["9876543210"])
    g1 = clusters([a], keys)[1]
    g2 = clusters([a], keys)[1]
    assert g1 == g2
    generate_keys(tmp_path / "other")
    other = load_keys(tmp_path / "other")
    assert clusters([a], other)[1] != g1  # a different key gives unrelated pseudonyms
    assert "9876543210" not in g1["a"]


def test_cluster_pseudonym_does_not_depend_on_input_order(keys):
    ms = [M("a", ["Rajesh", "Kumar"], phones=["9876543210"]), M("b", ["Rajesh", "Kumar"], phones=["9876543210"], hosp="H2"),
          M("c", ["Anil", "Gupta"], phones=["9000000001"])]
    assert clusters(ms, keys)[1] == clusters(list(reversed(ms)), keys)[1]


# ---- shared patient ids across different documents / sites (synthetic values only)
def test_same_national_id_links_across_sites():
    a = M("a", name=("Asha", "Verma"), mrn=("AADHAAR111122223333",), hosp="lab")
    b = M("b", name=("Asha", "Verma"), mrn=("AADHAAR111122223333",), hosp="opd")
    r = evaluate(a, b)
    assert "mrn" in r.strong and not r.veto


def test_different_national_ids_do_not_link():
    a = M("a", name=("Asha", "Verma"), mrn=("AADHAAR111122223333",), hosp="lab")
    b = M("b", name=("Asha", "Verma"), mrn=("AADHAAR444455556666",), hosp="opd")
    assert "mrn" not in evaluate(a, b).strong


def test_same_hospital_number_at_two_sites_needs_agreeing_names():
    same = evaluate(M("a", name=("Asha", "Verma"), mrn=("MRN0042",), hosp="X"), M("b", name=("Asha", "Verma"), mrn=("MRN0042",), hosp="Y"))
    assert "mrn" in same.strong
    other = evaluate(M("a", name=("Asha", "Verma"), mrn=("MRN0042",), hosp="X"), M("b", name=("Ravi", "Kulkarni"), mrn=("MRN0042",), hosp="Y"))
    assert "mrn" not in other.strong
    nameless = evaluate(M("a", name=("Asha", "Verma"), mrn=("MRN0042",), hosp="X"), M("b", mrn=("MRN0042",), hosp="Y"))
    assert "mrn" not in nameless.strong
