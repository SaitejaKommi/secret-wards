"""The organisers' output contract (docs/toolkit/docs/SPEC.md) on top of our existing stages.

  python main.py --input {input} --output {output}      with RAKSHA_SECRET in the environment

Writes {output}/sanitized/ (same relative paths and formats, except names that hold PII), report.json (written LAST),
records.jsonl. Exit 0 only when the release is complete; any per-file problem quarantines THAT file (reason code only),
a fatal problem removes partial output and exits non-zero. Only counts go to stdout; nothing personal, and never the secret.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
import time
from collections import Counter
from pathlib import Path

from ..config import Config
from ..contracts import PIIType, RedactedRecord
from ..detect import default_detectors
from ..detect.hidden import clean_encoded
from ..detect.learned import NameMemory
from ..detect.merge import UUID_LIKE
from ..link import link_documents
from ..link.mention import build_mention
from ..normalize.text import normalize, ocr_digit_view
from ..pipeline import make_unit, process_doc
from ..detect import detect_unit
from ..privacy.generalize import age_text, extract_facts, overrides, pin_text, plan_levels
from ..privacy.pseudonym import shift_days
from ..privacy.render import redact
from ..security.keys import hmac_hex
from ..security.keys import KeysMissing, keys_from_secret
from ..security.leak_gate import gate
from .readers import Parsed, Skip, read_file
from .renamer import Renamer
from .writers import write_csv, write_json, write_txt

ENTITY_LABEL = {
    PIIType.NAME: "NAME", PIIType.PHONE: "PHONE", PIIType.EMAIL: "EMAIL", PIIType.DATE: "DATE", PIIType.ABHA: "ABHA_NUMBER",
    PIIType.INSURANCE: "INSURANCE_ID", PIIType.MRN: "MRN", PIIType.ID: "ID", PIIType.ADDRESS: "ADDRESS", PIIType.PINCODE: "PIN",
}


def _alias_uuids(text: str, keys) -> str:
    """Replace every UUID (FHIR resource id, urn:uuid reference) with a keyed, valid UUID. The same UUID always maps to the same
    alias, so references still resolve, and nothing of the original (some carry a phone number's digits) is left."""
    if "-" not in text:
        return text

    def alias(m) -> str:
        h = hmac_hex(keys.docid, "uuid", m.group().lower(), n=32)
        return f"{h[:8]}-{h[8:12]}-4{h[13:16]}-{'89ab'[int(h[16], 16) % 4]}{h[17:20]}-{h[20:32]}"

    return UUID_LIKE.sub(alias, text)


_BLOB = re.compile(r"\s*[A-Za-z0-9+/]{24,}={0,2}\s*")


def _redact_plain(text: str, detectors, days: int, pin_fn) -> str:
    """Detect and redact a short plain string (the decoded text of an attachment)."""
    spans, _ = detect_unit(make_unit("x", None, text), detectors)
    return redact(text, [s for s in spans if s.role != "doctor"], days, [], pin_fn)


def peak_rss_mb() -> float:
    try:
        import resource

        r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return round(r / 1024 if sys.platform != "darwin" else r / 1048576, 1)
    except Exception:  # noqa: BLE001 - not available on Windows
        pass
    try:
        import ctypes
        import ctypes.wintypes as wt

        class PMC(ctypes.Structure):
            _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t), ("a", ctypes.c_size_t), ("b", ctypes.c_size_t),
                        ("c", ctypes.c_size_t), ("d", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t)]

        k, ps = ctypes.windll.kernel32, ctypes.windll.psapi
        k.GetCurrentProcess.restype = wt.HANDLE
        ps.GetProcessMemoryInfo.argtypes = [wt.HANDLE, ctypes.POINTER(PMC), wt.DWORD]
        pm = PMC()
        pm.cb = ctypes.sizeof(pm)
        ps.GetProcessMemoryInfo(k.GetCurrentProcess(), ctypes.byref(pm), pm.cb)
        return round(pm.PeakWorkingSetSize / 2 ** 20, 1)
    except Exception:  # noqa: BLE001
        return 0.0


class Entry:
    def __init__(self, rel: str, sha: str):
        self.rel, self.sha = rel, sha
        self.parsed: Parsed | None = None
        self.reason: str | None = None
        self.out_rel: str | None = None
        self.data: bytes | None = None


def _cleanup(out: Path) -> None:
    for name in ("sanitized", "records.jsonl", "report.json"):
        p = out / name
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        elif p.exists():
            p.unlink()


