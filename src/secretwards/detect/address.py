"""Indian address detection: house numbers, street/locality words, landmarks
("near Hanuman mandir", "mandir ke paas", "मंदिर के पास"), city gazetteer, village/post/district,
PIN codes. Anchors are found first, then extended over neighbouring comma segments that look like address text.
"""
from __future__ import annotations

import regex as re

from ..contracts import PIIType, Span, Unit
from . import lexicon as L
from ..normalize.text import ocr_digit_view
from .base import Collector
from .headers import hint_for
from .names import Tok, tokenize

_HOUSE = re.compile(
    r"(?<![\p{L}\d])(?:h\.?\s?no\.?|house\s*(?:no\.?)?|flat\s*(?:no\.?)?|plot\s*(?:no\.?)?|room\s*(?:no\.?)?|door\s*no\.?|bldg\.?|building)"
    r"\s*[:#.\-]?\s*[\w/\-]+", re.I)
_HOUSE_BARE = re.compile(r"(?<![\d/\p{L}])\d{1,4}\s*/\s*[A-Za-z0-9]{1,3}(?=\s*,)|(?<![\p{L}\d])#\s?\d+[\w/\-]*")
_SUFFIX = (r"nagar|colony|vihar|road|rd|marg|chowk|enclave|puram|ganj|pur|basti|bazaar|bazar|lane|street|st|layout|society|"
           r"apartments?|apts?|complex|sector|phase|block|extension|ext|khand|tola|para|garh|abad|gali|mohalla|gaon|village|nagri|wadi|peth|mandi|"
           r"stand|chauraha|crossing|market|park|bagh|talab|kunj|dham|sadan|niwas|bhawan|bhavan")
_SUFFIX_DEV = r"नगर|कॉलोनी|कालोनी|विहार|रोड|मार्ग|चौक|एन्क्लेव|पुरम|गंज|पुर|बस्ती|बाजार|गली|मोहल्ला|गाँव|गांव|सेक्टर|चौराहा|बाग|कुंज|धाम"
_AREA = re.compile(rf"(?<![\p{{L}}])(?:{_SUFFIX})(?![\p{{L}}])(?!\s*[:/])(?:\s*(?:no\.?\s*)?\d{{1,3}}[A-Za-z]?)?", re.I)
_AREA_DEV = re.compile(rf"(?<![/])(?:{_SUFFIX_DEV})(?![ऀ-ॿ])(?!\s*[:/])(?:\s*\d{{1,3}})?")
_LANDMARK = re.compile(
    r"(?<![\p{L}])(?:near|nr\.?|behind|opp\.?|opposite|beside|next\s+to|adjacent\s+to|in\s+front\s+of|infront\s+of|close\s+to|back\s+of)\s+", re.I)
_LM_HINGLISH = re.compile(r"\s+ke\s+(?:paas|pass|samne|saamne|peeche|piche|bagal|nazdik|najdik)\b", re.I)
_LM_DEV = re.compile(r"\s+के\s+(?:पास|सामने|पीछे|बगल|नजदीक|निकट)")
_VILLAGE = re.compile(
    r"(?<![\p{L}])(?:vill(?:age)?|post|p\.o\.?|thana|p\.s\.)\.?\s*[:\-]?\s+(?=[A-Z])|"
    r"(?:ग्राम|गाँव|पोस्ट|थाना)(?![/:\s]*[/:])\s*[:\-]?\s*", re.I)
