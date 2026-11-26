"""A text cell that records gold PII / medical spans while it is being built."""
from __future__ import annotations

import random

_CONFUSE = {"O": "0", "0": "O", "l": "1", "1": "l", "I": "l", "S": "5", "5": "S", "B": "8", "a": "o", "e": "c"}
_RN = {"m": "rn"}


def ocr_noise(s: str, rng: random.Random, rate: float) -> str:
    if rate <= 0:
        return s
    out = []
    for ch in s:
        if rng.random() < rate:
            r = rng.random()
            if r < 0.6 and ch in _CONFUSE:
                out.append(_CONFUSE[ch])
                continue
            if r < 0.75 and ch in _RN:
                out.append(_RN[ch])
                continue
            if r < 0.9 and ch.isalpha():
                continue  # dropped char
        out.append(ch)
    return "".join(out)


class Cell:
    def __init__(self, rng: random.Random, noise: float = 0.0):
        self.rng = rng
        self.noise = noise
        self._parts: list[str] = []
        self._n = 0
        self.pii: list[dict] = []
        self.med: list[dict] = []
        self.native = None  # optional non-string JSON value (e.g. int age)

    @property
    def text(self) -> str:
        return "".join(self._parts)

    def lit(self, s: str, noisy: bool = True) -> "Cell":
        if noisy and self.noise:
            s = ocr_noise(s, self.rng, self.noise)
        self._parts.append(s)
        self._n += len(s)
        return self

    def P(self, typ: str, s: str, role: str = "") -> "Cell":
        """Add a PII value (gold-labelled)."""
        if self.noise:
            s = ocr_noise(s, self.rng, self.noise * 0.7)
        self.pii.append({"start": self._n, "end": self._n + len(s), "type": typ, "text": s, "role": role})
        self._parts.append(s)
        self._n += len(s)
        return self

    def M(self, kind: str, s: str) -> "Cell":
        """Add a medical value that must survive de-identification."""
        if self.noise:
            s = ocr_noise(s, self.rng, self.noise * 0.5)
        self.med.append({"start": self._n, "end": self._n + len(s), "kind": kind, "text": s})
        self._parts.append(s)
        self._n += len(s)
        return self
