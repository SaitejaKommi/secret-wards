"""A minimal audit trail for one run: what the system did, in order, without ever holding a value.

Each event is a stage name plus integer counts (files, records, quarantined, repaired fields ...). Events are chained: the MAC of an event covers
the previous MAC, the sequence number, the stage and the counts, using HMAC-SHA256 under a sub-key derived from the run secret. Whoever holds the
secret can verify that no event was removed, reordered or altered after the run; anyone else only sees counts.

The trail lives inside report.json (key "audit"): no extra file, no timestamps (so it is deterministic for a given input and secret), and no
free text: a count that is not an integer, or a stage / key outside a plain identifier shape, is refused with a message that names the TYPE only.
"""
from __future__ import annotations

import json
import re
from typing import Mapping

from ..security.keys import Keys, hmac_hex

_IDENT = re.compile(r"[a-z][a-z0-9_]{0,40}")
VERSION = 1


class AuditError(Exception):
    pass


def _canonical(stage: str, counts: Mapping[str, int]) -> str:
    return json.dumps({"stage": stage, "counts": dict(sorted(counts.items()))}, sort_keys=True, separators=(",", ":"))


class AuditTrail:
    def __init__(self, keys: Keys):
        self._key = keys.docid
        self._head = hmac_hex(self._key, "audit", "genesis", n=32)
        self._events: list[dict] = []

    def record(self, stage: str, **counts: int) -> None:
        if not _IDENT.fullmatch(stage):
            raise AuditError("stage must be a plain identifier")
        clean: dict[str, int] = {}
        for k, v in counts.items():
            if not _IDENT.fullmatch(k):
                raise AuditError("count name must be a plain identifier")
            if isinstance(v, bool) or not isinstance(v, int):
                raise AuditError(f"count must be an int, got {type(v).__name__}")  # type name only: never the value
            clean[k] = v
        seq = len(self._events)
        mac = hmac_hex(self._key, "audit", self._head, str(seq), _canonical(stage, clean), n=32)
        self._events.append({"seq": seq, "stage": stage, "counts": dict(sorted(clean.items())), "mac": mac})
        self._head = mac

    def export(self) -> dict:
        return {"version": VERSION, "algorithm": "HMAC-SHA256 chain (sub-key from the run secret)", "events": list(self._events), "head": self._head}


def verify(audit: Mapping, keys: Keys) -> bool:
    """True if every event's MAC matches the chain under these keys and the head is the last MAC."""
    head = hmac_hex(keys.docid, "audit", "genesis", n=32)
    try:
        for i, ev in enumerate(audit["events"]):
            if ev["seq"] != i:
                return False
            mac = hmac_hex(keys.docid, "audit", head, str(i), _canonical(ev["stage"], ev["counts"]), n=32)
            if mac != ev["mac"]:
                return False
            head = mac
        return audit["head"] == head
    except (KeyError, TypeError):
        return False
