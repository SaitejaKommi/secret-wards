"""Cross-script, order-free, initial-aware name comparison.

A name becomes a list of Tok(key, initial, common). `key` is the phonetic skeleton
(script independent), `common` marks very frequent name parts (Kumar, Singh, Devi ...) that carry
little identity. compare() returns a similarity in [0, 1] and a conflict level:
  0 none      every full token of the shorter name is explained by the other name
  1 soft      some full tokens disagree (different surname, maybe a married name)
  2 hard      both names have full tokens and none of them match: different people
"""
from __future__ import annotations

from dataclasses import dataclass

import regex as re
from rapidfuzz import fuzz

from ..normalize.translit import is_devanagari, skeleton, to_latin

_HON = frozenset("mr mrs ms miss shri sh smt sri master kumari km late baby dr श्री श्रीमती श्रीमान कुमारी स्व डॉ".split())
_KIN = frozenset("bhaiya bhai didi ji sahab saab sahib babu uncle aunty bhabhi भैया भाई दीदी जी साहब".split())
_COMMON_RAW = "kumar kumari singh devi lal prasad chand ram shri begum bai rani kaur ben bhai das".split()
COMMON_KEYS = frozenset(skeleton(w) for w in _COMMON_RAW)
_TOKEN = re.compile(r"[\p{L}\p{M}]+")


@dataclass(frozen=True)
class Tok:
    key: str
    first: str  # first Latin letter of the romanized token
    initial: bool
    common: bool
    latin: str


def parse(tokens) -> list[Tok]:
    out: list[Tok] = []
    for raw in tokens:
        for w in _TOKEN.findall(raw):
            lw = w.lower()
            if lw in _HON or lw in _KIN or w in _HON or w in _KIN:
                continue
            lat = to_latin(w) if is_devanagari(w) else lw
            if not lat:
                continue
            key = skeleton(w)
            initial = len(w) == 1 or (len(w) == 2 and is_devanagari(w))
            if not key and not initial:
                continue
            out.append(Tok(key or lat[:1], lat[:1], initial, key in COMMON_KEYS, lat))
    return out


def _pair(a: Tok, b: Tok) -> float:
    if a.initial and b.initial:
        return 0.35 if a.first == b.first else 0.0
    if a.initial or b.initial:
        return 0.5 if a.first == b.first else 0.0
    if a.key == b.key:
        return 1.0
    r = max(fuzz.ratio(a.key, b.key), fuzz.ratio(a.latin, b.latin) - 5) / 100
    if r >= 0.85 and min(len(a.key), len(b.key)) >= 3:
        return round(0.9 * r, 3)  # typo / OCR variant
    r2 = fuzz.ratio(a.latin, b.latin) / 100
    if r2 >= 0.7 and a.first == b.first and min(len(a.latin), len(b.latin)) >= 4:
        return round(0.7 * r2, 3)  # likely OCR damage, weak
    return 0.0


def _weight(t: Tok) -> float:
    return 0.35 if t.common else (0.5 if t.initial else 1.0)


def compare(a: list[Tok], b: list[Tok]) -> tuple[float, int]:
    if not a or not b:
        return 0.0, 0
    pairs = sorted(((_pair(x, y), i, j) for i, x in enumerate(a) for j, y in enumerate(b)), key=lambda t: (-t[0], t[1], t[2]))
    used_a: set[int] = set()
    used_b: set[int] = set()
    got = 0.0
    matched_nc = 0
    soft_nc = 0  # an initial explained a full name ("Z" ~ "Zaidi")
    for s, i, j in pairs:
        if s <= 0 or i in used_a or j in used_b:
            continue
        used_a.add(i)
        used_b.add(j)
        got += s * min(_weight(a[i]), _weight(b[j]))
        if s >= 0.5 and not a[i].initial and not b[j].initial and not a[i].common and not b[j].common:
            matched_nc += 1
        elif (a[i].initial != b[j].initial) and not (a[i].common or b[j].common) and s > 0:
            soft_nc += 1
    wa, wb = sum(_weight(t) for t in a), sum(_weight(t) for t in b)
    sim = round(min(1.0, got / max(1e-9, min(wa, wb))), 3)
    nc_a = [i for i, t in enumerate(a) if not t.initial and not t.common]
    nc_b = [j for j, t in enumerate(b) if not t.initial and not t.common]
    un_nc_a = [i for i in nc_a if i not in used_a]
    un_nc_b = [j for j in nc_b if j not in used_b]
    un_init_a = [i for i, t in enumerate(a) if t.initial and i not in used_a]
    un_init_b = [j for j, t in enumerate(b) if t.initial and j not in used_b]
    conflict = 0
    if nc_a and nc_b:
        if matched_nc == 0:
            # a lone token (or an initial explaining one) may just be a different part of the same name
            conflict = 1 if (soft_nc or len(a) == 1 or len(b) == 1) else 2  # e.g. Rajesh Kumar vs Suresh Verma -> 2
        elif un_nc_a and un_nc_b:
            conflict = 1  # e.g. Rajesh Sharma vs Rajesh Verma
    # an initial that fits nothing on the other side while that side has an unexplained full name
    if (un_init_a and un_nc_b) or (un_init_b and un_nc_a):
        conflict = max(conflict, 2 if matched_nc == 0 else 1)
    return sim, conflict


def informative(a: list[Tok]) -> bool:
    """True if the name has at least one full non-common token (usable as identity evidence)."""
    return any(not t.initial and not t.common for t in a)
