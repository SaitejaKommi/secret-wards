"""Orchestration only: ingest -> normalize -> detect -> link -> pseudonymize -> generalize -> render
-> leak gate -> export. All real work lives in the stage packages."""
from __future__ import annotations

import json
import shutil
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

import regex as re

from .config import Config
from .contracts import (Detector, Document, MedSpan, PIIType, QReason, QuarantineEntry, RedactedRecord, SourceFile,
                        Span, Unit)
from .detect import default_detectors, detect_unit, propagate_names
from .detect.learned import NameMemory
from .export.csv_json import Namer, write_source
from .ingest import ingest_dir
from .link import link_documents
from .link.mention import build_mention
from .normalize.text import normalize
from .normalize.text import ocr_digit_view
from .privacy.generalize import age_text, extract_facts, overrides, pin_text, plan_levels
from .privacy.pseudonym import shift_days
from .privacy.render import redact
from .privacy.risk import measure
from .security import safe_log
from .security.keys import Keys, hmac_hex

OUT_DIRS = ("deidentified", "quarantine")
OUT_FILES = ("report.json", "deidentified.json", "manifest.json", "eval_spans.json")


def field_ref(keys: Keys, f: Optional[str]) -> str:
    """Keyed reference to a column / JSON path: lets evaluation match fields without writing them."""
    return "" if f is None else hmac_hex(keys.docid, "fld", f, n=8)


def header_of(field_name: str) -> str:
    """Header hint for a table column or JSON path: last key, snake/camel case split into words."""
    s = re.sub(r"\[\d+\]", "", field_name)
    s = s.split(".")[-1]
    s = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s).replace("_", " ")
    return s.strip().lower()


def safe_field(namer: Namer, f: str, path: list | None) -> str:
    """Column headers / JSON keys can carry PII: only vocabulary words survive, the rest become keyed hashes."""
    if path is None:
        return namer.name(f)
    s = ""
    for p in path:
        s += f"[{p}]" if isinstance(p, int) else (("." if s else "") + namer.name(p, "key"))
    return s or "_value"


def make_unit(doc_id: str, fld: Optional[str], text: str) -> Unit:
    return Unit(doc_id, fld, header_of(fld) if fld else "", text, normalize(text))


@dataclass
class DocResult:
    doc: Document
    units: list[Unit]
    spans: dict[Optional[str], list[Span]]
    meds: dict[Optional[str], list[MedSpan]]


def process_doc(doc: Document, detectors: Sequence[Detector]) -> DocResult:
    units: list[Unit] = []
    if doc.text:
        units.append(make_unit(doc.doc_id, None, doc.text))
    for f, v in doc.fields.items():
        if v and v.strip():
            units.append(make_unit(doc.doc_id, f, v))
    spans: dict = {}
    meds: dict = {}
    for u in units:
        s, m = detect_unit(u, detectors)
        spans[u.field] = s
        meds[u.field] = m
    extra = propagate_names(units, spans)
    for f, more in extra.items():
        spans[f] = sorted(spans[f] + more, key=lambda s: (s.start, s.end))
    return DocResult(doc, units, spans, meds)


