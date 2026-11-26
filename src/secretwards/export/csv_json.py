"""CSV / JSON / TXT writers. Header names, JSON keys and sheet names can carry PII, so they are
kept only if every word is in a known header vocabulary; otherwise they are replaced by a keyed hash."""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Sequence

import regex as re

from ..contracts import RedactedRecord, SourceFile
from ..detect.lexicon import HEADER_WORDS
from ..security.keys import Keys, hmac_hex

_SPLIT = re.compile(r"[^\p{L}\p{M}\d]+|(?<=[a-z])(?=[A-Z])")


class Namer:
    def __init__(self, keys: Keys):
        self.keys = keys

    def name(self, raw: str, kind: str = "col") -> str:
        if re.fullmatch(r"(?:col|key)_[0-9a-f]{6}|_?(?:extra|col)\d+", raw):
            return raw  # already sanitized / generated
        words = [w for w in _SPLIT.split(raw) if w]
        if words and len(raw) <= 60 and all(w.lower() in HEADER_WORDS or w.isdigit() and len(w) <= 2 for w in words):
            return raw
        return f"{kind}_{hmac_hex(self.keys.docid, 'name', raw, n=6)}"


def _csv_bytes(headers: list[str], rows: list[list[str]], delim: str = ",") -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=delim, lineterminator="\n")
    w.writerow(headers)
    w.writerows(rows)
    return buf.getvalue().encode("utf-8")


def _set_path(root, path: list, value):
    cur = root
    for i, p in enumerate(path):
        last = i == len(path) - 1
        nxt = None if last else path[i + 1]
        if isinstance(p, int):
            while len(cur) <= p:
                cur.append(None)
            if last:
                cur[p] = value
            else:
                if cur[p] is None:
                    cur[p] = [] if isinstance(nxt, int) else {}
                cur = cur[p]
        else:
            if last:
                cur[p] = value
            else:
                if p not in cur:
                    cur[p] = [] if isinstance(nxt, int) else {}
                cur = cur[p]


def _coerce(value: str, typ: str):
    if typ == "int" and value.lstrip("-").isdigit():
        return int(value)
    if typ == "float":
        try:
            return float(value)
        except ValueError:
            return value
    if typ == "bool" and value in ("true", "false"):
        return value == "true"
    if typ == "null" and value == "":
        return None
    return value


def _json_obj(rec: RedactedRecord, types: dict, namer: Namer, pseud: bool = True):
    root: dict | list = {}
    for field, value in rec.fields.items():
        path = rec.paths.get(field)
        if not path:
            continue
        safe = [p if isinstance(p, int) else namer.name(p, "key") for p in path]
        if not safe:
            return _coerce(value, types.get(field, "str"))
        if isinstance(safe[0], int) and isinstance(root, dict) and not root:
            root = []
        _set_path(root, safe, _coerce(value, types.get(field, "str")))
    if pseud and isinstance(root, dict):
        root = {"pseudonym": rec.pseudonym, **root}
    return root


def write_source(out_dir: Path, sf: SourceFile, recs: Sequence[RedactedRecord], namer: Namer) -> list[tuple[str, int]]:
    """Write de-identified output for one input file. Returns [(relative output name, record count)]."""
    stem = f"f{sf.ordinal:04d}"
    outs: list[tuple[str, int]] = []
    if sf.kind == "csv":
        hdrs = [namer.name(h) for h in sf.layout["headers"]]
        return _write_table(out_dir, stem, hdrs, sf, recs, sf.layout.get("delimiter", ","))
    if sf.kind == "xlsx":
        # one CSV per sheet, in document order
        i0 = 0
        for si, sh in enumerate(sf.layout["sheets"]):
            part = [r for r in recs if r.ordinal >= i0 and r.ordinal < i0 + sh["count"]]
            hdrs = [namer.name(h) for h in sh["headers"]]
            outs += _write_table(out_dir, f"{stem}_s{si + 1}", hdrs, sf, part, ",")
            i0 += sh["count"]
        return outs
    if sf.kind == "txt":
        r = recs[0] if recs else None
        if r is None:
            return []
        (out_dir / f"{stem}.txt").write_text(f"# pseudonym: {r.pseudonym}\n" + r.text, encoding="utf-8", newline="\n")
        return [(f"{stem}.txt", 1)]
    # json
    lay = sf.layout
    objs = {}
    for r in recs:
        objs[r.ordinal] = _json_obj(r, lay["types"].get(r.ordinal, {}), namer)
    rest = None
    if "rest_ordinal" in lay and lay["rest_ordinal"] in objs:
        rest = objs.pop(lay["rest_ordinal"])
        if isinstance(rest, dict):
            rest.pop("pseudonym", None)
    items = [objs[k] for k in sorted(objs)]
    mode = lay["mode"]
    if mode == "jsonl":
        data = "\n".join(json.dumps(o, ensure_ascii=False) for o in items) + "\n"
        name = f"{stem}.jsonl"
    else:
        if mode == "wrapped":
            doc = {namer.name(lay["wrapper_key"], "key"): items}
            if isinstance(rest, dict):
                doc = {**rest, **doc}
        elif mode == "single":
            doc = items[0] if items else {}
        else:
            doc = items
        data = json.dumps(doc, ensure_ascii=False, indent=1)
        name = f"{stem}.json"
    (out_dir / name).write_text(data, encoding="utf-8", newline="\n")
    return [(name, len(items))]


def _write_table(out_dir: Path, stem: str, headers: list[str], sf: SourceFile, recs: Sequence[RedactedRecord], delim: str):
    rows = []
    width = len(headers)
    pre = [r for r in recs if r.text and not r.fields]
    body = [r for r in recs if r.fields]
    for r in body:
        cells = list(r.fields.values())
        width = max(width, len(cells))
    hdr = ["pseudonym"] + headers + [f"extra{i}" for i in range(len(headers), width)]
    for r in body:
        vals = list(r.fields.values())
        rows.append([r.pseudonym] + vals + [""] * (width - len(vals)))
    # a preamble (title rows above the header) is written as one row of text in the first data column
    for r in pre:
        rows.insert(0, [r.pseudonym, r.text] + [""] * (width - 1))
    name = f"{stem}.csv"
    (out_dir / name).write_bytes(_csv_bytes(hdr, rows, ","))
    return [(name, len(recs))]
