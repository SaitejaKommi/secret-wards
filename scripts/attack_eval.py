"""MEASUREMENT ONLY: score the stand-in attacker (secretwards.privacy.attack) against an answer key.

The attacker itself never sees the answer key; this script only uses it to say whether the attacker's beliefs are right.
Prints counts and rates only (no names, ids or values).

usage:
  python scripts/attack_eval.py --kit ../Secret-Wards-ToolKit/dev --release raw                 # attack the raw input
  python scripts/attack_eval.py --kit ../Secret-Wards-ToolKit/dev --release out/ours            # attack our output
  python scripts/attack_eval.py --kit ../Secret-Wards-ToolKit/dev --release out/ours --other out/ours_secret2   # + A7
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from secretwards.contract.readers import Skip, read_file
from secretwards.pipeline import header_of
from secretwards.privacy import attack as A
from secretwards.security.keys import keys_from_secret


def release_records(kit: Path, release: str):
    """[(input rel, loc, pairs)] for the raw input or for an output folder (renames followed through report.json)."""
    truth = json.loads((kit / "truth" / "truth.json").read_text(encoding="utf-8"))
    keys = keys_from_secret(b"attack-eval")
    if release == "raw":
        files = [(rel, kit / "input" / rel) for rel in truth["files"]]
    else:
        out = Path(release)
        rep = json.loads((out / "report.json").read_text(encoding="utf-8"))
        by_sha = {e["input_sha256"]: e for e in rep["files"]}
        files = []
        for rel, f in truth["files"].items():
            e = by_sha.get(f["sha256"])
            if e and e.get("status") == "sanitized" and e.get("output"):
                files.append((rel, out / e["output"]))
    recs = []
    for rel, path in files:
        try:
            parsed = read_file(rel, path.read_bytes(), keys, 50_000_000)
        except (Skip, OSError, ValueError):
            continue
        for r in parsed.recs:
            pairs = [(header_of(k), v) for k, v in r.doc.fields.items()]
            if r.doc.text:
                pairs.append(("", r.doc.text))
            recs.append((rel, r.loc, pairs))
    return truth, recs


def pseudonyms_of(release: str) -> frozenset:
    if release == "raw":
        return frozenset()
    p = Path(release) / "records.jsonl"
    out = set()
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                v = json.loads(line).get("patient")
                if v:
                    out.add(v)
    return frozenset(out)


def evaluate(kit: Path, release: str) -> dict:
    reg = A.Registry.load(kit / "attacker" / "registry.csv")
    facts = A.load_facts(kit / "attacker" / "known_facts.jsonl")
    truth, recs = release_records(kit, release)
    rid_of = {pid: p["rid"] for pid, p in truth["patients"].items()}
    psn = pseudonyms_of(release)
    evs = [A.extract(pairs, reg, psn) for _rel, _loc, pairs in recs]
    years = [d.year for e in evs for d in e.dates]
    ref_year = int(statistics.median(years)) if years else 2025

    true_rid = []
    mapped = 0
    for rel, loc, _p in recs:
        u = truth["files"].get(rel, {}).get("units", {}).get(loc)
        if u is not None:
            mapped += 1
        true_rid.append(rid_of.get(u.get("patient")) if u else None)

    rec_probs = [A.link(e, reg, ref_year) for e in evs]
    groups = A.profiles(evs)
    prof_evs = [A.pool([evs[i] for i in g]) for g in groups]
    prof_probs = [A.link(e, reg, ref_year) for e in prof_evs]
    prof_of = {i: gi for gi, g in enumerate(groups) for i in g}

    # A2/A3: mean probability on the true person over patient records
    a3 = [rec_probs[i][0].get(r, 0.0) for i, r in enumerate(true_rid) if r]
    # A4: a patient is re-identified if any of their records reaches >= 0.5 (record or profile level)
    best = defaultdict(float)
    why = {}
    for i, r in enumerate(true_rid):
        if not r:
            continue
        pr, used_r = rec_probs[i]
        pp, used_p = prof_probs[prof_of[i]]
        p_rec, p_prof = pr.get(r, 0.0), pp.get(r, 0.0)
        p = max(p_rec, p_prof)
        if p > best[r]:
            best[r] = p
            why[r] = used_p if p_prof >= p_rec else used_r
    patients = sorted(best)
    identified = [r for r in patients if best[r] >= 0.5]
    why_counts = Counter(k for r in identified for k in why.get(r, []))

    # A5: targeted attack after trying to recover one global shift
    prof_top = [max(pp.items(), key=lambda kv: kv[1]) if pp else ("", 0.0) for pp, _u in prof_probs]
    shift = A.recover_global_shift(prof_evs, prof_top, facts)
    tgt = A.targeted(facts, prof_evs, reg, ref_year, shift)
    prof_true = []
    for g in groups:
        c = Counter(true_rid[i] for i in g if true_rid[i])
        prof_true.append(c.most_common(1)[0][0] if c else None)
    pat_rids = set(rid_of.values())
    a5 = []
    decoy_claims = 0
    for f in facts:
        dist = tgt.get(f.rid, {})
        if f.rid in pat_rids:
            a5.append(sum(p for gi, p in dist.items() if prof_true[gi] == f.rid))
        elif dist:
            decoy_claims += 1

    # A6: pseudonym inversion: does a pseudonym equal / embed / prefix a transform of a patient's originals?
    inverted = 0
    if psn:
        forms = set()
        for p in truth["patients"].values():
            origs = {str(u) for u in p.get("uhids") or []}
            per = reg.by_rid.get(p["rid"])
            if per and per.phone:
                origs.add(per.phone)
            for o in origs:
                digits = "".join(c for c in o if c.isdigit())
                forms |= {o.lower(), digits} | {h(o.encode()).hexdigest() for h in (hashlib.md5, hashlib.sha1, hashlib.sha256, hashlib.sha512)}
        forms = {f for f in forms if len(f) >= 6}
        for ps in psn:
            core = ps.lower().split("-")[-1]
            if any(f in ps.lower() or (len(core) >= 8 and f.startswith(core)) for f in forms):
                inverted += 1

    return {
        "records": len(recs), "records_mapped_to_truth": mapped, "patient_records": len(a3),
        "A3_mean_prob_true": sum(a3) / len(a3) if a3 else 0.0,
        "A4_patients": len(patients), "A4_identified": len(identified),
        "A4_rate": len(identified) / len(patients) if patients else 0.0,
        "A4_why": dict(why_counts.most_common()),
        "profiles": len(groups), "global_shift_recovered": shift is not None,
        "A5_fact_patients": len(a5), "A5_mean_success": sum(a5) / len(a5) if a5 else 0.0,
        "A5_decoy_claims": decoy_claims,
        "A6_pseudonyms": len(psn), "A6_inverted": inverted,
        "_best": dict(best),
    }


def a7(kit: Path, a: str, b: str) -> dict:
    """Two runs with different secrets: records (matched by input SHA-256 + locator) that keep the same pseudonym,
    and records whose dates all land on the same values."""
    from secretwards.normalize.dates import find_dates

    def load(release):
        out = Path(release)
        rep = json.loads((out / "report.json").read_text(encoding="utf-8"))
        sha_of = {e["output"]: e["input_sha256"] for e in rep["files"] if e.get("output")}
        ps = {}
        for line in (out / "records.jsonl").read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                f = d["file"] if d["file"].startswith("sanitized/") else "sanitized/" + d["file"]
                ps[(sha_of.get(f), d["loc"])] = d.get("patient")
        dates = {}
        for o, sha in sha_of.items():
            p = out / o
            if p.is_file():
                txt = p.read_text(encoding="utf-8", errors="replace")
                dates[sha] = sorted((m.y, m.m, m.d) for m in find_dates(txt) if m.d)
        return ps, dates

    pa, da = load(a)
    pb, db = load(b)
    both = [k for k in pa if k in pb and pa[k] and pb[k]]
    same_ps = sum(1 for k in both if pa[k] == pb[k])
    files = [s for s in da if s in db and da[s]]
    same_dates = sum(1 for s in files if da[s] == db[s])
    return {"A7_records_compared": len(both), "A7_same_pseudonym": same_ps,
            "A7_files_with_dates": len(files), "A7_files_all_dates_same": same_dates}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kit", required=True, help="kit dev folder (input/, truth/, attacker/)")
    ap.add_argument("--release", required=True, help="'raw' or an output folder")
    ap.add_argument("--other", help="a second output folder made with a different secret (A7)")
    a = ap.parse_args()
    res = evaluate(Path(a.kit), a.release)
    res.pop("_best")
    if a.other:
        res.update(a7(Path(a.kit), a.release, a.other))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
