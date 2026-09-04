"""Client-side upload validation: size caps + magic-byte sniffing.

Base64 uploads are validated *before* they are forwarded to BMONI's identity
or verification providers: decode failure, oversize files and a mismatch
between the declared filename extension and the actual file magic bytes are
all rejected here. Only JPEG, PNG and PDF are accepted.
"""

from __future__ import annotations

import base64
from typing import Literal

UPLOAD_TYPE = Literal["jpeg", "png", "pdf"]

_MAGIC: dict[str, bytes] = {
    "jpeg": b"\xff\xd8\xff",
    "png": b"\x89PNG\r\n\x1a\n",
    "pdf": b"%PDF-",
}

_EXT_TO_TYPE: dict[str, str] = {
    "jpg": "jpeg",
    "jpeg": "jpeg",
    "png": "png",
    "pdf": "pdf",
}

# Content types sent upstream, keyed by sniffed type.
CONTENT_TYPES = {
    "jpeg": "image/jpeg",
    "png": "image/png",
    "pdf": "application/pdf",
}


def sniff_type(content: bytes) -> str | None:
    """Return 'jpeg' | 'png' | 'pdf' from magic bytes, or None if unknown."""
    if content.startswith(_MAGIC["jpeg"]):
        return "jpeg"
    if content.startswith(_MAGIC["png"]):
        return "png"
    if content.startswith(_MAGIC["pdf"]):
        return "pdf"
    return None


def validate_upload(
    file_base64: str,
    *,
    filename: str = "upload.bin",
    max_mb: float = 5.0,
    allowed_types: set[str] | None = None,
) -> tuple[bytes, str]:
    """Validate and decode a base64 upload.

    Returns ``(content_bytes, content_type)`` where content_type is derived
    from the sniffed magic bytes (never from the caller-supplied filename).

    Raises:
        ValueError: base64 is malformed, the file exceeds ``max_mb``, magic
            bytes are unrecognized, or the type is not in ``allowed_types``.
    """
    allowed = allowed_types or {"jpeg", "png", "pdf"}
    try:
        content = base64.b64decode(file_base64, validate=False)
    except Exception as exc:  # pragma: no cover - b64decode is tolerant
        raise ValueError("file content must be valid base64") from exc

    if not content:
        raise ValueError("file content is empty")

    max_bytes = int(max_mb * 1024 * 1024)
    if len(content) > max_bytes:
        raise ValueError(
            f"file exceeds the {max_mb:g} MB upload limit "
            f"({len(content)} bytes decoded)"
        )

    kind = sniff_type(content)
    if kind is None:
        raise ValueError(
            "file type could not be verified from its magic bytes; "
            "expected JPEG, PNG or PDF"
        )
    if kind not in allowed:
        raise ValueError(
            f"file type '{kind}' is not allowed here (allowed: "
            f"{', '.join(sorted(allowed))})"
        )

    # Optional: cross-check the declared extension against the magic bytes so
    # a misleading filename (e.g. "id.png" holding a PDF) is caught early.
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    declared = _EXT_TO_TYPE.get(ext)
    if declared and declared != kind:
        raise ValueError(
            f"filename extension '.{ext}' does not match the file's actual "
            f"type ({kind}); refusing to send"
        )

    return content, CONTENT_TYPES[kind]
