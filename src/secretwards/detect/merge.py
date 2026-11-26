"""Combine spans from all detectors into one non-overlapping list.

Rules
- precedence by type (strict validators first), then longer span, then score
- lower-precedence spans are trimmed against accepted ones (a name inside an address disappears)
- adjacent same-type spans are joined (First + Last name, address pieces)
- medical guard: NAME/ADDRESS spans that are mostly a drug / lab / vital are dropped;
  numeric ID / PIN / DATE hits inside lab, dose or vital text are dropped;
  validated phones, emails and ABHA numbers are never dropped by the guard.
"""
from __future__ import annotations

import bisect
from typing import Sequence

from ..contracts import MedKind, PIIType, Span

_PRIO = {
    PIIType.EMAIL: 100, PIIType.ABHA: 90, PIIType.INSURANCE: 85, PIIType.MRN: 80, PIIType.PHONE: 75,
    PIIType.ID: 70, PIIType.DATE: 66, PIIType.ADDRESS: 60, PIIType.PINCODE: 58, PIIType.NAME: 50,
}
_NUMERIC_GUARDED = {PIIType.ID, PIIType.PINCODE, PIIType.DATE, PIIType.MRN}
_TEXT_GUARDED = {PIIType.NAME, PIIType.ADDRESS}


def _overlap(a0: int, a1: int, b0: int, b1: int) -> int:
    return max(0, min(a1, b1) - max(a0, b0))


def _index(intervals: list[tuple[int, int]]) -> tuple[list[int], list[int], list[int]]:
    """Intervals sorted by start plus a running maximum of their ends (for fast 'does anything overlap / contain' queries)."""
    intervals = sorted(intervals)
    starts = [a for a, _ in intervals]
    pmax, m = [], -1
    for _, e in intervals:
        m = max(m, e)
        pmax.append(m)
    return starts, pmax, [e for _, e in intervals]


def merge(spans: Sequence[Span], meds: Sequence[tuple[int, int, MedKind]], text: str) -> list[Span]:
    """`meds` are in ORIGINAL coordinates of this unit; `text` is the original unit text.
    Linear-ish in the number of spans: every lookup is a binary search (a 4 MB note used to take hours)."""
    text_kinds = (MedKind.DRUG, MedKind.LAB, MedKind.VITAL, MedKind.DOSE)
    num_kinds = (MedKind.LAB, MedKind.VITAL, MedKind.DOSE, MedKind.DURATION)
    t_starts, t_pmax, t_ends = _index([(a, b) for a, b, k in meds if k in text_kinds])
    n_starts, n_pmax, _n_ends = _index([(a, b) for a, b, k in meds if k in num_kinds])

    def text_cover(s0: int, s1: int) -> int:
        hi = bisect.bisect_left(t_starts, s1)  # meds starting before the span ends
        cov, i = 0, hi - 1
        while i >= 0 and t_pmax[i] > s0:
            cov += _overlap(s0, s1, t_starts[i], t_ends[i])
            i -= 1
        return cov

    def inside_numeric(s0: int, s1: int) -> bool:
        i = bisect.bisect_right(n_starts, s0) - 1
        return i >= 0 and n_pmax[i] >= s1

    kept: list[Span] = []
    for s in spans:
        if s.type in _TEXT_GUARDED:
            ln = max(1, s.end - s.start)
            if text_cover(s.start, s.end) / ln >= 0.6 and s.score < 0.95:
                continue
        if s.type in _NUMERIC_GUARDED and s.score < 0.9 and inside_numeric(s.start, s.end):
            continue
        kept.append(s)
    kept.sort(key=lambda s: (-_PRIO[s.type], -(s.end - s.start), -s.score, s.start))
    # accepted spans never overlap each other, so they stay sorted by start AND by end
    a_starts: list[int] = []
    a_ends: list[int] = []
    a_spans: list[Span] = []
    for s in kept:
        lo = bisect.bisect_right(a_ends, s.start)  # first accepted span that ends after s starts
        hi = bisect.bisect_left(a_starts, s.end)  # accepted spans starting before s ends
        pieces = [(s.start, s.end)]
        if hi > lo:
            for a in a_spans[lo:hi]:
                nxt = []
                for p0, p1 in pieces:
                    if _overlap(p0, p1, a.start, a.end) == 0:
                        nxt.append((p0, p1))
                        continue
                    if s.type in (PIIType.NAME, PIIType.ADDRESS):  # trimmable types
                        if p0 < a.start:
                            nxt.append((p0, a.start))
                        if p1 > a.end:
                            nxt.append((a.end, p1))
                    # strict types are dropped on conflict
                pieces = nxt
        for p0, p1 in pieces:
            if p1 - p0 >= 2:
                i = bisect.bisect_left(a_starts, p0)
                a_starts.insert(i, p0)
                a_ends.insert(i, p1)
                a_spans.insert(i, Span(s.doc_id, s.field, p0, p1, s.type, s.detector, s.score, s.role))
    accepted = a_spans
    accepted.sort(key=lambda s: (s.start, s.end))
    # join adjacent same-type spans
    out: list[Span] = []
    for s in accepted:
        if out:
            p = out[-1]
            gap = text[p.end:s.start]
            same_role = p.role == s.role or not p.role or not s.role
            joinable = (
                p.type == s.type == PIIType.NAME and same_role and gap.strip(" ") == "" and "\n" not in gap and len(gap) <= 2
            ) or (
                p.type == s.type == PIIType.ADDRESS and len(gap) <= 3 and gap.strip(" ,.-") == ""
            )
            if joinable:
                out[-1] = Span(p.doc_id, p.field, p.start, s.end, p.type, p.detector, max(p.score, s.score), p.role or s.role)
                continue
        out.append(s)
    return out