# a "City" / "Town" column in a rural export holds villages (redact); district / tehsil / state columns are what generalization keeps
_KEEP_HDR = re.compile(r"district|distt|zila|jila|tehsil|tahsil|taluk|state|जिला|तहसील|राज्य", re.I)
_KEEP_SEG = re.compile(r"^\s*(?:teh(?:sil)?\.?|tahsil|taluk[a]?|mandal|dist(?:t|rict)?\.?|zila|jila|state|तहसील|जिला|राज्य)(?![\p{L}])", re.I)
_BARE_PIN = re.compile(r"(?<![\d.])[1-9]\d{5}(?![\d.])")
_PIN_CTX = re.compile(r"(?<![\p{L}])(?:teh(?:sil)?|tahsil|distt?|district|village|vill|mohall?a|h\.?\s?no|c\s*/\s*o|near|address|pin|post|thana)(?![\p{L}])|तहसील|जिला|गाँव|ग्राम|पता|पिन", re.I)
_LABEL = re.compile(
    r"(?<![\p{L}])(?:address(?:\s*for\s*correspondence)?|addr|residence|resident\s+of|r\s*/\s*o|res\.?|ghar\s*ka\s*pata|pata|permanent\s*address|"
    r"गाँव\s*/\s*मोहल्ला|गाँव/मोहल्ला|पता|निवासी|निवास)\s*[:\-–=]+\s*|(?<![\p{L}])(?:resident\s+of|r\s*/\s*o|living\s+(?:in|at)|lives\s+(?:in|at)|stays\s+(?:in|at)|staying\s+at)\s+", re.I)
_PIN_BARE = re.compile(r"^[\s,\-:]*(?:pin\s*code|pincode|pin|zip|पिन\s*कोड|पिन)?\s*[:\-]?\s*([1-9]\d{5})(?!\d)", re.I)
_CLAUSE_STOP = frozenset("""presented admitted complaints complaining came brought advised diagnosed has had was is with since for who which
and but he she pt patient c/o known referred on admitted discharged phone mobile contact call email age aged dob date uhid abha policy
bimari dawai umar mobile aap hum rehte rehta ko ne se hain hai tha gaya aaya बताया है हैं था""".split())
_NUM_ONLY = re.compile(r"^\d{1,4}[A-Za-z]?$")


def _is_clause_word(t: str) -> bool:
    return t.lower() in _CLAUSE_STOP or t in L.HI_STOP and t not in ("पास", "सामने", "पीछे")


