"""Audit trail.

Every tool invocation (and every step of the approval lifecycle) can be
recorded as a JSONL line to a file or stdout. Records are off by default
(``BMONI_AUDIT_LOG`` unset). Arguments are always redacted; result content is
only included when ``BMONI_AUDIT_LOG_SENSITIVE=1`` (default).
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any

from .redact import redact

_audit: AuditLogger | None = None


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AuditLogger:
    """Append JSONL audit records to a file, or stdout when path == "stdout"."""

    def __init__(self, path: str, *, sensitive: bool = True) -> None:
        self.path = path.strip()
        self.sensitive = sensitive

    @property
    def enabled(self) -> bool:
        return bool(self.path)

    def record(
        self,
        *,
        event: str,
        principal: str | None,
        tool: str | None,
        outcome: str,
        fields: dict[str, Any] | None = None,
    ) -> None:
        if not self.enabled:
            return
        entry: dict[str, Any] = {
            "ts": _iso(),
            "event": event,
            "principal": principal,
            "tool": tool,
            "outcome": outcome,
        }
        for key, value in (fields or {}).items():
            if key == "result" and not self.sensitive:
                entry[key] = "[REDACTED]"
            elif key == "args":
                entry[key] = redact(value)
            else:
                entry[key] = redact(value)
        line = json.dumps(entry, ensure_ascii=False, default=str)
        try:
            if self.path == "stdout":
                print(line, file=sys.stdout, flush=True)
            else:
                _append_line(self.path, line)
        except OSError:  # never let auditing break a tool call
            return

    def close(self) -> None:
        global _audit
        _audit = None


def _append_line(path: str, line: str) -> None:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def set_audit(audit: AuditLogger | None) -> None:
    global _audit
    _audit = audit


def get_audit() -> AuditLogger | None:
    return _audit


def audit_record(
    *,
    event: str,
    principal: str | None = None,
    tool: str | None = None,
    outcome: str = "ok",
    fields: dict[str, Any] | None = None,
) -> None:
    """Record to the current audit logger (no-op when disabled)."""
    audit = get_audit()
    if audit is not None:
        audit.record(
            event=event, principal=principal, tool=tool, outcome=outcome, fields=fields
        )


# Re-exported timestamp helper for consumers that want ms-resolution expiry.
def now_epoch() -> float:
    return time.time()
