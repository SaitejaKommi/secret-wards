"""Candidate generation. Because a merge always needs a strong non-name agreement, blocking only
needs those keys; name-only blocks are not required (and would be quadratic)."""
from __future__ import annotations

from collections import defaultdict
from typing import Sequence

from ..contracts import Mention
from . import names as N
from .compare import _tok

ID_PREFIXES = ("a:", "a8:", "a6:", "e:", "m:", "i:")


def block_keys(m: Mention) -> list[str]:
    keys: list[str] = []
    for p in m.phones:
        keys.append("p:" + p)
    for e in m.emails:
        keys.append("e:" + e)
    for a in m.abha:
        keys += ["a:" + a, "a8:" + a[:8], "a6:" + a[-6:]]
    for i in m.insurance:
        keys.append("i:" + i)
    for r in m.mrn:
        keys.append(f"m:{m.hospital}:{r}")
    nks = sorted({t.key for t in _tok(m.name_tokens) if not t.initial and not t.common and t.key})
    if m.dob:
        keys += [f"d:{m.dob}:{k}" for k in nks] or [f"d:{m.dob}"]
    for rel in m.rel_tokens:
        rks = sorted({t.key for t in _tok(rel) if not t.initial and not t.common and t.key})
        keys += [f"r:{rk}:{nk}" for rk in rks for nk in nks]
    return keys


def candidate_pairs(mentions: Sequence[Mention], cap: int) -> tuple[list[tuple[int, int]], int]:
    blocks: dict[str, list[int]] = defaultdict(list)
    for i, m in enumerate(mentions):
        for k in set(block_keys(m)):
            blocks[k].append(i)
    pairs: set[tuple[int, int]] = set()
    skipped = 0
    for k in sorted(blocks):
        ms = blocks[k]
        if len(ms) < 2:
            continue
        if len(ms) > cap and not k.startswith(("a:", "e:")):
            skipped += 1
            continue
        for x in range(len(ms)):
            for y in range(x + 1, len(ms)):
                pairs.add((ms[x], ms[y]))
    return sorted(pairs), skipped
