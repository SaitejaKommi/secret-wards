"""Dataset-level name memory.

Pass 1 finds names with strong evidence (label cue, honorific, relation cue, name column).
This pass remembers those tokens for the whole run and flags the same tokens everywhere else,
including lowercase Hinglish and the Devanagari spelling. It is learned from the input at run
time (nothing is hardcoded), deterministic (set semantics, no ordering effects), and it never
learns drug / clinical / common words.
"""
from __future__ import annotations

from typing import Iterable, Optional

import regex as re

from ..contracts import PIIType, Span, Unit
from ..normalize.translit import skeleton
from .base import SpanIndex
from . import lexicon as L

_WORD = re.compile(r"[\p{L}\p{M}]+")
STRONG = 0.85


def _ok(w: str) -> bool:
    if len(w) < 3:
        return False
    if L.is_drug(w) or L.is_clinical(w) or L.is_common(w) or w in L.HI_STOP:
        return False
    return True


class NameMemory:
    def __init__(self) -> None:
        self.lat: set[str] = set()
        self.dev: set[str] = set()
        self.keys: set[str] = set()

    def learn(self, unit: Unit, spans: Iterable[Span]) -> None:
        for s in spans:
            if s.type != PIIType.NAME or s.score < STRONG or s.role == "doctor":
                continue
            for m in _WORD.finditer(unit.original[s.start:s.end]):
                w = m.group()
                if not _ok(w):
                    continue
                if "ऀ" <= w[0] <= "ॿ":
                    self.dev.add(w)
                else:
                    self.lat.add(w.lower())
                k = skeleton(w)
                if len(k) >= 3:
                    self.keys.add(k)

    def find(self, unit: Unit, existing: list[Span]) -> list[Span]:
        out: list[Span] = []
        text = unit.original
        taken = SpanIndex(existing)
        for m in _WORD.finditer(text):
            w = m.group()
            if len(w) < 3:
                continue
            a, b = m.start(), m.end()
            dev = "ऀ" <= w[0] <= "ॿ"
            if dev:
                hit = w in self.dev or (skeleton(w) in self.keys and _ok(w))
            else:
                hit = w.lower() in self.lat and _ok(w)
            if not hit:
                continue
            if taken.overlaps(a, b):
                continue
            out.append(Span(unit.doc_id, unit.field, a, b, PIIType.NAME, "learned", 0.6, ""))
        return out
