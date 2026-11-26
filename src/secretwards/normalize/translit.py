"""Devanagari <-> Latin helpers for matching names across scripts. Deterministic, table-driven.

`to_latin(token)`  rough romanization (Devanagari -> Latin, with schwa deletion).
`skeleton(token)`  a script-independent phonetic key: lowercase Latin, aspirates and
                   sibilants folded, vowels dropped (a leading vowel is kept as '*'),
                   doubles collapsed. Rajesh / राजेश -> 'rjs'; Mohammad / Mohd / मोहम्मद
                   all map to 'mhmd' via a small alias table.
This is a matching key, not a spelling. Different words can share a key; callers must
combine it with other evidence (see link/).
"""
from __future__ import annotations

import re

_VOWELS = {
    "अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo", "ऋ": "ri",
    "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au", "ऑ": "o", "ऍ": "e",
}
_MATRAS = {
    "ा": "aa", "ि": "i", "ी": "ee", "ु": "u", "ू": "oo", "ृ": "ri", "े": "e", "ै": "ai",
    "ो": "o", "ौ": "au", "ॉ": "o", "ॅ": "e",
}
_CONS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n",
    "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "n",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "व": "v", "श": "sh", "ष": "sh", "स": "s", "ह": "h",
    "ळ": "l", "क़": "k", "ख़": "kh", "ग़": "g", "ज़": "z", "ड़": "r", "ढ़": "rh", "फ़": "f",
    "य़": "y",
}
_HALANT = "्"
_NUKTA = "़"
_ANUSVARA = {"ं": "n", "ँ": "n", "ः": "h"}
_DEV_RANGE = re.compile(r"[ऀ-ॿ]")


def is_devanagari(s: str) -> bool:
    return bool(_DEV_RANGE.search(s))


def to_latin(word: str) -> str:
    """Romanize one Devanagari word (other chars pass through, lowercased)."""
    # fold precomposed nukta letters first
    word = word.replace("क़", "क़").replace("ख़", "ख़").replace("ग़", "ग़")
    word = word.replace("ज़", "ज़").replace("ड़", "ड़").replace("ढ़", "ढ़").replace("फ़", "फ़")
    word = word.replace("य़", "य़")
    # Build (kind, text) units so we can apply schwa deletion afterwards.
    units: list[list] = []  # [text, has_inherent_a]
    i, n = 0, len(word)
    while i < n:
        ch = word[i]
        two = word[i : i + 2]
        if two in _CONS:
            base, i = _CONS[two], i + 2
        elif ch in _CONS:
            base, i = _CONS[ch], i + 1
        else:
            base = None
        if base is not None:
            if i < n and word[i] == _NUKTA:
                i += 1
            if i < n and word[i] == _HALANT:
                units.append([base, False])
                i += 1
            elif i < n and word[i] in _MATRAS:
                units.append([base + _MATRAS[word[i]], False])
                i += 1
            else:
                units.append([base + "a", True])
            continue
        if ch in _VOWELS:
            units.append([_VOWELS[ch], False])
        elif ch in _ANUSVARA:
            units.append([_ANUSVARA[ch], False])
        elif ch in (_NUKTA, _HALANT):
            pass
        elif "ऀ" <= ch <= "ॿ":
            pass  # danda, om, etc.
        else:
            units.append([ch.lower(), False])
        i += 1
    # schwa deletion: word-final, and medial in V C a C V patterns (Hindi-style)
    for idx in range(len(units) - 1, -1, -1):
        if not units[idx][1]:
            continue
        last = idx == len(units) - 1
        if last and idx > 0:
            units[idx][0] = units[idx][0][:-1]
            continue
        if 0 < idx < len(units) - 1:
            prev_has_vowel = any(c in "aeiou" for c in units[idx - 1][0])
            nxt = units[idx + 1][0]
            if prev_has_vowel and nxt and nxt[-1] in "aeiou" and nxt[0] not in "aeiou":
                units[idx][0] = units[idx][0][:-1]
    return "".join(u[0] for u in units)


_ALIASES = {"md": "mhmd", "mhd": "mhmd", "mhmmd": "mhmd", "mohd": "mhmd"}
_DIGRAPHS = (
    ("chh", "c"), ("ch", "c"), ("sh", "s"), ("kh", "k"), ("gh", "g"), ("th", "t"),
    ("dh", "d"), ("ph", "p"), ("bh", "b"), ("jh", "j"), ("ck", "k"), ("ny", "n"),
    ("ee", "i"), ("oo", "u"), ("aa", "a"), ("ai", "a"), ("au", "a"),
)


def skeleton(token: str) -> str:
    """Script-independent phonetic key for one name token."""
    s = to_latin(token) if is_devanagari(token) else token
    s = s.lower()
    s = re.sub(r"[^a-z]", "", s)
    if not s:
        return ""
    s = s.replace("nh", "ng")  # anusvara+ha (सिंह) vs Latin 'singh'
    for a, b in _DIGRAPHS:
        s = s.replace(a, b)
    s = s.replace("w", "v").replace("z", "j").replace("f", "p").replace("q", "k").replace("x", "ks")
    s = re.sub(r"c(?!h)", "k", s)
    out: list[str] = []
    for idx, c in enumerate(s):
        if c in "aeiou" or (c == "y" and idx > 0):
            if idx == 0:
                out.append("*")
            continue
        if out and out[-1] == c:
            continue
        out.append(c)
    key = "".join(out)
    # an 'h' that only follows a vowel and ends the word is silent in most spellings
    return _ALIASES.get(key, key)