def _sanitize(inp: Path, out: Path, secret: bytes) -> dict:
    t0 = time.monotonic()
    keys = keys_from_secret(secret)
    cfg = Config()
    detectors = default_detectors()
    max_bytes = cfg.max_file_mb * 1024 * 1024

    def probe(items: list) -> bool:
        """Do these JSON list items carry personal data (a patient name, phone or id)? Cheap trial detection."""
        from ..ingest import _flatten, path_name

        for item in items:
            leaves: list = []
            _flatten(item, [], leaves)
            for path, val, _t in leaves:
                if not val or len(val) < 4 or len(val) > 200:
                    continue
                unit = make_unit("probe", path_name(path) or None, val)
                spans, _m = detect_unit(unit, detectors)
                if any(s.role != "doctor" and s.type in (PIIType.PHONE, PIIType.ABHA, PIIType.MRN, PIIType.EMAIL, PIIType.INSURANCE)
                       or (s.type == PIIType.NAME and s.role in ("patient", "relative")) for s in spans):
                    return True
        return False

    # ---- 1. walk, hash, parse (fail closed per file)
    entries: list[Entry] = []
    for path in sorted((p for p in inp.rglob("*") if p.is_file()), key=lambda p: p.relative_to(inp).as_posix()):
        rel = path.relative_to(inp).as_posix()
        try:
            raw = path.read_bytes()
        except OSError:
            e = Entry(rel, hashlib.sha256(b"").hexdigest())
            e.reason = "unreadable"
            entries.append(e)
            continue
        e = Entry(rel, hashlib.sha256(raw).hexdigest())
        try:
            e.parsed = read_file(rel, raw, keys, max_bytes, probe)
        except Skip as s:
            e.reason = s.reason
        except Exception:  # noqa: BLE001
            e.reason = "internal_error"
        entries.append(e)
        del raw

    # ---- 2. detect
    results: dict = {}
    for e in entries:
        if e.parsed is None:
            continue
        try:
            for rec in e.parsed.recs:
                results[rec.doc.doc_id] = process_doc(rec.doc, detectors)
        except Exception:  # noqa: BLE001
            for rec in e.parsed.recs:
                results.pop(rec.doc.doc_id, None)
            e.parsed, e.reason = None, "internal_error"

    mem = NameMemory()
    for r in results.values():
        for u in r.units:
            mem.learn(u, r.spans[u.field])
    for r in results.values():
        for u in r.units:
            more = mem.find(u, r.spans[u.field])
            if more:
                r.spans[u.field] = sorted(r.spans[u.field] + more, key=lambda s: (s.start, s.end))

    # ---- 3. link, quasi-identifier plan
    mention_of = {d: build_mention(r.doc, r.units, r.spans, r.meds) for d, r in results.items()}
    clusters = link_documents(list(mention_of.values()), keys, cfg)
    raw_ps = {d: c.pseudonym for c in clusters for d in c.doc_ids}
    shown = {d: "PSN-" + p[3:11] for d, p in raw_ps.items()}
    size_of = {d: len(c.doc_ids) for c in clusters for d in c.doc_ids}
    facts = {d: extract_facts(r.doc, r.units, r.spans, r.meds, mention_of[d]) for d, r in results.items()}
    levels, suppress_dx, _rare = plan_levels(facts, raw_ps, cfg)

    # ---- 4. render in place. Doctors stay. A pseudonym is written into a record only when we also claim it.
    red: dict[str, RedactedRecord] = {}
    claim: dict[str, str | None] = {}
    entities: Counter = Counter()
    n_ids = 0
    for e in entries:
        if e.parsed is None:
            continue
        for rec in e.parsed.recs:
            doc = rec.doc
            r = results[doc.doc_id]
            ps, linked = shown[doc.doc_id], size_of[doc.doc_id] >= 2
            days = shift_days(keys, cfg, raw_ps[doc.doc_id])
            lvl = levels[doc.doc_id]
            texts = {u.field: u.original for u in r.units}
            ov = overrides(facts[doc.doc_id], texts, lvl, doc.doc_id in suppress_dx, cfg)

            def pin_fn(t: str, lvl: int = lvl) -> str:
                d = "".join(c for c in ocr_digit_view(normalize(t).text) if c.isdigit())
                return pin_text(d if len(d) == 6 else None, lvl, cfg)

            has_patient = linked and any(s.type == PIIType.NAME and s.role == "patient" for ss in r.spans.values() for s in ss)
            embedded = False
            text, fields = "", dict(doc.fields)
            for u in r.units:
                keep = [s for s in r.spans[u.field] if s.role != "doctor"]
                for s in keep:
                    entities["PATIENT_NAME" if (s.type == PIIType.NAME and s.role == "patient") else
                             "RELATIVE_NAME" if (s.type == PIIType.NAME and s.role == "relative") else ENTITY_LABEL[s.type]] += 1
                n_ids += len(keep)
                extras = list(ov.get(u.field, ()))
                if linked:
                    repl = [s for s in keep if s.type == PIIType.NAME and s.role == "patient"] if has_patient else \
                           [s for s in keep if s.type == PIIType.MRN]
                    if repl:
                        embedded = True
                        keep = [s for s in keep if s not in repl]
                        extras += [(s.start, s.end, ps) for s in repl]
                out_text = redact(u.original, keep, days, extras, pin_fn)
                out_text = _alias_uuids(out_text, keys)
                if u.field is not None and _BLOB.fullmatch(u.original):
                    # a base64 attachment must stay valid base64: clean the decoded text and re-encode it
                    out_text = clean_encoded(u.original, lambda t, d=days, f=pin_fn: _redact_plain(t, detectors, d, f))
                if u.field is None:
                    text = out_text
                else:
                    fields[u.field] = out_text
            if doc.text and not r.units:
                text = doc.text
            if linked and not embedded and doc.source == "txt":
                text = f"Patient: {ps}\n{text}"  # a note with no usable name or id: the pseudonym goes on its own line
                embedded = True
            meta = {"generalization_level": str(lvl)}
            red[doc.doc_id] = RedactedRecord(doc.doc_id, doc.hospital, ps, doc.source, doc.ordinal, text, fields, meta, {})
            claim[doc.doc_id] = ps if (linked and embedded) else None

    # ---- 5. leak gate (repair only: never drops a record)
    red, _gated, gate_stats = gate(red, results, cfg, mode="redact")

    # ---- 6. rebuild every file in its original format
    renamer = Renamer(keys, detectors, mem)
    used: set[str] = set()
    lines: list[dict] = []
    for e in entries:
        if e.parsed is None:
            continue
        p = e.parsed
        try:
            if p.kind in ("csv", "tsv"):
                data = write_csv(p, red, renamer.header)
            elif p.kind == "json":
                data = write_json(p, red, renamer.key, keys)
            else:
                data = write_txt(p, red)
            new_rel = renamer.path(e.rel)
            if new_rel in used:
                new_rel = renamer.path(e.rel + "#" + e.sha[:8])
                if new_rel in used:
                    new_rel = f"d_{e.sha[:12]}/{Path(e.rel).name}" if False else f"f_{e.sha[:12]}{Path(e.rel).suffix}"
            used.add(new_rel)
        except Exception:  # noqa: BLE001
            e.parsed, e.reason = None, "internal_error"
            continue
        e.out_rel, e.data = new_rel, data
        for rec in p.recs:
            if rec.loc is None or not rec.doc.fields and not rec.doc.text:
                continue
            lines.append({"file": f"sanitized/{new_rel}", "loc": rec.loc, "patient": claim[rec.doc.doc_id]})

    n_san = sum(1 for e in entries if e.data is not None)
    report = {
        "schema": "raksha-report/1",
        "files": [
            ({"input_sha256": e.sha, "output": f"sanitized/{e.out_rel}", "status": "sanitized"} if e.data is not None else
             {"input_sha256": e.sha, "output": None, "status": "quarantined", "reason": e.reason or "internal_error"})
            for e in entries
        ],
        "counts": {
            "files_total": len(entries), "files_sanitized": n_san, "files_quarantined": len(entries) - n_san,
            "records_processed": len(lines), "identifiers_detected": n_ids,
            "records_linked": sum(1 for x in lines if x["patient"] is not None),
            "records_generalized": sum(1 for d, v in levels.items() if v > 0 and d in red),
            "records_suppressed": 0, "records_quarantined": 0,
        },
        "entities": dict(sorted(entities.items())),
        "timing": {"seconds": round(time.monotonic() - t0, 2)},
        "resources": {"peak_rss_mb": peak_rss_mb()},
    }
    return {"entries": entries, "lines": lines, "report": report, "gate": gate_stats}


def run_contract(inp: Path, out: Path, secret: bytes) -> int:
    out.mkdir(parents=True, exist_ok=True)
    try:
        res = _sanitize(inp, out, secret)
        for e in res["entries"]:
            if e.data is not None:
                dest = out / "sanitized" / e.out_rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(e.data)
        (out / "sanitized").mkdir(exist_ok=True)
        with open(out / "records.jsonl", "w", encoding="utf-8", newline="\n") as f:
            for line in res["lines"]:
                f.write(json.dumps(line, ensure_ascii=False, sort_keys=True) + "\n")
        (out / "report.json").write_text(json.dumps(res["report"], indent=2) + "\n", encoding="utf-8")  # last: marks completion
    except KeysMissing:
        _cleanup(out)
        print("error: RAKSHA_SECRET is not set", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - messages can echo record content: print the type only
        _cleanup(out)
        print(f"error: run failed ({type(exc).__name__})", file=sys.stderr)
        return 1
    c = res["report"]["counts"]
    print(f"files {c['files_total']} sanitized {c['files_sanitized']} quarantined {c['files_quarantined']} "
          f"records {c['records_processed']} linked {c['records_linked']}")
    return 0