class AddressDetector:
    name = "address"

    def detect(self, unit: Unit) -> list[Span]:
        text = unit.norm.text
        col = Collector(unit, self.name)
        if not text.strip():
            return col.spans
        toks = tokenize(text)
        spans: list[tuple[int, int, float]] = []
        hint = hint_for(unit.header)

        def seg_bounds(pos: int) -> tuple[int, int]:
            """[start, end) of the comma segment containing pos (bounded by newline/; .)"""
            a = max(text.rfind(",", 0, pos), text.rfind("\n", 0, pos), text.rfind(";", 0, pos)) + 1
            cands = [x for x in (text.find(",", pos), text.find("\n", pos), text.find(";", pos)) if x >= 0]
            b = min(cands) if cands else len(text)
            return a, b

        def seg_is_addressy(seg: str) -> bool:
            s = seg.strip()
            if not s or len(s) > 70 or _KEEP_SEG.match(s):
                return False
            ts = tokenize(s)
            words = [t for t in ts if t.t[0].isalpha() or "ऀ" <= t.t[0] <= "ॿ"]
            if not words:
                return bool(re.fullmatch(r"[\d/\-A-Za-z ]{1,10}", s)) and any(c.isdigit() for c in s)
            if any(_is_clause_word(t.t) for t in words):
                return False
            low = s.lower()
            if low in L.cities() or any(w.t.lower() in L.cities() for w in words):
                return True
            if _AREA.search(s) or _AREA_DEV.search(s) or _LANDMARK.search(s) or _LM_HINGLISH.search(s) or _LM_DEV.search(s) or _HOUSE.search(s):
                return True
            if re.search(r"[1-9]\d{5}", s):
                return True
            # capitalised, non-medical words only
            if len(words) <= 4 and all((w.t[0].isupper() or "ऀ" <= w.t[0] <= "ॿ") and not L.is_clinical(w.t) and not L.is_drug(w.t)
                                       and not L.is_common(w.t) for w in words):
                return True
            return False

        def extend(a: int, b: int) -> tuple[int, int]:
            # to the right over comma segments
            while b < len(text) and text[b] == ",":
                ns, ne = seg_bounds(b + 1)
                if seg_is_addressy(text[ns:ne]):
                    b = ne
                else:
                    break
            # to the left over comma segments (house numbers, locality names)
            while a > 0:
                k = a - 1
                while k >= 0 and text[k] in " ":
                    k -= 1
                if k >= 0 and text[k] == ",":
                    ps, pe = seg_bounds(k)
                    if seg_is_addressy(text[ps:pe]) and not _is_clause_word(text[ps:pe].strip().split(" ")[-1] if text[ps:pe].strip() else ""):
                        a = ps
                        continue
                break
            return a, b

        def left_words(i: int, maxn: int, dev: bool) -> int:
            """start offset after extending left over up to maxn address-name words"""
            start = toks[i].s
            k = i - 1
            n = 0
            while k >= 0 and n < maxn:
                t = toks[k]
                if text[t.e:toks[k + 1].s].strip(" .") != "" and not (text[t.e:toks[k + 1].s] == "." and False):
                    break
                if not (t.t[0].isalpha() or "ऀ" <= t.t[0] <= "ॿ"):
                    break
                if (("ऀ" <= t.t[0] <= "ॿ") != dev) or _is_clause_word(t.t) or L.is_clinical(t.t) or L.is_drug(t.t):
                    break
                if not dev and not (t.t[0].isupper()):
                    break
                start = t.s
                n += 1
                k -= 1
            return start

        # house numbers
        for m in _HOUSE.finditer(text):
            spans.append((m.start(), m.end(), 0.8))
        for m in _HOUSE_BARE.finditer(text):
            spans.append((m.start(), m.end(), 0.6))
        # locality words
        for rx, dev in ((_AREA, False), (_AREA_DEV, True)):
            for m in rx.finditer(text):
                i = next((k for k, t in enumerate(toks) if t.s >= m.start()), None)
                if i is None:
                    continue
                a = left_words(i, 3, dev)
                if a == m.start() and not dev:
                    # a bare suffix word with no name before it ("road", "stand") is weak evidence
                    w = text[m.start():m.end()].strip().lower()
                    if w in ("road", "street", "st", "lane", "park", "market", "stand", "block", "sector", "phase", "village", "complex", "society"):
                        if not re.match(r"\w+\s*(no\.?\s*)?\d", text[m.start():m.end()], re.I):
                            continue
                spans.append((a, m.end(), 0.75))
        # landmarks
        for m in _LANDMARK.finditer(text):
            j = m.end()
            i = next((k for k, t in enumerate(toks) if t.s >= j), None)
            if i is None:
                continue
            e = j
            n = 0
            k = i
            while k < len(toks) and n < 6:
                t = toks[k]
                if text[e:t.s].strip(" ") != "":
                    break
                if not (t.t[0].isalpha() or t.t[0].isdigit() or "ऀ" <= t.t[0] <= "ॿ") or _is_clause_word(t.t):
                    break
                e = t.e
                n += 1
                k += 1
            if n:
                spans.append((m.start(), e, 0.8))
        for rx, dev in ((_LM_HINGLISH, False), (_LM_DEV, True)):
            for m in rx.finditer(text):
                i = next((k for k, t in enumerate(toks) if t.e > m.start() + 1 and t.s >= m.start()), None)
                # words before the cue
                k = max((idx for idx, t in enumerate(toks) if t.e <= m.start()), default=None)
                if k is None:
                    continue
                a = toks[k].s
                n = 0
                while k >= 0 and n < 4:
                    t = toks[k]
                    if k + 1 < len(toks) and text[t.e:toks[k + 1].s].strip(" ") != "" and n:
                        break
                    if not (t.t[0].isalpha() or "ऀ" <= t.t[0] <= "ॿ") or _is_clause_word(t.t):
                        break
                    if (("ऀ" <= t.t[0] <= "ॿ") != dev):
                        break
                    a = t.s
                    n += 1
                    k -= 1
                if n:
                    spans.append((a, m.end(), 0.8))
        # village / post / district
        for m in _VILLAGE.finditer(text):
            i = next((k for k, t in enumerate(toks) if t.s >= m.end()), None)
            if i is None:
                continue
            e, n = m.end(), 0
            while i < len(toks) and n < 3 and (toks[i].t[0].isalpha() or "ऀ" <= toks[i].t[0] <= "ॿ") \
                    and text[e:toks[i].s].strip(" ") == "" and not _is_clause_word(toks[i].t) and not L.is_clinical(toks[i].t):
                e = toks[i].e
                n += 1
                i += 1
            if n:
                spans.append((m.start(), e, 0.7))
        # cities
        for k, t in enumerate(toks):
            w = t.t.lower()
            if w in L.cities() and t.t[0].isupper():
                spans.append((t.s, t.e, 0.8))
            elif k + 1 < len(toks) and f"{w} {toks[k + 1].t.lower()}" in L.cities() and t.t[0].isupper():
                spans.append((t.s, toks[k + 1].e, 0.8))
        # labelled address: everything up to the clause end
        for m in _LABEL.finditer(text):
            a = m.end()
            ns, ne = seg_bounds(a)
            end = a
            pos = a
            while True:
                s2, e2 = seg_bounds(pos)
                seg = text[pos:e2]
                km = _KEEP_SEG.match(seg)
                if km:
                    end = pos if pos > a else a
                    break
                cut = None
                for t in tokenize(seg):
                    if _is_clause_word(t.t) and (t.t[0].isalpha()):
                        cut = t.s
                        break
                if cut is not None:
                    if cut > 0:
                        end = pos + cut
                    break
                end = e2
                if e2 < len(text) and text[e2] == ",":
                    pos = e2 + 1
                    continue
                break
            if end > a:
                spans.append((a, end, 0.85))
        if (hint.kind == "address" or (hint.kind == "city" and not _KEEP_HDR.search(unit.header))) and text.strip() and not re.fullmatch(r"[\d\s]+", text.strip()) and len(text) < 300:
            spans.append((0, len(text), 0.7))

        # extend over neighbouring address-looking comma segments and merge overlaps
        ext = []
        for a, b, sc in spans:
            a2, b2 = extend(a, b)
            ext.append((a2, b2, sc))
        ext.sort()
        merged: list[list] = []
        for a, b, sc in ext:
            if merged and a <= merged[-1][1] + 2 and text[merged[-1][1]:a].strip(" ,") == "":
                merged[-1][1] = max(merged[-1][1], b)
                merged[-1][2] = max(merged[-1][2], sc)
            else:
                merged.append([a, b, sc])
        for a, b, sc in merged:
            # trailing PIN right after the address
            pm = _PIN_BARE.match(ocr_digit_view(text)[b:])
            if pm:
                col.add(b + pm.start(1), b + pm.end(1), PIIType.PINCODE, 0.85)
                # keep the cue word inside the address span end
            col.add(a, b, PIIType.ADDRESS, sc)
        # a bare 6-digit PIN on a line that reads like an address (district / tehsil may sit between them)
        pview = ocr_digit_view(text)
        for pm in _BARE_PIN.finditer(pview):
            ls = text.rfind("\n", 0, pm.start()) + 1
            le = text.find("\n", pm.end())
            if _PIN_CTX.search(text[ls: le if le >= 0 else len(text)].replace(text[pm.start():pm.end()], " ")):
                col.add(pm.start(), pm.end(), PIIType.PINCODE, 0.8)
        return col.spans
