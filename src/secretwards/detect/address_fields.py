"""Address parts by column meaning and by label: village, locality, house, landmark, street.

Complements the lead's `address.py` (which finds addresses from anchors in running text) for three gaps
seen on the practice data, using only labels and context, never place-name lists:
1. Columns whose header MEANS village / locality / house / landmark in English, Hindi or Hinglish
   ("Village Name", "Gaon", "Mauza", "ग्राम", "Mohalla", "Makan No") -> the whole cell is an address part.
2. "label: value" in text ("ग्राम: <name>", "Village - <name>", "Mohalla: <name>") -> the value up to the
   end of its segment, stopping before the next label (tehsil / district / PIN stay for generalization).
3. "Ward N" is a municipal ward (locality) ONLY when its line also carries address cues (H.No, mohalla,
   tehsil, C/O, address label...). A hospital ward ("Ward: 4 (Medicine)", "Ward 9, Bed 12") is kept.

Tehsil, district, city, state and PIN columns are never blanked here: they are what generalization keeps.
Medical collisions avoided on purpose: "Gram stain/positive", "5 ग्राम" (grams), "colony count",
"house surgeon", "road traffic accident", "heart block", "area" (BSA).
"""
from __future__ import annotations

import regex as re

from ..contracts import PIIType, Span, Unit
from . import lexicon as L
from .base import Collector

# ---- column meanings
_PART_HDR = re.compile(
    r"(?<![a-z])(?:village|vill|gaon|gaanv|gaav|gaon|gram|graam|mauza|mouza|majra|dehat|basti|mohall?a|mohallah|muhall?a|"
    r"locality|colony|tola|sector|neighbou?rhood|house|hno|h\s*no|makaa?n|ghar\s*(?:no|sankhya)|flat|plot|door|landmark|nishani|"
    r"nishaan|street|gali|lane|road|marg)(?![a-z])|"
    r"ग्राम|गाँव|गांव|गाव|मौजा|मोहल्ला|कॉलोनी|कालोनी|बस्ती|टोला|मकान|घर\s*(?:नं|सं)|गली|मार्ग|सड़क|लैंडमार्क|पहचान|निकट",
    re.I)
_NOT_PART_HDR = re.compile(
    r"tehsil|tahsil|taluk|district|distt|jila|zila|city|town|state|pin|zip|postal|date|doctor|hospital|ward\s*(?:name|type)|"
    r"तहसील|जिला|जनपद|शहर|राज्य|पिन|तारीख|डॉ", re.I)

# ---- labels in text
_LABEL_WORDS = (
    r"village|vill\.?|gaon|gaanv|gaav|mauza|mouza|majra|mohall?a|mohallah|muhall?a|locality|colony|basti|tola|landmark|"
    r"house\s*no\.?|h\.?\s?no\.?|makaa?n\s*(?:no\.?|number|sankhya)?|gali|street|"
    r"ग्राम|गाँव|गांव|गाव|मौजा|मोहल्ला|कॉलोनी|कालोनी|बस्ती|टोला|मकान\s*(?:नं\.?|सं\.?|संख्या)?|गली|लैंडमार्क|पहचान"
)
_LABELLED = re.compile(rf"(?<![\p{{L}}\p{{M}}\d])(?:{_LABEL_WORDS})\s*[:\-–=]\s*", re.I)
# English "gram" only with a colon and a capitalised value ("Gram: Rampur"), never "Gram stain / Gram positive"
_GRAM_EN = re.compile(r"(?<![\p{L}\d])(?i:gram)\s*:\s*(?=\p{Lu})")
# where a labelled value stops: segment ends, or the next address label begins
_STOP = re.compile(
    r"[,;|\n]|\s{2,}|\s(?:tehsil|tahsil|teh\.?|distt?\.?|district|jila|zila|post|p\.?o\.?|thana|pin|block|"
    r"तहसील|जिला|पोस्ट|थाना|पिन|ब्लॉक)\b|\s[\p{L}\p{M}.]+\s*:", re.I)
