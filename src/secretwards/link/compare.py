"""Pairwise evidence scoring between two Mentions (Fellegi-Sunter style, hand-set log-odds weights).

Rules of the road
- a name alone NEVER merges: at least one strong, non-name evidence type must agree
- hard vetoes (different ABHA, different DOB, different sex, contradicting names, impossible ages)
  stop a merge no matter what else agrees (an exactly equal ABHA overrides the soft ones)
- shared phones are weak-ish evidence (families share them) and are always checked against the names
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from rapidfuzz.distance import Levenshtein

from ..contracts import Mention
from . import names as N

W_ABHA = 10.0
W_ABHA_NEAR = 7.0
W_MRN = 6.0
W_EMAIL = 5.0
W_INS = 3.0
W_PHONE = 3.0
W_DOB = 4.0
W_REL = 3.5
W_NAME = 4.0
W_PIN = 1.0
W_AGE = 1.0


@dataclass(frozen=True)
class PairResult:
    score: float
    strong: tuple[str, ...]  # non-name evidence types that agree
    veto: str  # "" or reason code


@lru_cache(maxsize=200_000)
def _tok(tokens: tuple[str, ...]):
    return N.parse(tokens)


def _birth_year(m: Mention) -> int | None:
    if m.dob:
        return int(m.dob[:4])
    if m.age is not None and m.ref_year is not None:
        return m.ref_year - m.age
    return None


def evaluate(a: Mention, b: Mention) -> PairResult:
    score = 0.0
    strong: list[str] = []
    veto = ""
    abha_equal = False

    # --- identifiers
    if a.abha and b.abha:
        best = min(Levenshtein.distance(x, y) for x in a.abha for y in b.abha)
        if best == 0:
            score += W_ABHA
            strong.append("abha")
            abha_equal = True
        elif best <= 1:
            score += W_ABHA_NEAR
            strong.append("abha")
            abha_equal = True
        else:
            veto = "abha_differs"
    if set(a.mrn) & set(b.mrn) and a.hospital == b.hospital:
        score += W_MRN
        strong.append("mrn")
    if set(a.emails) & set(b.emails):
        score += W_EMAIL
        strong.append("email")
    if set(a.insurance) & set(b.insurance):
        score += W_INS
        strong.append("insurance")
    if set(a.phones) & set(b.phones):
        score += W_PHONE
        strong.append("phone")
    # --- dates of birth, age
    if a.dob and b.dob:
        if a.dob == b.dob:
            score += W_DOB
            strong.append("dob")
        elif not veto:
            veto = "dob_differs"
    ba, bb = _birth_year(a), _birth_year(b)
    if ba is not None and bb is not None:
        d = abs(ba - bb)
        if d <= 1:
            score += W_AGE
        elif d >= 4:
            score -= 4.0  # soft: ages are often mis-extracted, but father/son pairs must not merge
    elif a.age is not None and b.age is not None and abs(a.age - b.age) >= 25:
        score -= 4.0
    # --- sex
    if a.sex and b.sex:
        if a.sex != b.sex and not veto:
            veto = "sex_differs"
        elif a.sex == b.sex:
            score += 0.3
    # --- names
    ta, tb = _tok(a.name_tokens), _tok(b.name_tokens)
    sim, conflict = N.compare(ta, tb)
    if ta and tb:
        n_inf = min(sum(1 for t in ta if not t.initial), sum(1 for t in tb if not t.initial))
        score += W_NAME * sim * (1.0 if n_inf >= 2 else 0.6)  # a one-token name says less
        if conflict == 2 and not veto:
            veto = "name_conflict"
        elif conflict == 1:
            score -= 2.0
    # --- relative (father / husband) names
    rel_best, rel_conflict = 0.0, 0
    for ra in a.rel_tokens:
        for rb in b.rel_tokens:
            s2, c2 = N.compare(_tok(ra), _tok(rb))
            if s2 > rel_best:
                rel_best, rel_conflict = s2, c2
    if a.rel_tokens and b.rel_tokens:
        if rel_best >= 0.7 and rel_conflict == 0 and N.informative(_tok(a.rel_tokens[0])):
            score += W_REL
            strong.append("rel")
        elif rel_conflict == 2:
            score -= 3.0
    # --- location
    pin_equal = bool(a.pin and b.pin and a.pin == b.pin)
    if pin_equal:
        score += W_PIN
    # a father's / husband's name is shared by siblings and by namesakes: it only counts as strong
    # evidence when a compatible birth year or the same DOB backs it up (a shared city is not enough: namesakes live together)
    if strong == ["rel"]:
        support = (ba is not None and bb is not None and abs(ba - bb) <= 1) or bool(a.dob and a.dob == b.dob)
        if not support:
            strong = []
    if abha_equal and veto in ("sex_differs", "age_incompatible", "dob_differs", "name_conflict"):
        veto = ""  # an exactly matching national id outranks soft data-entry errors
    return PairResult(round(score, 3), tuple(strong), veto)
