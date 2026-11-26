"""Shared helpers for detectors: collecting spans on normalized text and mapping them back."""
from __future__ import annotations

from ..contracts import PIIType, Span, Unit


class Collector:
    """Accumulate matches in NORMALIZED coordinates, emit Spans in ORIGINAL coordinates."""

    def __init__(self, unit: Unit, detector: str):
        self.unit = unit
        self.detector = detector
        self.spans: list[Span] = []

    def add(self, s: int, e: int, typ: PIIType, score: float, role: str = "") -> None:
        n = self.unit.norm
        while e > s and n.text[e - 1] in " \n":
            e -= 1
        while s < e and n.text[s] in " \n":
            s += 1
        if e <= s:
            return
        a, b = n.to_orig(s, e)
        self.spans.append(Span(self.unit.doc_id, self.unit.field, a, b, typ, self.detector, score, role))
