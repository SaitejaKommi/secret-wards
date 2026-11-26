"""Constrained agglomerative clustering: no transitive over-merging.

Accepted pairs are processed best-first. Two clusters merge only if NO cross pair of members has a
hard veto (so A-B and B-C evidence cannot glue together an A and C that contradict each other).
"""
from __future__ import annotations

from typing import Sequence

from ..config import Config
from ..contracts import Cluster, Mention
from ..privacy.pseudonym import make_pseudonym
from ..security.keys import Keys
from .blocking import candidate_pairs
from .compare import PairResult, evaluate


def cluster_mentions(mentions: Sequence[Mention], keys: Keys, cfg: Config) -> list[Cluster]:
    ms = sorted(mentions, key=lambda m: m.doc_id)
    n = len(ms)
    cache: dict[tuple[int, int], PairResult] = {}

    def ev(i: int, j: int) -> PairResult:
        if i > j:
            i, j = j, i
        r = cache.get((i, j))
        if r is None:
            r = cache[(i, j)] = evaluate(ms[i], ms[j])
        return r

    pairs, _skipped = candidate_pairs(ms, cfg.block_cap)
    edges = []
    for i, j in pairs:
        r = ev(i, j)
        if not r.veto and r.strong and r.score >= cfg.link_threshold:
            edges.append((-r.score, ms[i].doc_id, ms[j].doc_id, i, j))
    edges.sort()

    parent = list(range(n))
    members: dict[int, list[int]] = {i: [i] for i in range(n)}
    evidence: dict[int, set[str]] = {i: set() for i in range(n)}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for _neg, _a, _b, i, j in edges:
        ri, rj = find(i), find(j)
        if ri == rj:
            continue
        if any(ev(x, y).veto for x in members[ri] for y in members[rj]):
            continue
        if len(members[ri]) < len(members[rj]):
            ri, rj = rj, ri
        parent[rj] = ri
        members[ri].extend(members[rj])
        del members[rj]
        evidence[ri] |= evidence.pop(rj) | set(ev(i, j).strong)

    groups = sorted(members.values(), key=lambda g: min(ms[x].doc_id for x in g))
    anchors = [_anchor(ms, g) for g in groups]
    # two different clusters must never share a pseudonym (e.g. a family phone): disambiguate
    seen: dict[str, int] = {}
    for a in anchors:
        seen[a] = seen.get(a, 0) + 1
    out = []
    for g, a in zip(groups, anchors):
        if seen[a] > 1:
            a = a + "|" + min(ms[x].doc_id for x in g)
        ev_codes = tuple(sorted(evidence.get(find(g[0]), set()))) or (("singleton",) if len(g) == 1 else ("merged",))
        out.append(Cluster(make_pseudonym(keys, a), tuple(sorted(ms[x].doc_id for x in g)), ev_codes))
    return out


def _anchor(ms: Sequence[Mention], g: list[int]) -> str:
    """Deterministic, as stable as the data allows: strongest identifier present in the cluster."""
    abha = sorted({a for x in g for a in ms[x].abha})
    if abha:
        return "abha:" + abha[0]
    mrn = sorted({f"{ms[x].hospital}:{r}" for x in g for r in ms[x].mrn})
    if mrn:
        return "mrn:" + mrn[0]
    em = sorted({e for x in g for e in ms[x].emails})
    if em:
        return "email:" + em[0]
    ins = sorted({i for x in g for i in ms[x].insurance})
    if ins:
        return "ins:" + ins[0]
    ph = sorted({p for x in g for p in ms[x].phones})
    if ph:
        return "phone:" + ph[0]
    return "doc:" + min(ms[x].doc_id for x in g)
