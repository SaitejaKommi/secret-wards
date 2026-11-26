"""PII-free logging: only codes, counts, ids and exception TYPE names. Never messages or values."""
from __future__ import annotations

import sys
from typing import TextIO

_stream: TextIO | None = None


def set_stream(stream: TextIO | None) -> None:
    global _stream
    _stream = stream


def log(event: str, **kv: int | str | float) -> None:
    """Log an event. Values must be ints/floats or short identifiers; strings are
    restricted to [A-Za-z0-9_.:-] so that free text can never slip through."""
    parts = [event]
    for k in sorted(kv):
        v = kv[k]
        if isinstance(v, str):
            v = "".join(c for c in v[:40] if c.isalnum() or c in "_.:-")
        parts.append(f"{k}={v}")
    out = _stream if _stream is not None else sys.stderr
    try:
        out.write(" ".join(parts) + "\n")
    except Exception:
        pass


def exc_code(e: BaseException) -> str:
    """Exception class name only. Messages routinely echo record content."""
    return type(e).__name__
