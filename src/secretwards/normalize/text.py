"""Unicode normalization with an offset map back to the original text.

Match on normalized text, redact on original text. Every normalized char knows the
[start, end) of the original chars it came from, so spans can be mapped back.

What it does:  NFKC per char, drop zero-width chars, Indic digits -> ASCII digits,
typographic dashes/quotes -> ASCII, whitespace runs -> single space.
"""
from __future__ import annotations

import unicodedata
from functools import lru_cache

import regex as _re

from ..contracts import NormText

_ZERO_WIDTH = {0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0x00AD, 0x200E, 0x200F}
_PUNCT = {
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "−": "-",
    "‘": "'", "’": "'", "‚": "'", "“": '"', "”": '"',
    " ": " ", " ": " ", " ": " ",
}


_NEEDS_WORK = ("  ", "\t", "\r", " \n", "\n ", "\f", "\v")


@lru_cache(maxsize=8192)
def normalize(text: str) -> NormText:
    """Cached; the ASCII fast path covers most English / Hinglish cells without a per-char loop."""
    if text.isascii() and text[:1] != " " and not any(x in text for x in _NEEDS_WORK):
        n = len(text)
        return NormText(text, tuple(range(n)), tuple(range(1, n + 1)))
    return _normalize_slow(text)


def _normalize_slow(text: str) -> NormText:
    out: list[str] = []
    starts: list[int] = []
    ends: list[int] = []
    prev_space = True  # leading whitespace is dropped
    for i, ch in enumerate(text):
        if ord(ch) in _ZERO_WIDTH:
            continue
        ch = _PUNCT.get(ch, ch)
        for c in unicodedata.normalize("NFKC", ch):
            if unicodedata.category(c) == "Nd":
                d = unicodedata.decimal(c, None)
                if d is not None:
                    c = str(d)
            if c.isspace() and c not in "\n":
                if prev_space:
                    if out and out[-1] == " ":
                        ends[-1] = i + 1
                    continue
                out.append(" ")
                starts.append(i)
                ends.append(i + 1)
                prev_space = True
                continue
            if c == "\n":
                if out and out[-1] == " ":  # no trailing space before newline
                    out.pop(); starts.pop(); ends.pop()
                out.append("\n")
                starts.append(i)
                ends.append(i + 1)
                prev_space = True
                continue
            out.append(c)
            starts.append(i)
            ends.append(i + 1)
            prev_space = False
    return NormText("".join(out), tuple(starts), tuple(ends))


_CONFUSABLE = {"O": "0", "o": "0", "l": "1", "I": "1", "|": "1", "S": "5", "B": "8", "Z": "2"}


_DIGIT = _re.compile(r"\d")


@lru_cache(maxsize=8192)
def ocr_digit_view(norm: str) -> str:
    """Same-length copy where OCR letter/digit confusions inside digit-heavy tokens
    are mapped to digits (98765432lO -> 9876543210). Offsets are unchanged."""
    if not _DIGIT.search(norm):
        return norm
    out = list(norm)
    i, n = 0, len(norm)
    while i < n:
        if norm[i].isspace():
            i += 1
            continue
        j = i
        while j < n and not norm[j].isspace():
            j += 1
        tok = norm[i:j]
        digits = sum(c.isdigit() for c in tok)
        conf = sum(c in _CONFUSABLE for c in tok)
        sep = sum(c in "+-.()/," for c in tok)
        if digits >= 4 and digits + conf + sep >= 0.8 * len(tok) and conf <= max(2, digits // 3):
            for k in range(i, j):
                if norm[k] in _CONFUSABLE:
                    out[k] = _CONFUSABLE[norm[k]]
        i = j
    return "".join(out)