_MAX_VALUE = 48

# house numbers written with a Hindi / Hinglish marker and no colon: "Makan No. 41", "मकान नं. 41", "Ghar No 7/2"
_HOUSE_MARK = re.compile(
    r"(?<![\p{L}\p{M}])(?:makaa?n|ghar|मकान|घर)\s*(?:no\.?|number|nambar|sankhya|नं\.?|नंबर|संख्या|सं\.?)\s*[:\-#.]?\s*"
    r"[A-Za-z]?\d{1,5}(?:\s*[/\-]\s*[A-Za-z0-9]{1,4})?[A-Za-z]?(?![\d])", re.I)

_WARD = re.compile(r"(?<![\p{L}\p{M}])(?:ward|वार्ड)\s*(?:no\.?|नं\.?|सं\.?)?\s*[:\-]?\s*\d{1,3}(?![\d/])", re.I)
_ADDR_CUE = re.compile(
    r"(?<![\p{L}])(?:h\.?\s?no|house|mohall?a|muhall?a|tehsil|tahsil|distt?|district|village|gaon|vill|post|c\s*/\s*o|s\s*/\s*o|"
    r"w\s*/\s*o|d\s*/\s*o|address|addr|pata|residence|r\s*/\s*o|landmark|near|colony|nagar|pin)(?![\p{L}])|"
    r"पता|मकान|मोहल्ला|तहसील|जिला|ग्राम|गाँव|गांव|पोस्ट|निवासी|के\s+पास|पिन", re.I)
_HOSP_WARD_AFTER = re.compile(r"\s*(?:\(|,\s*bed|\s*-\s*bed|bed\b|\s*(?:medicine|surgery|icu|nicu|picu|ortho|gynae?|paed|ent|"
                              r"pulmo|cardio|neuro|onco|general|male|female|private|emergency))", re.I)


def _clinical_value(v: str) -> bool:
    words = re.findall(r"[\p{L}\p{M}]+", v)
    return bool(words) and all(L.is_clinical(w) or L.is_drug(w) or L.is_common(w) for w in words)


class AddressFieldDetector:
    name = "address_fields"

    def detect(self, unit: Unit) -> list[Span]:
        col = Collector(unit, self.name)
        text = unit.norm.text
        stripped = text.strip()
        if not stripped:
            return col.spans
        hdr = unit.header

        # 1. whole cell when the column means an address part
        if hdr and _PART_HDR.search(hdr) and not _NOT_PART_HDR.search(hdr) and len(stripped) <= 120 \
                and re.search(r"[\p{L}\d]", stripped):
            s0 = text.index(stripped[0])
            col.add(s0, s0 + len(stripped), PIIType.ADDRESS, 0.85)
            return col.spans

        # 2. "label: value"
        for rx in (_LABELLED, _GRAM_EN):
            for m in rx.finditer(text):
                a = m.end()
                stop = _STOP.search(text, a)
                b = stop.start() if stop else len(text)
                b = min(b, a + _MAX_VALUE)
                value = text[a:b].rstrip(" .-")
                if not value or not re.search(r"[\p{L}\d]", value) or _clinical_value(value):
                    continue
                col.add(a, a + len(value), PIIType.ADDRESS, 0.85)

        # 3. house number with a Hindi / Hinglish marker
        for m in _HOUSE_MARK.finditer(text):
            col.add(m.start(), m.end(), PIIType.ADDRESS, 0.85)

        # 4. municipal ward inside an address line
        for m in _WARD.finditer(text):
            ls = text.rfind("\n", 0, m.start()) + 1
            le = text.find("\n", m.end())
            line = text[ls: le if le >= 0 else len(text)]
            rest = line.replace(m.group(), " ", 1)
            if _HOSP_WARD_AFTER.match(text, m.end()):
                continue
            if (hdr and re.search(r"addr|pata|पता|line|residence", hdr, re.I)) or _ADDR_CUE.search(rest):
                col.add(m.start(), m.end(), PIIType.ADDRESS, 0.85)
        return col.spans
