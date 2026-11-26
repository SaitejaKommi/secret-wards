"""Re-identification risk of the released data, measured with our own linkage attack.

Attacker model (worst case, voter-list scenario): for each patient the attacker knows exact age,
sex, full PIN code and the diagnosis ("a 47-year-old woman from Ward 12 with dengue"). The attacker
looks for released patients compatible with that knowledge. If exactly one is compatible the patient
is re-identified. We report the same attack on the raw data (baseline) and on the release.

Also reported: k-anonymity of the released quasi-identifier tuple and a simple l-diversity (distinct
diagnoses per class). All numbers are over patients (pseudonyms), not records.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Mapping

from ..config import Config
from .generalize import Facts, age_text, qi_key


def _compatible(release: tuple, f: Facts, cfg: Config) -> bool:
    age, sex, pin, dx = release
    if age is not None and f.age is not None:
        if str(age) == "<18":
            if f.age >= 18:
                return False
        elif "-" in str(age):
            lo, hi = (int(x) for x in str(age).split("-"))
            if not (lo <= f.age <= hi):
                return False
        elif str(age).endswith("+"):
            if f.age < int(str(age)[:-1]):
                return False
        elif int(age) != f.age:
            return False
    if sex is not None and f.sex is not None and sex != f.sex:
        return False
    if pin is not None and f.pin and pin != "[PIN]" and not f.pin.startswith(pin.rstrip("X")):
        return False
    if dx not in (None, "[suppressed]") and f.dx is not None and dx != f.dx:
        return False
    return True


def _attack(rows: list[tuple[tuple, Facts]], cfg: Config, use_los: bool = False) -> dict:
    """rows: (released qi tuple, true facts) per patient. Returns attack statistics."""
    bucket: dict[tuple, list[int]] = defaultdict(list)
    for i, (rel, _f) in enumerate(rows):
        bucket[(rel[1], (rel[2] or "")[:2])].append(i)
    uniq = 0
    risk_sum = 0.0
    worst = 0.0
    n = 0
    for i, (rel, f) in enumerate(rows):
        if f.age is None and f.pin is None and f.dx is None:
            continue
        cands = []
        for (sx, p2), idxs in bucket.items():
            if sx is not None and f.sex is not None and sx != f.sex:
                continue
            if p2 and f.pin and p2 != f.pin[:2] and p2 != "[P":
                continue
            cands.extend(idxs)
        m = sum(1 for j in cands if _compatible(rows[j][0], f, cfg) and (not use_los or f.los is None or rows[j][1].los is None or rows[j][1].los == f.los))
        m = max(m, 1)
        n += 1
        uniq += 1 if m == 1 else 0
        risk_sum += 1.0 / m
        worst = max(worst, 1.0 / m)
    return {"patients": n, "uniquely_reidentified": round(uniq / n, 4) if n else 0.0,
            "mean_risk": round(risk_sum / n, 4) if n else 0.0, "max_risk": round(worst, 4)}


def measure(facts: Mapping[str, Facts], level: Mapping[str, int], pseud_of: Mapping[str, str], rare: frozenset, cfg: Config) -> dict:
    # one row per patient: the record with the lowest doc_id (deterministic)
    first: dict[str, str] = {}
    for d in sorted(facts):
        f = facts[d]
        if f.age is None or not f.sex or not f.pin or not f.dx:
            continue  # the attack is evaluated on patients whose four quasi-identifiers are all known
        first.setdefault(pseud_of[d], d)
    from dataclasses import replace
    full = replace(cfg, qi_include_dx=True)  # the attacker always uses the diagnosis; k-anonymity may not
    rel_rows = [(qi_key(facts[d], level[d], full, rare), facts[d]) for d in first.values()]
    k_rows = [(qi_key(facts[d], level[d], cfg, rare), facts[d]) for d in first.values()]
    raw_rows = [((str(facts[d].age) if facts[d].age is not None else None, facts[d].sex, facts[d].pin, facts[d].dx), facts[d])
                for d in first.values()]
    classes: dict[tuple, list] = defaultdict(list)
    for rel, f in k_rows:
        classes[rel].append(f.dx)
    sizes = [len(v) for v in classes.values()]
    in_small = sum(len(v) for v in classes.values() if len(v) < cfg.k_target)
    total = sum(sizes) or 1
    l_div = min((len({x for x in v if x}) for v in classes.values() if len(v) >= cfg.k_target and any(v)), default=0)
    return {
        "population": "patients with age, sex, PIN and diagnosis all known (%d)" % len(first),
        "attacker_knowledge": "exact age, sex, full PIN, diagnosis",
        "baseline_attack_on_raw_data": _attack(raw_rows, cfg),
        "attack_on_release": _attack(rel_rows, cfg),
        "attack_on_release_knowing_length_of_stay": _attack(rel_rows, cfg, use_los=True),
        "baseline_attack_knowing_length_of_stay": _attack(raw_rows, cfg, use_los=True),
        "k_target": cfg.k_target,
        "k_min": min(sizes) if sizes else 0,
        "fraction_patients_in_classes_below_k": round(in_small / total, 4),
        "equivalence_classes": len(classes),
        "l_diversity_min_distinct_dx_in_k_classes": l_div,
        "levels_used": {str(l): sum(1 for d in first.values() if level[d] == l) for l in sorted({level[d] for d in first.values()})},
    }
