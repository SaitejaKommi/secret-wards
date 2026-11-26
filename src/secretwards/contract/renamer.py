"""Hidden channels: file and folder names, CSV headers and JSON keys can themselves hold personal data.

A name is replaced ONLY when it holds PII (the contract says: rename a header or file only if it contains PII).
The replacement is a keyed hash, identical for identical input, so repeated keys / headers stay consistent.
For file names the new path is declared in report.json under the file's input_sha256.
"""
from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Sequence

from ..contracts import Detector
from ..detect import detect_unit
from ..detect import lexicon as L
from ..pipeline import make_unit
from ..security.keys import Keys, hmac_hex

_SPLIT = re.compile(r"[_\-\s.()\[\]]+")
_DIGITS = re.compile(r"\d{6,}")
_CHUNK = re.compile(r"[A-Za-z0-9]+(?:[-/][A-Za-z0-9]+)*")
_IDLIKE = re.compile(r"[A-Za-z]{1,6}[-/]?\d{5,}")
_SAFE_WORDS = (L.HEADER_WORDS | L.CLINICAL_WORDS | L.COMMON_WORDS)


class Renamer:
    def __init__(self, keys: Keys, detectors: Sequence[Detector], memory=None):
        self.keys = keys
        self.detectors = detectors
        self.memory = memory  # names learned from the data itself (NameMemory): a file called after a patient is renamed
        self._cache: dict[str, bool] = {}

    # ---- does this short string hold personal data?
    def _detected(self, text: str) -> bool:
        hit = self._cache.get(text)
        if hit is None:
            spans, _ = detect_unit(make_unit("x", None, text), self.detectors)
            hit = any(s.role != "doctor" for s in spans)
            self._cache[text] = hit
        return hit

    def holds_pii(self, text: str, *, filename: bool = False) -> bool:
        if not text.strip():
            return False
        if _DIGITS.search(text.replace(" ", "")) or _IDLIKE.search(text):
            return True
        for chunk in _CHUNK.findall(text):  # ids such as IP-26-00130: letters plus at least five digits, joined by - or /
            if sum(c.isdigit() for c in chunk) >= 5 and any(c.isalpha() for c in chunk):
                return True
        spaced = _SPLIT.sub(" ", text)
        if self._detected(text) or self._detected(spaced):
            return True
        if self.memory is not None and self.memory.find(make_unit("x", None, re.sub(r"(?<=[a-z])(?=[A-Z])", " ", spaced)), []):
            return True
        if filename:
            # a Title-case word that is not ordinary document vocabulary is probably a person's name
            for tok in _SPLIT.split(text):
                if len(tok) >= 3 and tok[0].isupper() and tok[1:].islower() and tok.lower() not in _SAFE_WORDS:
                    return True
        return False

    def token(self, raw: str, kind: str) -> str:
        return f"{kind}_{hmac_hex(self.keys.docid, 'name', raw, n=8)}"

    # ---- headers and keys
    def header(self, h: str) -> str:
        return self.token(h, "col") if self.holds_pii(h) else h

    def key(self, k: str) -> str:
        return self.token(k, "key") if self.holds_pii(k) else k

    # ---- paths
    def path(self, rel: str) -> str:
        """Return the output path (relative, POSIX). Each component is kept unless it holds PII."""
        parts = PurePosixPath(rel).parts
        out = []
        for i, comp in enumerate(parts):
            last = i == len(parts) - 1
            if last:
                suffix = PurePosixPath(comp).suffix
                stem = comp[: len(comp) - len(suffix)] if suffix else comp
                out.append(self.token(comp, "f") + suffix if self.holds_pii(stem, filename=True) else comp)
            else:
                out.append(self.token(comp, "d") if self.holds_pii(comp, filename=True) else comp)
        return "/".join(out)