def _clean_out(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for d in OUT_DIRS:
        if (out / d).exists():
            shutil.rmtree(out / d)
    for f in OUT_FILES:
        if (out / f).exists():
            (out / f).unlink()


def run(in_dir: Path, out_dir: Path, cfg: Config, keys: Keys, detectors: Sequence[Detector] | None = None) -> dict:
    t0 = time.perf_counter()
    detectors = list(detectors) if detectors is not None else default_detectors()
    _clean_out(out_dir)
    (out_dir / "deidentified").mkdir()
    (out_dir / "quarantine").mkdir()

    files, quarantined = ingest_dir(in_dir, cfg, keys)
    safe_log.log("ingest_done", files=len(files), quarantined=len(quarantined))

    results: dict[str, DocResult] = {}
    n_docs = 0
    for sf in files:
        for doc in sf.docs:
            n_docs += 1
            try:
                results[doc.doc_id] = process_doc(doc, detectors)
            except Exception as e:  # fail closed: the record is dropped, only the exception type is logged
                quarantined.append(QuarantineEntry(doc.doc_id, QReason.INTERNAL_ERROR, "record"))
                safe_log.log("doc_failed", err=safe_log.exc_code(e))
    # dataset-level name memory: names found with strong evidence are flagged everywhere else too
    mem = NameMemory()
    for r in results.values():
        for u in r.units:
            mem.learn(u, r.spans[u.field])
    for r in results.values():
        for u in r.units:
            more = mem.find(u, r.spans[u.field])
            if more:
                r.spans[u.field] = sorted(r.spans[u.field] + more, key=lambda s: (s.start, s.end))
    t_detect = time.perf_counter()

    # --- link & pseudonymize
    mention_of = {d: build_mention(r.doc, r.units, r.spans, r.meds) for d, r in results.items()}
    clusters = link_documents(list(mention_of.values()), keys, cfg)
    pseud_of = {d: c.pseudonym for c in clusters for d in c.doc_ids}

    # --- quasi-identifier plan: generalize only where k-anonymity needs it
    facts = {d: extract_facts(r.doc, r.units, r.spans, r.meds, mention_of[d]) for d, r in results.items()}
    levels, suppress_dx, rare_dx = plan_levels(facts, pseud_of, cfg)

    # --- generalize / render
    namer = Namer(keys)
    records: dict[str, RedactedRecord] = {}
    counts: Counter = Counter()
    for sf in files:
        for doc in sf.docs:
            r = results.get(doc.doc_id)
            if r is None:
                continue
            ps = pseud_of[doc.doc_id]
            days = shift_days(keys, cfg, ps)
            text = ""
            fields: dict[str, str] = {}
            lvl = levels[doc.doc_id]
            texts = {u.field: u.original for u in r.units}
            ov = overrides(facts[doc.doc_id], texts, lvl, doc.doc_id in suppress_dx, cfg)

            def pin_fn(t: str, lvl: int = lvl) -> str:
                d = "".join(c for c in normalize(ocr_digit_view(normalize(t).text)).text if c.isdigit())
                return pin_text(d if len(d) == 6 else None, lvl, cfg)

            for u in r.units:
                red = redact(u.original, r.spans[u.field], days, ov.get(u.field, ()), pin_fn)
                if u.field is None:
                    text = red
                else:
                    fields[u.field] = red
                for s in r.spans[u.field]:
                    counts[s.type.value] += 1
            for f, v in doc.fields.items():
                if f not in fields:
                    fields[f] = v  # empty / whitespace-only cells
            raw_paths = sf.layout.get("paths", {}).get(doc.ordinal, {})
            ordered, paths, used = {}, {}, set()
            for f in doc.fields:
                sn = safe_field(namer, f, raw_paths.get(f))
                while sn in used:
                    sn += "_"
                used.add(sn)
                ordered[sn] = fields[f]
                if f in raw_paths:
                    paths[sn] = [p if isinstance(p, int) else namer.name(p, "key") for p in raw_paths[f]]
            fa = facts[doc.doc_id]
            meta = {"generalization_level": str(lvl)}
            if fa.age is not None:
                meta["age"] = age_text(fa.age, lvl, cfg)
            if fa.sex:
                meta["sex"] = fa.sex
            if fa.pin:
                meta["pin_prefix"] = pin_text(fa.pin, lvl, cfg)
            records[doc.doc_id] = RedactedRecord(doc.doc_id, doc.hospital, ps, doc.source, doc.ordinal, text, ordered, meta, paths)

    # --- leak gate (see security/leak_gate.py)
    from .security.leak_gate import gate
    records, gated, gate_stats = gate(records, results, cfg)
    quarantined.extend(gated)
    risk = measure(facts, levels, pseud_of, rare_dx, cfg)

    # --- export
    manifest = []
    for sf in files:
        recs = [records[d.doc_id] for d in sf.docs if d.doc_id in records]
        outs = write_source(out_dir / "deidentified", sf, recs, namer) if recs else []
        manifest.append({"input_ordinal": sf.ordinal, "kind": sf.kind, "records_in": len(sf.docs), "records_out": len(recs),
                         "outputs": [o for o, _ in outs]})
    ordered_recs = []
    for sf in files:
        for d in sf.docs:
            if d.doc_id in records:
                ordered_recs.append(records[d.doc_id])
    (out_dir / "deidentified.json").write_text(json.dumps([
        {"doc_id": r.doc_id, "hospital": r.hospital, "pseudonym": r.pseudonym, "source": r.source, "ordinal": r.ordinal,
         "text": r.text, "fields": r.fields, "meta": r.meta} for r in ordered_recs], ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True), encoding="utf-8")
    qj = [{"ref": q.ref, "reason": q.reason.value, "scope": q.scope} for q in sorted(quarantined, key=lambda q: (q.scope, q.ref))]
    (out_dir / "quarantine" / "index.json").write_text(json.dumps(qj, indent=1), encoding="utf-8")
    if cfg.emit_spans:
        dump = {d: sorted([[field_ref(keys, f), s.start, s.end, s.type.value, s.detector, s.role] for f, ss in r.spans.items() for s in ss])
                for d, r in sorted(results.items())}
        (out_dir / "eval_spans.json").write_text(json.dumps(dump), encoding="utf-8")

    reasons = Counter(q.reason.value for q in quarantined if q.scope == "file")
    rec_q = Counter(q.reason.value for q in quarantined if q.scope == "record")
    cl_sizes = Counter(len(c.doc_ids) for c in clusters)
    report = {
        "files": {"total": len(files) + sum(1 for q in quarantined if q.scope == "file"), "processed": len(files),
                  "quarantined": sum(reasons.values()), "quarantine_reasons": dict(sorted(reasons.items()))},
        "records": {"total": n_docs, "output": len(records), "quarantined": sum(rec_q.values()),
                    "quarantine_reasons": dict(sorted(rec_q.items()))},
        "detections": dict(sorted(counts.items())),
        "patients": {"pseudonyms": len(clusters), "cluster_size_histogram": {str(k): v for k, v in sorted(cl_sizes.items())}},
        "privacy": {**risk, "policy": "age exact unless k-anonymity needs a band; ages >= %d reported as N+; PIN reduced to a prefix; "
                    "street address, names, phones, ids removed; dates shifted per patient; rare diagnoses suppressed only when "
                    "still unique after coarser age/PIN" % cfg.age_top_code,
                    "records_generalized": sum(1 for v in levels.values() if v > 0), "rare_diagnoses_suppressed": len(suppress_dx),
                    "date_shift_days_range": [cfg.date_shift_min_days, cfg.date_shift_max_days]},
        "leak_gate": gate_stats,
        "note": "counts only; no record values appear in this report",
    }
    (out_dir / "report.json").write_text(json.dumps(report, indent=1, sort_keys=True), encoding="utf-8")
    t1 = time.perf_counter()
    safe_log.log("run_done", records=len(records), detect_s=round(t_detect - t0, 2), total_s=round(t1 - t0, 2))
    return report
