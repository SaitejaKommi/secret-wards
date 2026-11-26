"""Person-name detection for English / Hindi / Hinglish text.

Evidence, strongest first:
  1. label cues      "Patient Name:", "Guardian:", "नाम:", "Mareez ka naam:"    -> run of name tokens
  2. relation cues   s/o d/o w/o c/o, son of, पिता, पति ...                       -> relative
  3. honorifics      Mr Mrs Shri Smt Dr ... (Dr + drug is NOT a person)
  4. header hints    a 'name' column makes the whole cell a name (if it looks like one)
  5. gazetteer       common given names / surnames, also matched across scripts
  6. kin terms       "<name> bhaiya / didi / ji"
  7. capital runs    2+ capitalised unknown words, weakest, off the medical lexicon
Medical lexicons veto drug / disease / unit words at every step.
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass

import regex as re

from ..contracts import PIIType, Span, Unit
from . import lexicon as L
from .base import Collector
from .headers import hint_for

_TOK = re.compile(r"[\p{L}\p{M}][\p{L}\p{M}'’\-]*|\d+|[^\s\p{L}\p{M}\d]")
_DEV = re.compile(r"[ऀ-ॿ]")
_HON = frozenset("mr mrs ms miss shri sh smt sri master kumari km late baby श्री श्रीमती श्रीमान कुमारी स्व".split())
_DOCW = frozenset("dr prof doctor डॉ डॉक्टर".split())
_KIN = frozenset("bhaiya bhai didi ji sahab saab sahib babu uncle aunty aunt bhabhi mummy papa dada dadi nana nani chacha chachi mama mausi "
                 "भैया भाई दीदी जी साहब साहिब बाबू चाचा मामा".split())
_KIN_BLOCK = frozenset("haan han ok okay yes no ha ji nahi aap tum ye wo kya kab sir madam".split())
_STOP_AFTER = frozenset("age aged yrs years year old male female sex phone mobile address resident residing from with and of the at on in for".split())

_LABEL_PATIENT = re.compile(
    r"(?:patient(?:'s)?\s*(?:full\s*)?name|pt\.?\s*name|name\s*of\s*(?:the\s*)?(?:patient|member|insured)|full\s*name|"
    r"member\s*name|insured\s*name|\bname|\bnm|\bnaam|(?:mareez|marij|mariz|rogi|rogee)\s*ka\s*naam|"
    r"रोगी\s*का\s*नाम|मरीज़?\s*का\s*नाम|नाम|\bmember|\binsured|\bpatient|\bpt|मरीज़?|रोगी)\s*[:\-–=]+\s*", re.I)
_LABEL_REL = re.compile(
    r"(?:guardian|attendant|relative|father(?:\s*/\s*husband)?(?:'s)?(?:\s*name)?|mother(?:'s)?(?:\s*name)?|husband(?:'s)?(?:\s*name)?|"
    r"wife(?:'s)?(?:\s*name)?|spouse|next\s*of\s*kin|kin|contact\s*person|nominee|informant|emergency\s*contact|"
    r"(?:pita|pati|patni|mata|bhai)\s*ka\s*naam|पिता\s*/\s*पति(?:\s*का\s*नाम)?|पिता(?:\s*का\s*नाम)?|पति(?:\s*का\s*नाम)?|"
    r"पत्नी(?:\s*का\s*नाम)?|माता(?:\s*का\s*नाम)?|अभिभावक|संरक्षक)\s*[:\-–=]+\s*", re.I)
_LABEL_DOC = re.compile(
    r"(?:referred\s*by|consultant|doctor|physician|treating\s*doctor|consulting\s*doctor|"
    r"डॉक्टर|चिकित्सक)\s*[:\-–=]+\s*", re.I)
_REL_CUE = re.compile(
    r"(?<![\p{L}\d])(?:s\s*/\s*o|d\s*/\s*o|w\s*/\s*o|c\s*/\s*o|son\s+of|daughter\s+of|wife\s+of|husband\s+of|"
    r"father|mother|husband|wife|guardian|attendant|brother|sister|uncle|aunty|"
    r"पुत्र|पुत्री|सुपुत्र|सुपुत्री|पत्नी|पिता|पति|माता|भाई|बहन|पिता का नाम|पति का नाम|pita ka naam|pati ka naam)(?![\p{L}])"
    r"\s*[:\-.]?\s*", re.I)
_HON_CUE = re.compile(
    r"(?<![\p{L}\d])(?:mr|mrs|ms|miss|shri|sh|smt|sri|master|kumari|km|late|baby|श्रीमती|श्रीमान|श्री|कुमारी|स्व)(?![\p{L}])\.?\s*", re.I)
_DR_CUE = re.compile(r"(?<![\p{L}\d])(?:dr|prof|doctor|डॉक्टर|डॉ)(?![\p{L}])\.?\s*", re.I)
_PT_WEAK = re.compile(r"(?<![\p{L}\d])(?:patient|pt|mareez|मरीज़?|रोगी)\s+(?=[A-Zऀ-ॿ])", re.I)
_RELATION_BEFORE = frozenset("s/o d/o w/o c/o".split())


@dataclass
class Tok:
    s: int
    e: int
    t: str


def tokenize(text: str) -> list[Tok]:
    out = []
    for m in _TOK.finditer(text):
        e = m.end()
        # a single letter followed by '.' is an initial: keep the dot inside the token ("R.")
        if len(m.group()) == 1 and m.group().isalpha() and text[e:e + 1] == "." and not (text[e + 1:e + 2].isalpha() and False):
            e += 1
        out.append(Tok(m.start(), e, text[m.start():e]))
    return out


def _letters(t: str) -> str:
    return t.strip(".'’-")


def _is_cap(t: str) -> bool:
    return t[:1].isupper()


def _is_deva(t: str) -> bool:
    return bool(_DEV.search(t))


def _veto(t: str, strong: bool) -> bool:
    w = t.lower().strip(".'’").removesuffix("'s").removesuffix("’s")
    if w in L.DRUG_WORDS:
        return True
    if strong:
        return False
    return w in L.CLINICAL_WORDS or L.is_common(t) or t in L.HI_STOP


def _nameish(text: str, toks: list[Tok], i: int, strong: bool, have_name: bool) -> bool:
    """Can toks[i] be part of a person's name?"""
    tk = toks[i]
    t = tk.t
    if len(t) == 1 and not t.isalpha():
        return False
    if t.endswith(("'s", "’s")):
        return False
    if _is_deva(t):
        if t in L.HI_STOP or len(t) < 2:
            return False
        return strong or L.deva_gaz_name(t)
    if not t[0].isalpha():
        return False
    w = _letters(t)
    if _veto(t, strong):
        return False
    if len(w) == 1:  # initial: "R." or a bare capital next to another name token
        nxt = text[tk.e:tk.e + 1]
        if nxt == "/":
            return False
        return w.isupper() and (t.endswith(".") or have_name)
    if L.is_gaz_name(t):
        return True
    if strong:
        return True  # label cue grants lowercase / unknown names
    return _is_cap(t) and len(w) >= 2


