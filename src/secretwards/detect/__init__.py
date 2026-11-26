"""Detection stage: run every detector on a Unit, apply the medical guard, merge."""
from __future__ import annotations

from typing import Sequence

import regex as re

from ..contracts import Detector, MedKind, MedSpan, PIIType, Span, Unit
from . import lexicon as L
from .address import AddressDetector
from .address_fields import AddressFieldDetector
from .india_ids import IndiaIdDetector
from .medical_guard import find_medical
from .merge import merge
from .names import NameDetector
from .rules import RuleDetector
from ..normalize.translit import skeleton


def default_detectors() -> list[Detector]:
    """Teammates: append a CRF detector here (it must implement contracts.Detector)."""
    return [RuleDetector(), AddressDetector(), NameDetector(), IndiaIdDetector(), AddressFieldDetector()]


def detect_unit(unit: Unit, detectors: Sequence[Detector]) -> tuple[list[Span], list[MedSpan]]:
    raw: list[Span] = []
    for d in detectors:
        raw.extend(d.detect(unit))
    meds_norm = find_medical(unit)
    meds_orig = []
    for s, e, k in meds_norm:
        a, b = unit.norm.to_orig(s, e)
        meds_orig.append((a, b, k))
    spans = merge(raw, meds_orig, unit.original)
    medspans = [MedSpan(unit.doc_id, unit.field, a, b, k) for a, b, k in meds_orig]
    return spans, medspans


_WORD = re.compile(r"[\p{L}\p{M}]+")


def propagate_names(units: Sequence[Unit], per_unit: dict[tuple[str | None], list[Span]]) -> dict:
    """Redact other occurrences of detected person-name tokens inside the SAME document.

    A name found once (e.g. in the name column or after 'Patient:') is a strong hint that the same
    token elsewhere in this record is the same person ('rajesh bhaiya', the Devanagari spelling...).
    Tokens that are medical / common words are never propagated.
    """
    toks_lat: set[str] = set()
    toks_dev: set[str] = set()
    keys: set[str] = set()
    for u in units:
        for s in per_unit.get(u.field, []):
            if s.type != PIIType.NAME:
                continue
            for m in _WORD.finditer(u.original[s.start:s.end]):
                w = m.group()
                if len(w) < 3:
                    continue
                if L.is_drug(w) or L.is_clinical(w) or L.is_common(w) or w in L.HI_STOP:
                    continue
                if "ऀ" <= w[0] <= "ॿ":
                    toks_dev.add(w)
                else:
                    toks_lat.add(w.lower())
                k = skeleton(w)
                if len(k) >= 3:
                    keys.add(k)
    extra: dict[str | None, list[Span]] = {}
    if not (toks_lat or toks_dev):
        return extra
    for u in units:
        have = per_unit.get(u.field, [])
        for m in _WORD.finditer(u.original):
            w = m.group()
            if len(w) < 3:
                continue
            hit = (w.lower() in toks_lat) or (w in toks_dev)
            if not hit and "ऀ" <= w[0] <= "ॿ":
                k = skeleton(w)
                hit = len(k) >= 3 and k in keys and w not in L.HI_STOP and not L.is_common(w)
            if not hit and w[0].isalpha() and "ऀ" > w[0]:
                k = skeleton(w)
                hit = len(k) >= 4 and k in keys and not (L.is_drug(w) or L.is_clinical(w) or L.is_common(w)) and w[0].isupper()
            if not hit:
                continue
            a, b = m.start(), m.end()
            if any(s.start < b and a < s.end for s in have):
                continue
            extra.setdefault(u.field, []).append(Span(u.doc_id, u.field, a, b, PIIType.NAME, "propagate", 0.6, ""))
    return extra
