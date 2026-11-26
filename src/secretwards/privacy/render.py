"""Turn spans into redacted text. Dates are shifted (same format), everything else gets a placeholder."""
from __future__ import annotations

from typing import Sequence

from ..contracts import ID_TYPES, PIIType, Span
from ..normalize.dates import find_dates, render as render_date, shift
from ..normalize.text import normalize

PLACEHOLDER = {
    PIIType.NAME: "[NAME]", PIIType.PHONE: "[PHONE]", PIIType.EMAIL: "[EMAIL]", PIIType.ADDRESS: "[ADDRESS]",
    PIIType.PINCODE: "[PIN]", PIIType.DATE: "[DATE]",
}
for _t in ID_TYPES:
    PLACEHOLDER[_t] = "[ID]"


def shift_date_text(original: str, days: int) -> str | None:
    """Shift the single date found in `original`; None if it cannot be parsed safely."""
    n = normalize(original).text
    ms = find_dates(n)
    if len(ms) != 1:
        return None
    m = ms[0]
    if n[:m.start].strip(" ,;:()-") or n[m.end:].strip(" ,;:()-"):
        return None  # extra text around the date: do not guess
    y, mo, d = shift(m, days)
    return render_date(m, y, mo, d)


def redact(original: str, spans: Sequence[Span], days: int, extras: Sequence[tuple[int, int, str]] = (), pin_fn=None) -> str:
    """Apply spans (placeholders / shifted dates / generalized PIN) plus extra replacements
    (generalized ages, suppressed diagnoses, birth-year bands). An extra that overlaps a span is ignored, except
    that an extra covering whole DATE spans replaces them (a date of birth generalized to a birth-year band)."""
    items = [(s.start, s.end, s) for s in spans]
    for a, b, t in extras:
        hit = [it for it in items if a < it[1] and it[0] < b]
        if hit and all(not isinstance(o, str) and o.type == PIIType.DATE and a <= s and e <= b for s, e, o in hit):
            items = [it for it in items if it not in hit]
            hit = []
        if not hit:
            items.append((a, b, t))
    out = []
    pos = 0
    for a, b, obj in sorted(items, key=lambda x: (x[0], x[1])):
        if a < pos:
            continue
        out.append(original[pos:a])
        if isinstance(obj, str):
            out.append(obj)
        elif obj.type == PIIType.DATE:
            out.append(shift_date_text(original[a:b], days) or "[DATE]")
        elif obj.type == PIIType.PINCODE and pin_fn is not None:
            out.append(pin_fn(original[a:b]))
        else:
            out.append(PLACEHOLDER[obj.type])
        pos = b
    out.append(original[pos:])
    return "".join(out)
