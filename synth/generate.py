"""Synthetic hospital dump generator with gold PII spans, patient ids and medical values.

dev      patients/templates/schemas we may look at while building detectors
heldout  different name pools, templates and column schemas; used only for reporting

Layout written:  <out>/<split>/in/<hospital>/...   (pipeline input)
                 <out>/<split>/gold.json            (never given to the pipeline)
"""
from __future__ import annotations

import csv
import io
import json
import random
from pathlib import Path

import openpyxl

from . import pools as P
from .cell import Cell
from .people import HOSPITALS, Encounter, Person, make_encounters, make_people, fmt_phone
from . import templates as T


class Gold:
    def __init__(self) -> None:
        self.records: list[dict] = []
        self.canaries: list[dict] = []
        self.quarantine_expected: list[str] = []
        self.files: list[str] = []

    def add_record(self, file: str, index: int, pid: str | None, cells: dict[str | None, Cell], hospital: str) -> None:
        pii, med = [], []
        for fname, c in cells.items():
            for x in c.pii:
                pii.append({"field": fname, **x})
            for x in c.med:
                med.append({"field": fname, **x})
        self.records.append({"file": file, "index": index, "patient": pid, "hospital": hospital, "pii": pii, "med": med})


def _canary_person(rng: random.Random) -> dict:
    f, l = rng.choice(P.CANARY_FIRST), rng.choice(P.CANARY_LAST)
    num = str(rng.choice([7, 8, 9])) + "".join(str(rng.randrange(10)) for _ in range(9))
    return {"name": f"{f} {l}", "phone": num, "email": f"{f.lower()}.{l.lower()}{rng.randrange(10, 99)}@mailbox.in"}


def _row_cells(schema, p: Person, enc: Encounter, rng: random.Random, noise: float, dstyle: int) -> list[Cell]:
    kind, lang, cols = schema
    cells = []
    for header, logical in cols:
        c = T.cell_for(logical, p, enc, rng, lang, noise, dstyle if rng.random() > 0.1 else rng.randrange(9))
        if logical not in ("mrn", "name", "name_rel", "phone", "phones") and rng.random() < 0.06:
            c = Cell(rng)  # missing value
        cells.append(c)
    return cells


def _shift(cells: list[Cell], rng: random.Random) -> list[Cell]:
    """Simulate an Excel export with a shifted column from a random position on."""
    pos = rng.randrange(1, max(2, len(cells) - 1))
    if rng.random() < 0.5:
        return cells[:pos] + [Cell(rng)] + cells[pos:]
    return cells[:pos] + cells[pos + 1:]


def _col_name(headers: list[str], i: int) -> str:
    return headers[i] if i < len(headers) else f"_extra{i}"


def _walk_json(node, path: str, out: dict):
    """Cell tree -> plain JSON object, collecting {path: Cell}."""
    if isinstance(node, Cell):
        out[path] = node
        if not node.text:
            return None
        if isinstance(node.native, int) and node.text == str(node.native):
            return node.native
        return node.text
    if isinstance(node, dict):
        return {k: _walk_json(v, f"{path}.{k}" if path else k, out) for k, v in node.items()}
    if isinstance(node, list):
        return [_walk_json(v, f"{path}[{i}]", out) for i, v in enumerate(node)]
    return node


from . import blind as B  # noqa: E402


