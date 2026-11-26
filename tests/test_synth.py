import csv
import io
import json
import re
from pathlib import Path

import pytest

from synth.generate import generate


def _load_cells(path: Path):
    """Return list of {field: text} per record, mirroring gold indexing."""
    suf = path.suffix
    if suf == ".txt":
        return [{None: path.read_text(encoding="utf-8")}]
    if suf == ".csv":
        raw = path.read_bytes().decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(raw)))
        # preamble: first row shorter than the 2nd
        out = []
        if len(rows) > 1 and len(rows[0]) == 1 and len(rows[1]) > 2:
            out.append({None: rows[0][0]})
            rows = rows[1:]
        hdr = rows[0]
        for r in rows[1:]:
            out.append({(hdr[i] if i < len(hdr) else f"_extra{i}"): v for i, v in enumerate(r)})
        return out
    if suf == ".json":
        doc = json.loads(path.read_text(encoding="utf-8"))
        recs = doc if isinstance(doc, list) else doc["records"]
        out = []
        for r in recs:
            flat = {}

            def walk(n, p):
                if isinstance(n, dict):
                    for k, v in n.items():
                        walk(v, f"{p}.{k}" if p else k)
                elif isinstance(n, list):
                    for i, v in enumerate(n):
                        walk(v, f"{p}[{i}]")
                elif n is not None:
                    flat[p] = str(n)

            walk(r, "")
            out.append(flat)
        return out
    if suf == ".xlsx":
        import openpyxl

        wb = openpyxl.load_workbook(path)
        rows = list(wb.active.iter_rows(values_only=True))
        hdr = [str(h) for h in rows[0] if h is not None]
        return [{(hdr[i] if i < len(hdr) else f"_extra{i}"): ("" if v is None else str(v)) for i, v in enumerate(r)} for r in rows[1:]]
    raise ValueError(suf)


@pytest.fixture(scope="module")
def dataset(tmp_path_factory):
    out = {}
    for split in ("dev", "heldout"):
        root = generate(tmp_path_factory.mktemp("s"), split, seed=3, n_patients=60)
        out[split] = (root, json.loads((root / "gold.json").read_text(encoding="utf-8")))
    return out


@pytest.mark.parametrize("split", ["dev", "heldout"])
def test_gold_spans_match_files(dataset, split):
    root, gold = dataset[split]
    cache = {}
    checked = 0
    for rec in gold["records"]:
        if rec["file"] in gold["quarantine_expected"]:
            continue
        cells = cache.setdefault(rec["file"], _load_cells(root / "in" / rec["file"]))
        cell = cells[rec["index"]]
        for kind in ("pii", "med"):
            for s in rec[kind]:
                assert cell[s["field"]][s["start"]:s["end"]] == s["text"]
                checked += 1
    assert checked > 500


def test_generator_is_deterministic(tmp_path):
    a = generate(tmp_path / "a", "dev", seed=5, n_patients=25)
    b = generate(tmp_path / "b", "dev", seed=5, n_patients=25)
    assert (a / "gold.json").read_bytes() == (b / "gold.json").read_bytes()
    fa = sorted(p.relative_to(a / "in") for p in (a / "in").rglob("*") if p.is_file())
    fb = sorted(p.relative_to(b / "in") for p in (b / "in").rglob("*") if p.is_file())
    assert fa == fb
    for f in fa:
        if f.suffix != ".xlsx":  # xlsx embeds a creation timestamp
            assert (a / "in" / f).read_bytes() == (b / "in" / f).read_bytes()


def test_heldout_names_are_disjoint_from_dev(dataset):
    from synth import pools as P

    dev = {n[0] for n in P.FIRST_M_SEEN + P.FIRST_F_SEEN + P.LAST_SEEN}
    held = {n[0] for n in P.FIRST_M_HELD + P.FIRST_F_HELD + P.LAST_HELD}
    assert not (dev & held)


def test_there_are_same_name_different_patient_pairs(dataset):
    _, gold = dataset["dev"]
    assert any(v["twin_of"] for v in gold["patients"].values())


def _all_test_names():
    from synth import blind as B
    from synth import pools as P

    held = P.FIRST_M_HELD + P.FIRST_F_HELD + P.LAST_HELD
    blind = B.FIRST_M + B.FIRST_F + B.LAST
    canary = [(n, "") for n in P.CANARY_FIRST + P.CANARY_LAST]
    return held, blind, canary


def test_gazetteer_contains_no_heldout_blind_or_canary_name():
    from secretwards.detect import lexicon as L
    from secretwards.normalize.translit import skeleton

    gaz = L.first_names() | L.surnames()
    for names in _all_test_names():
        assert not [n for n, _ in names if n.lower() in gaz]
    # phonetic collisions are allowed (spelling variants of real gazetteer names) but must stay rare
    gk = {skeleton(n) for n in gaz if len(skeleton(n)) >= 3}
    for names in _all_test_names():
        coll = [n for n, _ in names if len(skeleton(n)) >= 3 and skeleton(n) in gk]
        assert len(coll) <= 0.15 * len(names), coll


def test_held_cities_are_not_in_the_city_gazetteer():
    from secretwards.detect import lexicon as L
    from synth import blind as B
    from synth import pools as P

    assert not [c for c, _ in P.CITIES_HELD + B.CITIES if c.lower() in L.cities()]


def test_blind_split_generates_and_gold_matches_files(tmp_path):
    root = generate(tmp_path, "blind", seed=2, n_patients=40)
    gold = json.loads((root / "gold.json").read_text(encoding="utf-8"))
    cache, checked = {}, 0
    for rec in gold["records"]:
        if rec["file"] in gold["quarantine_expected"]:
            continue
        cells = cache.setdefault(rec["file"], _load_cells(root / "in" / rec["file"]))
        cell = cells[rec["index"]]
        for kind in ("pii", "med"):
            for s in rec[kind]:
                assert cell[s["field"]][s["start"]:s["end"]] == s["text"]
                checked += 1
    assert checked > 300