def _gap_ok(text: str, a: Tok, b: Tok, comma: bool = False) -> bool:
    g = text[a.e:b.s]
    if comma and g in (", ", ","):
        return True
    return g != "" and set(g) <= {" "}


def take_run(text: str, toks: list[Tok], i: int, strong: bool, max_n: int = 4) -> tuple[int, int] | None:
    """Longest run of name-ish tokens starting at token index i -> (first_tok, last_tok)."""
    n = len(toks)
    # skip honorifics at the start of the run
    while i < n and toks[i].t.lower().strip(".") in _HON | _DOCW:
        if i + 1 < n and (text[toks[i].e:toks[i + 1].s].strip(" .") == ""):
            i += 1
        else:
            break
    j = i
    have = False
    while j < n and j - i < max_n:
        if j > i and not _gap_ok(text, toks[j - 1], toks[j], comma=strong and j - i == 1 and _is_cap(toks[j - 1].t)
                                 and _is_cap(toks[j].t) and not L.is_common(toks[j].t)):
            break
        if not _nameish(text, toks, j, strong, have):
            break
        have = True
        j += 1
    if j == i:
        return None
    # trailing single capital that is really part of "s/o"
    last = toks[j - 1]
    if len(_letters(last.t)) == 1 and not last.t.endswith(".") and j - 1 > i:
        j -= 1
    return i, j - 1


def _first_tok_at(starts: list[int], pos: int) -> int:
    return bisect.bisect_left(starts, pos)


