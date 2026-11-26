"""Key files: generated locally, never printed, never committed (keys/ is gitignored).

Four independent 32-byte keys so that a leak of one does not unlock the others:
  docid.key      doc ids / file refs / hospital labels
  pseudonym.key  patient pseudonyms
  date.key       per-patient date shifts
  enc.key        AES-GCM for anything written encrypted
"""
from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass
from pathlib import Path

KEY_NAMES = ("docid", "pseudonym", "date", "enc")


class KeysMissing(Exception):
    pass


@dataclass(frozen=True)
class Keys:
    docid: bytes
    pseudonym: bytes
    date: bytes
    enc: bytes

    def __repr__(self) -> str:
        return "Keys(<hidden>)"

    __str__ = __repr__


def generate_keys(keys_dir: str | Path, overwrite: bool = False) -> list[str]:
    """Create any missing key files. Returns the names created (never the values)."""
    d = Path(keys_dir)
    d.mkdir(parents=True, exist_ok=True)
    made = []
    for n in KEY_NAMES:
        p = d / f"{n}.key"
        if p.exists() and not overwrite:
            continue
        p.write_text(os.urandom(32).hex(), encoding="ascii")
        try:
            os.chmod(p, 0o600)
        except OSError:
            pass
        made.append(n)
    return made


def load_keys(keys_dir: str | Path) -> Keys:
    d = Path(keys_dir)
    vals = {}
    for n in KEY_NAMES:
        p = d / f"{n}.key"
        if not p.is_file():
            raise KeysMissing(n)
        vals[n] = bytes.fromhex(p.read_text(encoding="ascii").strip())
        if len(vals[n]) < 16:
            raise KeysMissing(n)
    return Keys(**vals)


def keys_from_secret(secret: bytes) -> Keys:
    """Derive all four sub-keys from the evaluator's RAKSHA_SECRET (one label per purpose).
    Nothing is read from disk, so the run needs no keys/ folder; a different secret gives unrelated keys."""
    if not secret:
        raise KeysMissing("secret")
    prk = hmac.new(b"secret-wards|kdf|v1", secret, hashlib.sha256).digest()

    def sub(label: bytes) -> bytes:
        return hmac.new(prk, b"secret-wards|" + label + b"|1", hashlib.sha256).digest()

    return Keys(docid=sub(b"docid"), pseudonym=sub(b"pseudonym"), date=sub(b"date"), enc=sub(b"enc"))


def hmac_hex(key: bytes, *parts: str, n: int = 16) -> str:
    """Domain-separated keyed hash of the given parts, hex, first n chars."""
    h = hmac.new(key, digestmod=hashlib.sha256)
    for p in parts:
        b = p.encode("utf-8")
        h.update(len(b).to_bytes(4, "big"))
        h.update(b)
    return h.hexdigest()[:n]
