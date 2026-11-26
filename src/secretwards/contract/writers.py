"""Contract writers: rebuild each file in its ORIGINAL format from redacted records.

Same delimiter / header / row count / row lengths for tables, same key order / structure / value types for JSON,
same text for TXT. Everything is written as UTF-8. Never adds a column or a key, never drops a row.
"""
from __future__ import annotations

import csv
import io
import json
from typing import Callable

from ..contracts import RedactedRecord
from ..security.keys import Keys, hmac_hex
from .readers import Parsed


def write_csv(p: Parsed, red: dict[str, RedactedRecord], rename: Callable[[str], str]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=p.layout["delimiter"], lineterminator="\n")
    w.writerow([rename(h) for h in p.layout["header"]])
    for rec in p.recs:
        r = red[rec.doc.doc_id]
        w.writerow([r.fields.get(c, rec.doc.fields[c]) for c in rec.names])
    return buf.getvalue().encode("utf-8")


def surrogate_number(keys: Keys, original: str, length: int) -> int:
    """Keyed stand-in for a numeric PII value (phone, Aadhaar stored as a JSON number): same digit count, so the
    JSON value type is unchanged, but not the real number."""
    h = int(hmac_hex(keys.docid, "num", original, n=32), 16)
    digits = str(h).rjust(length, "7")[:length]
    return int(("1" if digits[0] == "0" else digits[0]) + digits[1:])


def write_json(p: Parsed, red: dict[str, RedactedRecord], rename_key: Callable[[str], str], keys: Keys) -> bytes:
    leaf: dict[tuple, str] = {}
    for rec in p.recs:
        r = red[rec.doc.doc_id]
        for name, path in rec.paths.items():
            new = r.fields.get(name)
            if new is not None and new != rec.doc.fields[name]:
                leaf[path] = new

    def coerce(orig, new: str):
        if isinstance(orig, bool) or orig is None:
            return orig
        if isinstance(orig, int):
            if new.lstrip("-").isdigit():
                return int(new)
            return surrogate_number(keys, str(orig), len(str(abs(orig))))
        if isinstance(orig, float):
            try:
                return float(new)
            except ValueError:
                return float(surrogate_number(keys, repr(orig), 6))
        return new

    def rebuild(node, path: tuple):
        if isinstance(node, dict):
            return {rename_key(k): rebuild(v, path + (k,)) for k, v in node.items()}
        if isinstance(node, list):
            return [rebuild(v, path + (i,)) for i, v in enumerate(node)]
        new = leaf.get(path)
        return node if new is None else coerce(node, new)

    out = rebuild(p.layout["data"], ())
    return (json.dumps(out, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def write_txt(p: Parsed, red: dict[str, RedactedRecord]) -> bytes:
    return red[p.recs[0].doc.doc_id].text.encode("utf-8")