class NameDetector:
    name = "names"

    def __init__(self, heuristic: bool = True):
        self.heuristic = heuristic

    def detect(self, unit: Unit) -> list[Span]:
        text = unit.norm.text
        col = Collector(unit, self.name)
        if not text.strip():
            return col.spans
        toks = tokenize(text)
        if not toks:
            return col.spans
        starts = [t.s for t in toks]
        hint = hint_for(unit.header)
        taken: set[int] = set()

        def emit(i: int, j: int, score: float, role: str) -> None:
            if any(k in taken for k in range(i, j + 1)):
                return
            a, b = toks[i].s, toks[j].e
            if toks[j].t.endswith(".") and len(_letters(toks[j].t)) > 1:
                b -= 1
            col.add(a, b, PIIType.NAME, score, role)
            taken.update(range(i, j + 1))

        def after(m_end: int, strong: bool, score: float, role: str) -> None:
            i = _first_tok_at(starts, m_end)
            if i >= len(toks):
                return
            r = take_run(text, toks, i, strong)
            if r:
                emit(r[0], r[1], score, role)

        # 4. header hint: whole cell is a name
        clinical_cell = any(L.is_drug(t.t) or L.is_clinical(t.t) for t in toks)  # a diagnosis in a shifted column
        if hint.kind == "name" and len(text) <= 80 and not clinical_cell and not any(c.isdigit() for c in text.replace(" ", "")[:3]):
            i0 = 0
            r = take_run(text, toks, i0, True, 5)
            if r:
                emit(r[0], r[1], 0.85, hint.role or "patient")
        # 1. label cues
        for rx, role in ((_LABEL_REL, "relative"), (_LABEL_DOC, "doctor"), (_LABEL_PATIENT, "patient")):
            for m in rx.finditer(text):
                after(m.end(), True, 0.95, role)
        # 2. relation cues
        for m in _REL_CUE.finditer(text):
            after(m.end(), False, 0.9, "relative")
        # 3. honorifics
        for m in _DR_CUE.finditer(text):
            after(m.end(), False, 0.85, "doctor")
        for m in _HON_CUE.finditer(text):
            after(m.end(), False, 0.85, "")
        for m in _PT_WEAK.finditer(text):
            after(m.end(), False, 0.8, "patient")
        # 5. gazetteer
        n = len(toks)
        i = 0
        while i < n:
            t = toks[i].t
            if i in taken:
                i += 1
                continue
            hit = False
            if _is_deva(t):
                hit = L.deva_gaz_name(t) and t not in L.HI_STOP
            elif t[0].isalpha() and len(_letters(t)) >= 3 and L.is_gaz_name(t) and not _veto(t, False):
                hit = True
            if hit:
                a = i
                while a > 0 and a - 1 not in taken and _gap_ok(text, toks[a - 1], toks[a]) and i - a < 3 \
                        and _nameish(text, toks, a - 1, False, True) and (_is_cap(toks[a - 1].t) or L.is_gaz_name(toks[a - 1].t) or _is_deva(toks[a - 1].t)):
                    a -= 1
                b = i
                while b + 1 < n and b + 1 not in taken and _gap_ok(text, toks[b], toks[b + 1]) and b - a < 3 \
                        and _nameish(text, toks, b + 1, False, True) and (_is_cap(toks[b + 1].t) or L.is_gaz_name(toks[b + 1].t) or _is_deva(toks[b + 1].t)):
                    b += 1
                lower_only = all(toks[k].t.islower() for k in range(a, b + 1) if not _is_deva(toks[k].t))
                emit(a, b, 0.6 if lower_only else 0.75, "")
                i = b + 1
                continue
            i += 1
        # 6. kin terms: "<name> bhaiya"
        for k in range(1, n):
            if toks[k].t.lower() in _KIN and k - 1 not in taken and _gap_ok(text, toks[k - 1], toks[k]):
                p = toks[k - 1]
                w = p.t.lower()
                if w in _KIN_BLOCK or len(_letters(p.t)) < 3 or _veto(p.t, False) or w in _STOP_AFTER:
                    continue
                if _is_deva(p.t) and (p.t in L.HI_STOP):
                    continue
                if _is_deva(p.t) or p.t[0].isalpha():
                    emit(k - 1, k - 1, 0.7, "")
        # 7. capital runs
        if self.heuristic:
            self._cap_runs(text, toks, taken, emit)
        return col.spans

    def _cap_runs(self, text: str, toks: list[Tok], taken: set[int], emit) -> None:
        n = len(toks)
        i = 0
        while i < n:
            t = toks[i].t
            ok = (t[0].isalpha() and not _is_deva(t) and _is_cap(t) and i not in taken
                  and (len(_letters(t)) >= 2 or t.endswith(".")) and not _veto(t, False))
            if not ok:
                i += 1
                continue
            j = i
            while j + 1 < n and j + 1 not in taken and _gap_ok(text, toks[j], toks[j + 1]):
                t2 = toks[j + 1].t
                if t2[0].isalpha() and not _is_deva(t2) and (_is_cap(t2)) and not _veto(t2, False)                         and (len(_letters(t2)) >= 2 or t2.endswith(".")):
                    j += 1
                else:
                    break
            if j > i:
                # skip sentence-initial single runs and all-upper headings
                run = [toks[k].t for k in range(i, j + 1)]
                if not all(w.isupper() for w in run) or i == 0 or text[:toks[i].s].endswith(": "):
                    line_start = toks[i].s == 0 or text[toks[i].s - 1] == "\n"
                    if not (line_start and len(run) < 3 and not text[:toks[i].s].strip() == ""):
                        emit(i, j, 0.45, "")
            i = j + 1
