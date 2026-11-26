"""AES-256-GCM vault (minimal). Teammate task: envelope encryption, key rotation, audit trail.

Blob layout: 1-byte version | 12-byte nonce | ciphertext+tag. `context` is bound as AAD.
"""
from __future__ import annotations

import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_VERSION = b"\x01"


class AesGcmVault:
    def __init__(self, key: bytes):
        if len(key) != 32:
            raise ValueError("bad key length")
        self._aes = AESGCM(key)

    def encrypt(self, data: bytes, context: bytes = b"") -> bytes:
        nonce = os.urandom(12)
        return _VERSION + nonce + self._aes.encrypt(nonce, data, context)

    def decrypt(self, blob: bytes, context: bytes = b"") -> bytes:
        if not blob or blob[:1] != _VERSION or len(blob) < 29:
            raise ValueError("bad blob")
        return self._aes.decrypt(blob[1:13], blob[13:], context)
