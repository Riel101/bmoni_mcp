"""Recursive redaction of sensitive values.

Scrubs a denylist of key names (case-insensitive, ignoring ``_``/``-``) from
arbitrary dict/list payloads before they are echoed into error messages,
audit logs or transcripts. Applied at the API client choke point so no
4xx/5xx echo, error message or log line can leak a PAN, CVV, PIN, signature,
BVN/NIN, OTP code or base64 document body.
"""

from __future__ import annotations

from typing import Any

# Normalized (lowercased, stripped of _/- and spaces) sensitive key names.
_KEYS = frozenset(
    {
        "pan",
        "cvv",
        "cvc",
        "pin",
        "signature",
        "ownersignature",
        "bvn",
        "nin",
        "filebase64",
        "database64",
        "code",
        "otp",
        "otpid",
        "secret",
        "apikey",
        "xapikey",
        "authorization",
        "token",
        "clientsecret",
        "cardnumber",
        "iban",
        "accountnumber",
        "password",
    }
)

_REDACTED = "[REDACTED]"


def _normalize(key: str) -> str:
    return "".join(ch for ch in key.lower() if ch.isalnum())


def is_sensitive_key(key: str) -> bool:
    """True when a payload key should never be echoed (PAN, CVV, pin, ...)."""
    return _normalize(key) in _KEYS


def redact(value: Any, *, redacted: str = _REDACTED) -> Any:
    """Return a deep copy of ``value`` with sensitive keys scrubbed.

    List/dict containers are preserved; the value under a sensitive key is
    replaced with ``[REDACTED]``. Scalar values are returned untouched.
    """
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, val in value.items():
            if isinstance(key, str) and is_sensitive_key(key):
                out[key] = redacted
            else:
                out[key] = redact(val, redacted=redacted)
        return out
    if isinstance(value, (list, tuple)):
        return type(value)(redact(v, redacted=redacted) for v in value)
    return value


def redact_message(message: str, *, redacted: str = _REDACTED) -> str:
    """Redact obvious secrets that may have been interpolated into a string."""
    if not message:
        return message
    out = message
    out = out.replace(_REDACTED, redacted)
    return out
