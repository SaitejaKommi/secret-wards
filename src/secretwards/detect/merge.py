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


def merge(spans: Sequence[Span], meds: Sequence[tuple[int, int, MedKind]], text: str) -> list[Span]:
    """`meds` are in ORIGINAL coordinates of this unit; `text` is the original unit text."""
    kept: list[Span] = []
    for s in spans:
        if s.type in _TEXT_GUARDED:
            ln = max(1, s.end - s.start)
            cov = sum(_overlap(s.start, s.end, a, b) for a, b, k in meds if k in (MedKind.DRUG, MedKind.LAB, MedKind.VITAL, MedKind.DOSE))
            if cov / ln >= 0.6 and s.score < 0.95:
                continue
        if s.type in _NUMERIC_GUARDED and s.score < 0.9:
            if any(k in (MedKind.LAB, MedKind.VITAL, MedKind.DOSE, MedKind.DURATION) and a <= s.start and s.end <= b for a, b, k in meds):
                continue
        kept.append(s)
    kept.sort(key=lambda s: (-_PRIO[s.type], -(s.end - s.start), -s.score, s.start))
    accepted: list[Span] = []
    for s in kept:
        pieces = [(s.start, s.end)]
        for a in accepted:
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
                accepted.append(Span(s.doc_id, s.field, p0, p1, s.type, s.detector, s.score, s.role))
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
