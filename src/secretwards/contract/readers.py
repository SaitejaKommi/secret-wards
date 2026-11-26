"""Contract readers: parse one input file into addressable records (rows, JSON pointers, whole documents).

Locator rules (docs/toolkit/docs/SPEC.md, confirmed against the practice answer key's shapes):
  CSV / TSV   row:N      N = 0-based data row, header excluded
  JSON        /key/N     for every top-level key whose value is a non-empty list of objects (dict top level,
                         not a FHIR Bundle); everything else in the file is a file-level 'metadata' record (loc None)
  other JSON  doc        a top-level list, a single object, a FHIR Bundle: the whole file is one record
  TXT         doc
Anything that cannot be parsed safely raises Skip(reason): the whole file is quarantined (a reason code, never content).
"""
from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from ..contracts import Document, QReason
from ..ingest import Quarantine, _flatten, _unique_headers, decode_bytes, path_name
from ..security.keys import Keys, hmac_hex

KIND_BY_EXT = {".csv": "csv", ".tsv": "tsv", ".json": "json", ".txt": "txt"}


class Skip(Exception):
    """The file cannot be sanitized safely: quarantine it. `reason` is a short code."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass
class Rec:
    loc: str | None  # None = file-level metadata (sanitized, but not listed in records.jsonl)
    doc: Document
    names: list[str] = field(default_factory=list)  # csv: column names in order
    paths: dict[str, tuple] = field(default_factory=dict)  # json: leaf name -> path tuple
    types: dict[str, str] = field(default_factory=dict)  # json: leaf name -> str|int|float|bool|null


@dataclass
class Parsed:
    rel: str
    kind: str
    recs: list[Rec]
    layout: dict = field(default_factory=dict)


def _doc_id(keys: Keys, rel: str, loc: str | None) -> str:
    return hmac_hex(keys.docid, "doc", rel, loc or "@file", n=16)


def _hospital(keys: Keys, rel: str) -> str:
    parts = rel.split("/")
    return "H" + hmac_hex(keys.docid, "hosp", parts[0] if len(parts) > 1 else "", n=4)


def decode_text(raw: bytes) -> str:
    try:
        return decode_bytes(raw)
    except Quarantine as q:
        raise Skip("empty_file" if q.reason == QReason.EMPTY else "undecodable_text")
    except UnicodeError:
        raise Skip("undecodable_text")


def _escape(key: str) -> str:
    return key.replace("~", "~0").replace("/", "~1")


# ------------------------------------------------------------------ csv / tsv
def _read_table(rel: str, text: str, kind: str, keys: Keys) -> Parsed:
    head = text.lstrip()[:1]
    if head in ("{", "["):
        try:
            json.loads(text)
        except (ValueError, RecursionError):
            pass
        else:
            raise Skip("content_mismatch")  # JSON behind a .csv/.tsv extension: not a table
    sample = "\n".join(text.splitlines()[:12])
    if kind == "tsv":
        delim = "\t"
    else:
        counts = {d: sample.count(d) for d in (",", "\t", ";", "|")}
        delim = max(counts, key=lambda d: counts[d])
        if counts[delim] == 0:
            delim = ","
    csv.field_size_limit(50_000_000)
    try:
        rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=delim))
    except csv.Error:
        raise Skip("parse_error")
    if not rows:
        raise Skip("empty_file")
    header = rows[0]
    base = _unique_headers(header)
    hosp = _hospital(keys, rel)
    recs: list[Rec] = []
    for i, row in enumerate(rows[1:]):
        cols = (base + [f"_extra{j}" for j in range(len(base), len(row))])[: len(row)]
        fields = {c: v for c, v in zip(cols, row)}
        loc = f"row:{i}"
        recs.append(Rec(loc, Document(_doc_id(keys, rel, loc), hosp, "csv", i, "", fields), cols))
    return Parsed(rel, kind, recs, {"delimiter": delim, "header": header, "base_names": base})


# ------------------------------------------------------------------ json
def _make_rec(keys: Keys, rel: str, loc: str | None, ordinal: int, leaves: list) -> Rec:
    fields, paths, types = {}, {}, {}
    for path, val, typ in leaves:
        name = path_name(path) or "_value"
        while name in fields:
            name += "#"
        fields[name] = val
        paths[name] = tuple(path)
        types[name] = typ
    doc = Document(_doc_id(keys, rel, loc), _hospital(keys, rel), "json", ordinal, "", fields)
    return Rec(loc, doc, list(fields), paths, types)


# A top-level entity that names the patient means the whole file is ONE patient's document (e.g. a lab report with
# a "patient" object and a list of panels), not a list of patient records.
_SINGLE_ENTITY = re.compile(r"(?i)patient|person|subject|member|beneficiar|^name$")


def _read_json(rel: str, text: str, keys: Keys, probe: Optional[Callable[[list], bool]] = None) -> Parsed:
    try:
        data = json.loads(text)
    except (ValueError, RecursionError):
        raise Skip("malformed_json")
    list_keys: list[str] = []
    if isinstance(data, dict) and data.get("resourceType") != "Bundle":
        list_keys = [k for k, v in data.items() if isinstance(v, list) and v and all(isinstance(x, dict) for x in v)]
        if list_keys and any(_SINGLE_ENTITY.search(k) and isinstance(v, (dict, str)) for k, v in data.items()):
            list_keys = []
        # the list items must themselves carry personal data to count as patient records
        if list_keys and probe is not None:
            list_keys = [k for k in list_keys if probe(data[k][:3])]
    recs: list[Rec] = []
    try:
        if not list_keys:
            leaves: list = []
            _flatten(data, [], leaves)
            recs.append(_make_rec(keys, rel, "doc", 0, leaves))
        else:
            n = 0
            for k in list_keys:
                for i, item in enumerate(data[k]):
                    leaves = []
                    _flatten(item, [k, i], leaves)
                    recs.append(_make_rec(keys, rel, f"/{_escape(k)}/{i}", n, leaves))
                    n += 1
            meta: list = []
            for k, v in data.items():
                if k not in list_keys:
                    _flatten(v, [k], meta)
            if meta:
                recs.append(_make_rec(keys, rel, None, n, meta))
    except RecursionError:
        raise Skip("too_deep")
    return Parsed(rel, "json", recs, {"data": data})


# ------------------------------------------------------------------ txt
def _read_txt(rel: str, text: str, keys: Keys) -> Parsed:
    if not text.strip():
        raise Skip("empty_file")
    doc = Document(_doc_id(keys, rel, "doc"), _hospital(keys, rel), "txt", 0, text, {})
    return Parsed(rel, "txt", [Rec("doc", doc)])


def read_file(rel: str, raw: bytes, keys: Keys, max_bytes: int, probe: Optional[Callable[[list], bool]] = None) -> Parsed:
    kind = KIND_BY_EXT.get(Path(rel).suffix.lower())
    if kind is None:
        raise Skip("unsupported_format")
    if not raw.strip():
        raise Skip("empty_file")
    if len(raw) > max_bytes:
        raise Skip("too_large")
    text = decode_text(raw)
    if kind in ("csv", "tsv"):
        return _read_table(rel, text, kind, keys)
    if kind == "json":
        return _read_json(rel, text, keys, probe)
    return _read_txt(rel, text, keys)
