"""Canonical diagnosis key and diagnosis-entry extent.

Why: the privacy layer groups records by diagnosis (a quasi-identifier) and suppresses diagnoses held by very
few patients. Grouping on raw text fragments ("gout" vs "gout unspecified m10 9", Hindi vs English names of
the same disease) made common diseases look rare, so they were suppressed and the medical value was lost.

- `dx_key(text)`: the ICD-10 code when one is written (any language around it: "माइग्रेन (G43.9)" and
  "Migraine, unspecified (G43.9)" share "G43.9"); otherwise the normalized text.
- `dx_entry_end(text, start)`: where one diagnosis entry ends: at ';', '|', a newline, a sentence end ('. ') or the
  end; a bracketed ICD code closes the entry ("Cushing's syndrome, unspecified (E24.9)" stays whole, "Gout, unspecified (M10.9)"
  keeps its comma); without a code the first comma ends it ("Dx: Viral fever, Tab Cetirizine 10 mg 0-0-1" keeps the drug).
"""
from __future__ import annotations

import regex as re

from ..normalize.text import normalize

# ICD-10: letter, 2 digits, optional .digits (B26, G43.9, U07.1); not inside a longer token
ICD10 = re.compile(r"(?<![A-Za-z0-9])([A-Z]\d{2}(?:\.\d{1,4})?)(?![A-Za-z0-9])")
_ENTRY_END = re.compile(r"[;|\n।]|\.(?=\s|$)")  # entry list separators, or a sentence end (not the dot in G43.9)


def dx_key(text: str) -> str:
    """Canonical grouping key for one diagnosis entry."""
    n = normalize(text).text
    m = ICD10.search(n)
    if m:
        return m.group(1).upper()
    s = re.sub(r"[^\p{L}\p{M}\d ]+", " ", n.lower())
    return re.sub(r"\s+", " ", s).strip()


_CODE_IN_BRACKETS = re.compile(r"\(\s*[A-Z]\d{2}(?:\.\d{1,4})?\s*\)")


def dx_entry_end(text: str, start: int) -> int:
    """End offset (exclusive) of the diagnosis entry starting at `start` in `text`, trailing spaces trimmed.

    The entry is cut at ';', '|', a newline or a sentence end. Inside that, a bracketed ICD code closes the entry
    ("Gout, unspecified (M10.9)"); without one, the first comma does ("Viral fever, Tab Cetirizine 10 mg" keeps the drug).
    """
    m = _ENTRY_END.search(text, start)
    end = m.start() if m else len(text)
    code = _CODE_IN_BRACKETS.search(text, start, end)
    if code:
        end = code.end()
    else:
        comma = text.find(",", start, end)
        if comma >= 0:
            end = comma
    while end > start and text[end - 1] in " \t\r":
        end -= 1
    return end
