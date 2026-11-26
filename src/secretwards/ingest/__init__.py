"""Ingest: one adapter per format. Anything unreadable raises Quarantine(reason) -> the file is
quarantined, never passed through half-processed. Only hashes/ordinals identify files in logs."""
from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path

from ..config import Config
from ..contracts import Document, QReason, QuarantineEntry, SourceFile
from ..security.keys import Keys, hmac_hex


class Quarantine(Exception):
    def __init__(self, reason: QReason):
        super().__init__(reason.value)
        self.reason = reason


SUPPORTED = {".csv", ".tsv", ".txt", ".json", ".jsonl", ".ndjson", ".xlsx"}


def decode_bytes(raw: bytes) -> str:
    if not raw.strip():
        raise Quarantine(QReason.EMPTY)
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8")
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return raw.decode("utf-16")
        except UnicodeError:
            raise Quarantine(QReason.ENCODING)
    if b"\x00" in raw[:8192]:
        raise Quarantine(QReason.ENCODING)
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass
    try:
        text = raw.decode("cp1252")
    except UnicodeDecodeError:
        raise Quarantine(QReason.ENCODING)
    return text


def _doc_id(keys: Keys, rel: str, ordinal: int) -> str:
    return hmac_hex(keys.docid, "doc", rel, str(ordinal), n=16)


def _hospital(keys: Keys, rel: str) -> str:
    parts = rel.split("/")
    comp = parts[0] if len(parts) > 1 else ""
    return "H" + hmac_hex(keys.docid, "hosp", comp, n=4)


def _unique_headers(cells: list[str]) -> list[str]:
    out, seen = [], {}
    for i, c in enumerate(cells):
        h = c.strip() or f"_col{i}"
        if h in seen:
            seen[h] += 1
            h = f"{h}_{seen[h]}"
        else:
            seen[h] = 0
        out.append(h)
    return out


def _table_docs(rows: list[list[str]], keys: Keys, rel: str, hosp: str, source: str, start_ordinal: int) -> tuple[list[Document], dict]:
    """Rows -> Documents. Leading single-cell rows before the header are a preamble (its own document)."""
    docs: list[Document] = []
    non_empty = [r for r in rows if any(c.strip() for c in r)]
    if not non_empty:
        raise Quarantine(QReason.EMPTY)
    h_idx = 0
    widths = [sum(1 for c in r if c.strip()) for r in rows]
    for i, w in enumerate(widths):
        if w >= 2:
            h_idx = i
            break
    else:
        h_idx = next(i for i, r in enumerate(rows) if any(c.strip() for c in r))
    pre = [" ".join(c for c in r if c.strip()) for r in rows[:h_idx] if any(c.strip() for c in r)]
    ordinal = start_ordinal
    if pre:
        docs.append(Document(_doc_id(keys, rel, ordinal), hosp, source, ordinal, "\n".join(pre), {}))
        ordinal += 1
    headers = _unique_headers(rows[h_idx])
    for r in rows[h_idx + 1:]:
        if not any(c.strip() for c in r):
            continue
        fields = {}
        for i, c in enumerate(r):
            fields[headers[i] if i < len(headers) else f"_extra{i}"] = c
        docs.append(Document(_doc_id(keys, rel, ordinal), hosp, source, ordinal, "", fields))
        ordinal += 1
    return docs, {"headers": headers, "preamble": bool(pre)}


def _read_csv(raw: bytes, keys: Keys, rel: str, hosp: str, ext: str) -> tuple[list[Document], dict]:
    text = decode_bytes(raw)
    sample = "\n".join(text.splitlines()[:12])
    if ext == ".tsv":
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
        raise Quarantine(QReason.UNREADABLE)
    docs, layout = _table_docs(rows, keys, rel, hosp, "csv", 0)
    layout["delimiter"] = delim
    return docs, layout


def _flatten(node, path: list, out: list):
    """Collect (path, value, type) for JSON leaves."""
    if isinstance(node, dict):
        for k, v in node.items():
            _flatten(v, path + [str(k)], out)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _flatten(v, path + [i], out)
    elif isinstance(node, bool):
        out.append((path, "true" if node else "false", "bool"))
    elif node is None:
        out.append((path, "", "null"))
    elif isinstance(node, int):
        out.append((path, str(node), "int"))
    elif isinstance(node, float):
        out.append((path, repr(node), "float"))
    else:
        out.append((path, str(node), "str"))


def path_name(path: list) -> str:
    s = ""
    for p in path:
        if isinstance(p, int):
            s += f"[{p}]"
        else:
            s += ("." if s else "") + p
    return s


def _json_docs(records: list, keys: Keys, rel: str, hosp: str, start: int, extra_layout: dict) -> tuple[list[Document], dict]:
    docs = []
    paths: dict[int, dict[str, list]] = {}
    types: dict[int, dict[str, str]] = {}
    for i, rec in enumerate(records):
        leaves: list = []
        _flatten(rec, [], leaves)
        fields, ps, ts = {}, {}, {}
        for path, val, typ in leaves:
            name = path_name(path) or "_value"
            fields[name] = val
            ps[name] = path
            ts[name] = typ
        ordinal = start + i
        docs.append(Document(_doc_id(keys, rel, ordinal), hosp, "json", ordinal, "", fields))
        paths[ordinal] = ps
        types[ordinal] = ts
    return docs, {"paths": paths, "types": types, **extra_layout}


