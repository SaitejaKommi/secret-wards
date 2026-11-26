"""Keyed pseudonyms and per-patient date shifts. Both derive from the pseudonym key / date key
(kept outside the data), so they are stable across runs and not reversible without the key."""
from __future__ import annotations

from ..config import Config
from ..security.keys import Keys, hmac_hex


def make_pseudonym(keys: Keys, anchor: str) -> str:
    return "PT-" + hmac_hex(keys.pseudonym, "patient", anchor, n=12).upper()


def shift_days(keys: Keys, cfg: Config, pseudonym: str) -> int:
    """One shift per patient, never 0, within +/- [min, max] days; preserves every interval."""
    h = int(hmac_hex(keys.date, "shift", pseudonym, n=12), 16)
    width = cfg.date_shift_max_days - cfg.date_shift_min_days + 1
    mag = cfg.date_shift_min_days + h % width
    return -mag if (h >> 40) & 1 else mag
