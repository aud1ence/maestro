from __future__ import annotations

import hashlib
import hmac

import pytest
from fastapi import HTTPException

from app.server import _verify_signature


def sign(secret: str, payload: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def test_verify_signature_ok():
    payload = b'{"hello":"world"}'
    secret = "abc123"
    sig = sign(secret, payload)
    _verify_signature(payload, sig, secret)


def test_verify_signature_fail():
    payload = b'{"hello":"world"}'
    secret = "abc123"

    with pytest.raises(HTTPException) as exc:
        _verify_signature(payload, "sha256=deadbeef", secret)

    assert exc.value.status_code == 401
