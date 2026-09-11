"""Obfuscation codec for word list blobs (zlib -> xor -> base64).

Obfuscation only — keeps list contents out of casual view on disk and in
any committed blob; the key is right here, so this is not encryption.
Stdlib-only so pack/fetch scripts run without the app venv."""

import base64
import zlib

_LIST_KEY = b"autoclean"
_LIST_MAGIC = b"ACL1:"


def decode_list(data: bytes) -> str:
    if data.startswith(_LIST_MAGIC):
        raw = base64.b64decode(data[len(_LIST_MAGIC):])
        raw = bytes(b ^ _LIST_KEY[i % len(_LIST_KEY)]
                    for i, b in enumerate(raw))
        return zlib.decompress(raw).decode("utf-8")
    return data.decode("utf-8")


def encode_list(text: bytes) -> bytes:
    raw = zlib.compress(text)
    raw = bytes(b ^ _LIST_KEY[i % len(_LIST_KEY)]
                for i, b in enumerate(raw))
    return _LIST_MAGIC + base64.b64encode(raw)