def generate(out_root: str | Path, split: str = "dev", seed: int = 1, n_patients: int = 300) -> Path:
    assert split in ("dev", "heldout", "blind")
    rng = random.Random(f"synth:{split}:{seed}")
    root = Path(out_root) / split
    inp = root / "in"
    if inp.exists():
        import shutil
        shutil.rmtree(inp)
    inp.mkdir(parents=True)
    people = make_people(rng, n_patients, split)
    encs = make_encounters(rng, people, split)
    txt_only = {p.pid for p in people if rng.random() < 0.25}  # appear in free text only, never in a table
    if split == "blind":
        from . import blind as B

        schemas, txts, txt_map = B.BLIND_SCHEMAS, B.BLIND_TXT, B.BLIND_TXT_BY_HOSP
    else:
        schemas = T.SEEN_SCHEMAS if split == "dev" else T.HELD_SCHEMAS
        txts = T.SEEN_TXT if split == "dev" else T.HELD_TXT
        txt_map = T.TXT_BY_HOSP["seen" if split == "dev" else "held"]
    gold = Gold()
    cn_i = 0

    def canary(kind: str, where: str):
        nonlocal cn_i
        cp = _canary_person(rng)
        cn_i += 1
        return cp

    def noise_rate() -> float:
        return rng.choice([0.0, 0.0, 0.0, 0.012, 0.025])

    by_h: dict[str, list[Encounter]] = {h: [] for h in HOSPITALS}
    for e in encs:
        if e.person.pid not in txt_only:
            by_h[e.hospital].append(e)

    file_no = 0
    for h in HOSPITALS:
        hd = inp / h
        hd.mkdir(exist_ok=True)
        kind, lang, cols = schemas[h]
        es = sorted(by_h[h], key=lambda e: (e.admit, e.person.pid))
        chunks = [es[: len(es) // 2], es[len(es) // 2:]] if len(es) > 8 else [es]
        for ci, chunk in enumerate(chunks):
            if not chunk:
                continue
            file_no += 1
            dstyle = rng.choice([0, 1, 3, 4])
            if kind in ("csv", "xlsx"):
                headers = [c[0] for c in cols]
                extra_header = None
                preamble = None
                if kind == "csv" and ci == 0 and h == "hosp_e":
                    cp = canary("hdr", "csv header")
                    extra_header = f"Referred by Dr. {cp['name']}"
                    gold.canaries.append({"type": "NAME", "text": cp["name"], "where": "csv_header"})
                if kind == "csv" and ci == 1 and h in ("hosp_a", "hosp_d"):
                    cp = canary("pre", "csv preamble")
                    preamble = f"Exported by {cp['name']} on {cp['phone']}"
                    gold.canaries.append({"type": "NAME", "text": cp["name"], "where": "csv_preamble"})
                    gold.canaries.append({"type": "PHONE", "text": cp["phone"], "where": "csv_preamble"})
                hdrs = headers + ([extra_header] if extra_header else [])
                rows: list[list[Cell]] = []
                for e in chunk:
                    cells = _row_cells(schemas[h], e.person, e, rng, noise_rate(), dstyle)
                    if extra_header:
                        cells.append(Cell(rng))
                    if rng.random() < 0.07:
                        cells = _shift(cells, rng)
                    rows.append(cells)
                rel = f"{h}/registry_{ci + 1}.{kind}"
                path = inp / rel
                offs = 0
                if kind == "csv":
                    buf = io.StringIO()
                    w = csv.writer(buf, lineterminator="\n")
                    if preamble:
                        buf.write(preamble + "\n")
                        offs = 1
                        gold.add_record(rel, 0, None, {None: _lit_cell(preamble, rng, [("NAME", cp["name"]), ("PHONE", cp["phone"])])}, h)
                    w.writerow(hdrs)
                    for cells in rows:
                        w.writerow([c.text for c in cells])
                    enc_ = "utf-8-sig" if h == "hosp_d" else "utf-8"
                    path.write_bytes(buf.getvalue().encode(enc_))
                else:
                    wb = openpyxl.Workbook()
                    ws = wb.active
                    sheet = "Sheet1"
                    if ci == 1 and h == "hosp_b":
                        cp = canary("sheet", "xlsx sheet")
                        sheet = cp["name"][:31]
                        gold.canaries.append({"type": "NAME", "text": cp["name"], "where": "sheet_name"})
                    ws.title = sheet
                    ws.append(hdrs)
                    for cells in rows:
                        ws.append([c.text for c in cells])
                    wb.save(path)
                for ri, (e, cells) in enumerate(zip(chunk, rows)):
                    fm = {_col_name(hdrs, i): c for i, c in enumerate(cells)}
                    gold.add_record(rel, ri + offs, e.person.pid, fm, h)
                gold.files.append(rel)
            else:  # json
                rel = f"{h}/export_{ci + 1}.json"
                recs, golds = [], []
                canary_key = None
                for ri, e in enumerate(chunk):
                    tree = (B.blind_json_record(e.person, e, rng, noise_rate(), dstyle) if split == "blind"
                            else T.json_record(split, e.person, e, rng, noise_rate(), dstyle))
                    if ci == 1 and ri == 0:
                        cp = canary("key", "json key")
                        canary_key = f"alt_contact_{cp['phone']}"
                        tree[canary_key] = Cell(rng).lit("n/a")
                        gold.canaries.append({"type": "PHONE", "text": cp["phone"], "where": "json_key"})
                    cells: dict[str, Cell] = {}
                    obj = _walk_json(tree, "", cells)
                    recs.append(obj)
                    golds.append((e, cells))
                doc = recs if ci == 0 else {"exported_by": "system", "records": recs}
                (inp / rel).write_bytes(json.dumps(doc, ensure_ascii=ci == 0, indent=1).encode("utf-8"))
                for ri, (e, cells) in enumerate(golds):
                    gold.add_record(rel, ri, e.person.pid, cells, h)
                gold.files.append(rel)

    # free-text documents
    nt = 0
    for e in encs:
        if e.person.pid not in txt_only and rng.random() > 0.55:
            continue
        tpl = txts[rng.choice(txt_map[e.hospital])]
        c = tpl(e.person, e, rng, noise_rate())
        nt += 1
        rel = f"{e.hospital}/notes/doc_{nt:05d}.txt"
        (inp / e.hospital / "notes").mkdir(exist_ok=True)
        (inp / rel).write_bytes(c.text.encode("utf-8"))
        gold.add_record(rel, 0, e.person.pid, {None: c}, e.hospital)
        gold.files.append(rel)

    # canary-bearing text files (filename + unlabeled footer)
    for k in range(4):
        e = rng.choice(encs)
        cp = canary("fn", "filename")
        c = txts[rng.choice(txt_map[e.hospital])](e.person, e, rng, 0.0)
        foot = Cell(rng)
        foot.lit("\nBilling contact: ").P("NAME", cp["name"], "other").lit(", ").P("PHONE", cp["phone"]).lit(", ").P("EMAIL", cp["email"]).lit("\n")
        full = Cell(rng)
        full.lit(c.text, noisy=False)
        full.pii = list(c.pii)
        full.med = list(c.med)
        full._n = len(c.text)
        shift = len(c.text)
        full.lit(foot.text, noisy=False)
        for x in foot.pii:
            full.pii.append({**x, "start": x["start"] + shift, "end": x["end"] + shift})
        fn = f"letter_{cp['name'].replace(' ', '_')}.txt"
        rel = f"{e.hospital}/notes/{fn}"
        (inp / rel).write_bytes(full.text.encode("utf-8"))
        gold.add_record(rel, 0, e.person.pid, {None: full}, e.hospital)
        gold.files.append(rel)
        for t, v in (("NAME", cp["name"]), ("PHONE", cp["phone"]), ("EMAIL", cp["email"])):
            gold.canaries.append({"type": t, "text": v, "where": "txt_footer"})
        gold.canaries.append({"type": "NAME", "text": cp["name"], "where": "filename"})

    # files that must be quarantined
    junk = {
        "hosp_a/scan_0001.pdf": b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<>>\nendobj\n",
        "hosp_b/broken.xlsx": bytes(rng.randrange(256) for _ in range(600)),
        "hosp_c/truncated.json": b'[{"patient_id": "REG-1", "patient": {"name": "Trunc',
        "hosp_d/binary.csv": b"\x00\x01\x02\xff\xfe\x00\x00" + bytes(rng.randrange(256) for _ in range(400)),
        "hosp_e/empty.txt": b"",
        "hosp_a/archive.zip": b"PK\x03\x04" + bytes(rng.randrange(256) for _ in range(200)),
    }
    for rel, data in junk.items():
        (inp / rel).write_bytes(data)
        gold.quarantine_expected.append(rel)
        gold.files.append(rel)

    pat = {}
    for p in people:
        pat[p.pid] = {"twin_of": p.twin_of}
    out = {
        "version": 1, "split": split, "seed": seed, "records": gold.records, "canaries": gold.canaries,
        "quarantine_expected": gold.quarantine_expected, "files": sorted(gold.files), "patients": pat,
    }
    (root / "gold.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return root


def _lit_cell(text: str, rng: random.Random, pii: list[tuple[str, str]]) -> Cell:
    c = Cell(rng)
    c._parts = [text]
    c._n = len(text)
    for t, v in pii:
        i = text.find(v)
        c.pii.append({"start": i, "end": i + len(v), "type": t, "text": v, "role": "other"})
    return c
