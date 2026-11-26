"""Find dates in normalized text and re-render a shifted date in the same style.

Used by detection (find) and by the privacy layer (shift + render), so a free-text
"12th March, 2021" and a table cell "12/03/2021" are treated by the same code.
Day-first is assumed (Indian convention); a numeric date whose 2nd part is > 12 is read month-first.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Optional

import regex as re

_EN = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
_HI = ["जनवरी", "फरवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"]
_MON = {}
for i, m in enumerate(_EN):
    _MON[m] = i + 1
    _MON[m[:3]] = i + 1
_MON["sept"] = 9
for i, m in enumerate(_HI):
    _MON[m] = i + 1
_MON.update({"सितम्बर": 9, "अक्तूबर": 10, "नवम्बर": 11, "दिसम्बर": 12, "अप्रेल": 4})

_MON_RE = "|".join(sorted((re.escape(k) for k in _MON), key=len, reverse=True))
_SEP = r"[/\-.]"

_P_NUM = re.compile(rf"(?<![\d/\-.])(\d{{1,2}})({_SEP})(\d{{1,2}})\2(\d{{4}}|\d{{2}})(?![\d]|[/\-.]\d)")
_P_ISO = re.compile(rf"(?<![\d/\-.])(\d{{4}})({_SEP})(\d{{1,2}})\2(\d{{1,2}})(?![\d]|[/\-.]\d)")
_P_DMY = re.compile(
    rf"(?<![\d\p{{L}}])(\d{{1,2}})(st|nd|rd|th)?[\s\-/.]*({_MON_RE})(?:\p{{L}}*)\.?(,?)[\s\-/.]*(\d{{4}}|\d{{2}})(?![\d])", re.I)
_P_MDY = re.compile(
    rf"(?<![\p{{L}}])({_MON_RE})\p{{L}}*\.?[\s\-/.]*(\d{{1,2}})(st|nd|rd|th)?(,?)[\s\-/.]*(\d{{4}})(?![\d])", re.I)
_P_MY = re.compile(rf"(?<![\p{{L}}\d])({_MON_RE})(?:\p{{L}}*)\.?(,?)\s+(\d{{4}})(?![\d])", re.I)


@dataclass(frozen=True)
class DateMatch:
    start: int
    end: int
    y: int
    m: int
    d: Optional[int]  # None: month-year only
    kind: str  # num | iso | dmy | mdy | my
    sep: str = "/"
    pad: bool = True
    yy: bool = False
    mdy_numeric: bool = False
    month_text: str = ""  # original month token style: "en_abbr" | "en_full" | "en_upper" | "hi"
    ordinal: bool = False
    comma: bool = False


def _year(s: str) -> int:
    y = int(s)
    if len(s) == 2:
        y = 2000 + y if y <= 29 else 1900 + y
    return y


def _valid(y: int, m: int, d: int) -> bool:
    if not (1900 <= y <= 2100):
        return False
    try:
        dt.date(y, m, d)
        return True
    except ValueError:
        return False


def _month_style(tok: str) -> str:
    if any("ऀ" <= c <= "ॿ" for c in tok):
        return "hi"
    if tok.isupper():
        return "en_upper"
    if len(tok) <= 4 and tok.lower() in _MON and tok.lower() not in _EN:
        return "en_abbr"
    if tok.lower() in _EN and len(tok) > 3:
        return "en_full"
    return "en_abbr"


def find_dates(text: str) -> list[DateMatch]:
    out: list[DateMatch] = []
    taken: list[tuple[int, int]] = []

    def free(a: int, b: int) -> bool:
        return all(b <= s or a >= e for s, e in taken)

    def add(dm: DateMatch) -> None:
        if free(dm.start, dm.end):
            out.append(dm)
            taken.append((dm.start, dm.end))

    for m in _P_ISO.finditer(text):
        y, mo, d = int(m.group(1)), int(m.group(3)), int(m.group(4))
        if _valid(y, mo, d):
            add(DateMatch(m.start(), m.end(), y, mo, d, "iso", m.group(2), len(m.group(3)) == 2 and len(m.group(4)) == 2))
    for m in _P_NUM.finditer(text):
        a, b, ys = int(m.group(1)), int(m.group(3)), m.group(4)
        y = _year(ys)
        d, mo, mdy = a, b, False
        if b > 12 and a <= 12:
            d, mo, mdy = b, a, True
        if _valid(y, mo, d):
            add(DateMatch(m.start(), m.end(), y, mo, d, "num", m.group(2), len(m.group(1)) == 2, len(ys) == 2, mdy))
    for m in _P_DMY.finditer(text):
        mo = _MON.get(m.group(3).lower())
        if mo is None:
            continue
        d, ys = int(m.group(1)), m.group(5)
        y = _year(ys)
        if _valid(y, mo, d):
            seg = text[m.start():m.end()]
            add(DateMatch(m.start(), m.end(), y, mo, d, "dmy", " ", len(m.group(1)) == 2, len(ys) == 2, False,
                          _month_style(_month_token(seg, m.group(3))), bool(m.group(2)), bool(m.group(4))))
    for m in _P_MDY.finditer(text):
        mo = _MON.get(m.group(1).lower())
        if mo is None:
            continue
        d, y = int(m.group(2)), int(m.group(5))
        if _valid(y, mo, d):
            seg = text[m.start():m.end()]
            add(DateMatch(m.start(), m.end(), y, mo, d, "mdy", " ", False, False, False,
                          _month_style(_month_token(seg, m.group(1))), bool(m.group(3)), bool(m.group(4))))
    for m in _P_MY.finditer(text):
        mo = _MON.get(m.group(1).lower())
        if mo is None:
            continue
        y = int(m.group(3))
        if 1900 <= y <= 2100:
            seg = text[m.start():m.end()]
            add(DateMatch(m.start(), m.end(), y, mo, None, "my", " ", False, False, False,
                          _month_style(_month_token(seg, m.group(1))), False, bool(m.group(2))))
    out.sort(key=lambda x: x.start)
    return out


def _month_token(seg: str, grp: str) -> str:
    i = seg.lower().find(grp.lower())
    j = i
    while j < len(seg) and (seg[j].isalpha() or "ऀ" <= seg[j] <= "ॿ"):
        j += 1
    return seg[i:j] if i >= 0 else grp


def _month_name(m: int, style: str) -> str:
    if style == "hi":
        return _HI[m - 1]
    full = _EN[m - 1].capitalize()
    if style == "en_full":
        return full
    if style == "en_upper":
        return full[:3].upper()
    return full[:3]


def _ord(d: int) -> str:
    suf = "th" if 10 <= d % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(d % 10, "th")
    return f"{d}{suf}"


def shift(dm: DateMatch, days: int) -> tuple[int, int, Optional[int]]:
    """Shift by `days`; month-only dates move by the nearest whole number of months."""
    if dm.d is None:
        idx = dm.y * 12 + dm.m - 1 + round(days / 30.44)
        return idx // 12, idx % 12 + 1, None
    n = dt.date(dm.y, dm.m, dm.d) + dt.timedelta(days=days)
    return n.year, n.month, n.day


def render(dm: DateMatch, y: int, m: int, d: Optional[int]) -> str:
    yr = f"{y % 100:02d}" if dm.yy else f"{y}"
    if dm.kind == "iso":
        return f"{y}{dm.sep}{m:02d}{dm.sep}{d:02d}"
    if dm.kind == "num":
        a, b = (m, d) if dm.mdy_numeric else (d, m)
        if dm.pad:
            return f"{a:02d}{dm.sep}{b:02d}{dm.sep}{yr}"
        return f"{a}{dm.sep}{b}{dm.sep}{yr}"
    if dm.kind == "dmy":
        dd = _ord(d) if dm.ordinal else (f"{d:02d}" if dm.pad else str(d))
        return f"{dd} {_month_name(m, dm.month_text)}{',' if dm.comma else ''} {yr}"
    if dm.kind == "mdy":
        dd = _ord(d) if dm.ordinal else str(d)
        return f"{_month_name(m, dm.month_text)} {dd}{',' if dm.comma else ''} {y}"
    return f"{_month_name(m, dm.month_text)}{',' if dm.comma else ''} {y}"
