"""Scorer: compares pipeline output with gold. Prints counts and rates only (no record values),
except with --show-misses, a dev flag that prints SYNTHETIC gold strings to help debugging.

Metrics
  span recall/precision   per coarse type, from eval_spans.json (offsets only), >=50% overlap rule
  leak rate               gold PII text still present in the output record (exact / name-token)
  medical retention       gold medical values still present in the output record
  linkage                 pairwise precision / recall of pseudonym clusters vs gold patients
  canary leaks            planted strings found anywhere under the output dir (content or names)
  quarantine              expected bad files were quarantined, nothing else was
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from secretwards.security.keys import hmac_hex, load_keys


def _fref(keys, f):
    return "" if f is None else hmac_hex(keys.docid, "fld", f, n=8)

GROUP = {"NAME": "NAME", "PHONE": "PHONE", "EMAIL": "EMAIL", "DATE": "DATE", "ABHA": "ID", "INSURANCE": "ID", "MRN": "ID",
         "ID": "ID", "ADDRESS": "LOC", "PINCODE": "LOC"}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s)).strip().casefold()


def _digits(s: str) -> str:
    out = []
    for c in unicodedata.normalize("NFKC", s):
        d = unicodedata.decimal(c, None)
        if d is not None:
            out.append(str(d))
    return "".join(out)


def _cover(gs: int, ge: int, preds: list[tuple[int, int]]) -> float:
    cov = 0
    last = gs
    for a, b in sorted(preds):
        a, b = max(a, last), min(b, ge)
        if b > a:
            cov += b - a
            last = b
    return cov / max(1, ge - gs)


def _rate(n: int, d: int) -> float | None:
    return None if d == 0 else round(n / d, 4)


def score(gold_path: Path, out_dir: Path, keys_dir: str = "keys", show: int = 0) -> dict:
    gold = json.loads(gold_path.read_text(encoding="utf-8"))
    keys = load_keys(keys_dir)
    out_recs = {r["doc_id"]: r for r in json.loads((out_dir / "deidentified.json").read_text(encoding="utf-8"))}
    spans_path = out_dir / "eval_spans.json"
    spans = json.loads(spans_path.read_text(encoding="utf-8")) if spans_path.exists() else None

    def did(rec) -> str:
        return hmac_hex(keys.docid, "doc", rec["file"], str(rec["index"]), n=16)

    # ---------------- span-level + leak + medical
    t_hit, t_tot = Counter(), Counter()  # typed recall by group
    a_hit = Counter()  # any-type recall (was it redacted at all)
    p_tp, p_tot = Counter(), Counter()
    leak_exact, leak_tot = Counter(), Counter()
    name_tok_leak, name_tok_tot = 0, 0
    med_hit, med_tot = Counter(), Counter()
    age_ok = age_exact = 0
    misses = defaultdict(list)
    n_gold_recs = 0
    for rec in gold["records"]:
        d = did(rec)
        if d not in out_recs:
            continue
        n_gold_recs += 1
        o = out_recs[d]
        blob = _norm(o["text"] + "\n" + "\n".join(o["fields"].values()))
        dblob = _digits(blob)
        words = set(re.findall(r"[\wऀ-ॿ]+", blob))
        # spans for this doc
        pr = spans.get(d, []) if spans is not None else None
        for g in rec["pii"]:
            grp = GROUP[g["type"]]
            t_tot[grp] += 1
            if pr is not None:
                same = [(s[1], s[2]) for s in pr if s[0] == _fref(keys, g["field"]) and GROUP[s[3]] == grp]
                anyp = [(s[1], s[2]) for s in pr if s[0] == _fref(keys, g["field"])]
                if _cover(g["start"], g["end"], same) >= 0.5:
                    t_hit[grp] += 1
                elif show and len(misses[grp]) < show:
                    misses[grp].append(g["text"])
                if _cover(g["start"], g["end"], anyp) >= 0.5:
                    a_hit[grp] += 1
            txt = _norm(g["text"])
            leak_tot[grp] += 1
            if grp == "PHONE":
                dg = _digits(g["text"])
                leaked = len(dg) >= 8 and dg in dblob
            elif grp == "DATE":
                leaked = len(txt) >= 6 and txt in blob
            else:
                leaked = len(txt) >= 4 and txt in blob
            if leaked:
                leak_exact[grp] += 1
            if grp == "NAME":
                for w in re.findall(r"[\wऀ-ॿ]+", txt):
                    if len(w) >= 4 and g.get("role") != "doctor":
                        name_tok_tot += 1
                        if w in words:
                            name_tok_leak += 1
        for m in rec["med"]:
            med_tot[m["kind"]] += 1
            if _norm(m["text"]) in blob:
                med_hit[m["kind"]] += 1
                if m["kind"] == "AGE":
                    age_ok += 1
                    age_exact += 1
            elif m["kind"] == "AGE":
                # a generalized age is acceptable when the released band still contains the true age
                try:
                    true_age = int(_digits(m["text"])[:3])
                    band = o.get("meta", {}).get("age", "")
                    if band.endswith("+"):
                        ok = true_age >= int(band[:-1])
                    elif band.startswith("<"):
                        ok = true_age < int(band[1:])
                    else:
                        lo, hi = (int(x) for x in band.split("-"))
                        ok = lo <= true_age <= hi
                except (ValueError, TypeError):
                    ok = False
                age_ok += 1 if ok else 0
            if False:
                pass
        if pr is not None:
            gold_by_field = defaultdict(list)
            for g in rec["pii"]:
                gold_by_field[_fref(keys, g["field"])].append((g["start"], g["end"]))
            for s in pr:
                grp = GROUP[s[3]]
                p_tot[grp] += 1
                if _cover(s[1], s[2], gold_by_field.get(s[0], [])) >= 0.5:
                    p_tp[grp] += 1

    # ---------------- linkage
    by_pred: dict[str, Counter] = defaultdict(Counter)
    for rec in gold["records"]:
        d = did(rec)
        if d in out_recs and rec["patient"] is not None:
            by_pred[out_recs[d]["pseudonym"]][rec["patient"]] += 1
    c2 = lambda n: n * (n - 1) // 2  # noqa: E731
    tp = sum(c2(n) for c in by_pred.values() for n in c.values())
    pred_pairs = sum(c2(sum(c.values())) for c in by_pred.values())
    gold_cnt = Counter()
    for c in by_pred.values():
        gold_cnt.update(c)
    gold_pairs = sum(c2(n) for n in gold_cnt.values())
    twin = {p: v["twin_of"] for p, v in gold["patients"].items() if v["twin_of"]}
    twin_pairs = {frozenset((a, b)) for a, b in twin.items()}
    bad_twin_merges = sum(1 for c in by_pred.values() if any(frozenset((a, b)) in twin_pairs for a in c for b in c if a < b))
    multi = sum(1 for c in by_pred.values() if len(c) > 1)

    # ---------------- canaries over everything written
    texts, names_ = [], []
    for p in sorted(out_dir.rglob("*")):
        names_.append(p.relative_to(out_dir).as_posix())
        if p.is_file():
            texts.append(p.read_bytes().decode("utf-8", errors="ignore"))
    big = _norm("\n".join(texts + names_))
    bigd = _digits(big)
    cn_leaks = 0
    cn_by_where = Counter()
    for c in gold["canaries"]:
        if c["type"] == "PHONE":
            hit = _digits(c["text"]) in bigd
        else:
            hit = _norm(c["text"]) in big
        if hit:
            cn_leaks += 1
            cn_by_where[c["where"]] += 1

    # ---------------- quarantine
    qidx = json.loads((out_dir / "quarantine" / "index.json").read_text(encoding="utf-8"))
    qrefs = {q["ref"] for q in qidx if q["scope"] == "file"}
    exp = {hmac_hex(keys.docid, "file", r, n=12) for r in gold["quarantine_expected"]}

    res = {
        "records_scored": n_gold_recs,
        "span_recall_typed": {g: _rate(t_hit[g], t_tot[g]) for g in sorted(t_tot)} if spans is not None else None,
        "span_recall_any": {g: _rate(a_hit[g], t_tot[g]) for g in sorted(t_tot)} if spans is not None else None,
        "span_precision": {g: _rate(p_tp[g], p_tot[g]) for g in sorted(p_tot)} if spans is not None else None,
        "recall_overall": _rate(sum(a_hit.values()), sum(t_tot.values())) if spans is not None else None,
        "precision_overall": _rate(sum(p_tp.values()), sum(p_tot.values())) if spans is not None else None,
        "leak_rate_exact": {g: _rate(leak_exact[g], leak_tot[g]) for g in sorted(leak_tot)},
        "leak_rate_overall": _rate(sum(leak_exact.values()), sum(leak_tot.values())),
        "name_token_leak": _rate(name_tok_leak, name_tok_tot),
        "medical_retention": {k: _rate(med_hit[k], med_tot[k]) for k in sorted(med_tot)},
        "age_exact_kept": _rate(age_exact, med_tot["AGE"]),
        "age_kept_or_in_released_band": _rate(age_ok, med_tot["AGE"]),
        "medical_retention_overall": _rate(sum(med_hit.values()) - med_hit["AGE"] + age_ok, sum(med_tot.values())),
        "link_precision": _rate(tp, pred_pairs),
        "link_recall": _rate(tp, gold_pairs),
        "clusters_with_multiple_patients": multi,
        "twin_pairs_merged": bad_twin_merges,
        "twin_pairs_total": len(twin_pairs),
        "canary_total": len(gold["canaries"]),
        "canary_leaks": cn_leaks,
        "canary_leaks_by_where": dict(cn_by_where),
        "quarantine_expected": len(exp),
        "quarantine_found": len(exp & qrefs),
        "quarantine_unexpected": len(qrefs - exp),
    }
    if show:
        res["_misses"] = {k: v for k, v in misses.items()}
    return res


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m eval")
    ap.add_argument("--gold", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--keys-dir", default="keys")
    ap.add_argument("--json", default=None)
    ap.add_argument("--show-misses", type=int, default=0, help="dev only: print N synthetic missed strings per type")
    a = ap.parse_args()
    r = score(Path(a.gold), Path(a.out), a.keys_dir, a.show_misses)
    print(json.dumps(r, indent=1, ensure_ascii=False))
    if a.json:
        Path(a.json).write_text(json.dumps(r, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