def _read_json(raw: bytes, keys: Keys, rel: str, hosp: str, ext: str) -> tuple[list[Document], dict]:
    text = decode_bytes(raw)
    try:
        if ext in (".jsonl", ".ndjson"):
            data = [json.loads(line) for line in text.splitlines() if line.strip()]
            mode = "jsonl"
        else:
            data = json.loads(text)
            mode = "list"
    except (json.JSONDecodeError, RecursionError):
        raise Quarantine(QReason.UNREADABLE)
    wrapper_key = None
    rest = None
    if mode == "list":
        if isinstance(data, list):
            records = data
        elif isinstance(data, dict):
            lists = [k for k, v in data.items() if isinstance(v, list) and v and all(isinstance(x, dict) for x in v)]
            if len(lists) == 1:
                wrapper_key = lists[0]
                records = data[wrapper_key]
                rest = {k: v for k, v in data.items() if k != wrapper_key}
                mode = "wrapped"
            else:
                records = [data]
                mode = "single"
        else:
            raise Quarantine(QReason.UNREADABLE)
    else:
        records = data
    if not records:
        raise Quarantine(QReason.EMPTY)
    docs, layout = _json_docs(records, keys, rel, hosp, 0, {"mode": mode, "wrapper_key": wrapper_key})
    if rest:
        d2, l2 = _json_docs([rest], keys, rel, hosp, len(docs), {})
        docs.extend(d2)
        layout["paths"].update(l2["paths"])
        layout["types"].update(l2["types"])
        layout["rest_ordinal"] = d2[0].ordinal
    return docs, layout


def _read_txt(raw: bytes, keys: Keys, rel: str, hosp: str) -> tuple[list[Document], dict]:
    text = decode_bytes(raw)
    if not text.strip():
        raise Quarantine(QReason.EMPTY)
    return [Document(_doc_id(keys, rel, 0), hosp, "txt", 0, text, {})], {}


def _read_xlsx(path: Path, raw: bytes, cfg: Config, keys: Keys, rel: str, hosp: str) -> tuple[list[Document], dict]:
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            total = sum(i.file_size for i in z.infolist())
            if total > cfg.max_unzipped_mb * 1024 * 1024:
                raise Quarantine(QReason.SUSPICIOUS_ARCHIVE)
    except zipfile.BadZipFile:
        raise Quarantine(QReason.UNREADABLE)
    try:
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    except Exception:
        raise Quarantine(QReason.UNREADABLE)
    docs: list[Document] = []
    sheets = []
    try:
        for ws in wb.worksheets:
            rows = []
            for r in ws.iter_rows(values_only=True):
                rows.append(["" if v is None else _cell_text(v) for v in r])
            if not any(any(c.strip() for c in r) for r in rows):
                continue
            d, lay = _table_docs(rows, keys, rel, hosp, "xlsx", len(docs))
            docs.extend(d)
            sheets.append({"headers": lay["headers"], "count": len(d), "preamble": lay["preamble"]})
    except Quarantine:
        raise
    except Exception:
        raise Quarantine(QReason.UNREADABLE)
    if not docs:
        raise Quarantine(QReason.EMPTY)
    return docs, {"sheets": sheets}


def _cell_text(v) -> str:
    import datetime as dt

    if isinstance(v, dt.datetime):
        return v.date().isoformat() if v.time() == dt.time(0) else v.isoformat(sep=" ")
    if isinstance(v, dt.date):
        return v.isoformat()
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def read_file(path: Path, rel: str, ordinal: int, cfg: Config, keys: Keys) -> SourceFile:
    ext = Path(rel).suffix.lower()
    if ext not in SUPPORTED:
        raise Quarantine(QReason.UNSUPPORTED_FORMAT)
    size = path.stat().st_size
    if size == 0:
        raise Quarantine(QReason.EMPTY)
    if size > cfg.max_file_mb * 1024 * 1024:
        raise Quarantine(QReason.TOO_LARGE)
    raw = path.read_bytes()
    hosp = _hospital(keys, rel)
    if ext in (".csv", ".tsv"):
        docs, layout = _read_csv(raw, keys, rel, hosp, ext)
        kind = "csv"
    elif ext in (".json", ".jsonl", ".ndjson"):
        docs, layout = _read_json(raw, keys, rel, hosp, ext)
        kind = "json"
    elif ext == ".txt":
        docs, layout = _read_txt(raw, keys, rel, hosp)
        kind = "txt"
    else:
        docs, layout = _read_xlsx(path, raw, cfg, keys, rel, hosp)
        kind = "xlsx"
    return SourceFile(ref=hmac_hex(keys.docid, "file", rel, n=12), ordinal=ordinal, kind=kind, docs=docs, layout=layout)


def ingest_dir(in_dir: Path, cfg: Config, keys: Keys) -> tuple[list[SourceFile], list[QuarantineEntry]]:
    files, quarantined = [], []
    paths = sorted((p for p in in_dir.rglob("*") if p.is_file()), key=lambda p: p.relative_to(in_dir).as_posix())
    for ordinal, p in enumerate(paths):
        rel = p.relative_to(in_dir).as_posix()
        try:
            files.append(read_file(p, rel, ordinal, cfg, keys))
        except Quarantine as q:
            quarantined.append(QuarantineEntry(hmac_hex(keys.docid, "file", rel, n=12), q.reason, "file"))
        except Exception:  # any surprise: fail closed
            quarantined.append(QuarantineEntry(hmac_hex(keys.docid, "file", rel, n=12), QReason.INTERNAL_ERROR, "file"))
    return files, quarantined
