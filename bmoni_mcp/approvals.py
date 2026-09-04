"""Human-in-the-loop approval records.

A content-matched, consume-once sqlite store. For every harmful call the
enforcement middleware writes a PENDING record here; a human approver
(separate principal) marks it APPROVED or REJECTED; the agent then repeats
the *identical* call and the middleware matches it on
``(principal, tool, args_hash)``, consumes it once and only then dispatches.

Records persist across restarts (``BMONI_APPROVAL_DB``) and expire by TTL.
Stdlib only.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any

from . import audit as _audit
from .redact import redact

STATUS_PENDING = "PENDING"
STATUS_APPROVED = "APPROVED"
STATUS_REJECTED = "REJECTED"
STATUS_USED = "USED"
STATUS_EXPIRED = "EXPIRED"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS approvals (
    id          TEXT PRIMARY KEY,
    principal   TEXT NOT NULL,
    tool        TEXT NOT NULL,
    args_hash   TEXT NOT NULL,
    risk        TEXT NOT NULL,
    summary     TEXT NOT NULL,
    status      TEXT NOT NULL,
    created_at  REAL NOT NULL,
    expires_at  REAL NOT NULL,
    resolved_at REAL,
    resolved_by TEXT,
    reason      TEXT,
    denied_until REAL
);
CREATE INDEX IF NOT EXISTS idx_approvals_match
    ON approvals (principal, tool, args_hash, status);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals (status);
"""

_AMOUNT_KEYS = (
    "amount",
    "from_amount",
    "price",
    "max_single_transaction_amount",
    "total_daily_limit",
    "supporting_document_id",
)
_CURRENCY_KEYS = (
    "currency",
    "from_currency",
    "to_currency",
    "price_currency",
    "destination_currency",
)
_DEST_KEYS = (
    "to_user_id",
    "destination_address",
    "callback_url",
    "account_number",
    "bank_account_id",
    "card_id",
    "workflow_id",
    "proposal_id",
)


class ApprovalError(Exception):
    """Raised for invalid approval operations (already resolved, expired...)."""


class ApprovalQuotaError(Exception):
    """Raised when a principal has too many pending approvals."""


@dataclass
class ApprovalRecord:
    id: str
    principal: str
    tool: str
    args_hash: str
    risk: str
    summary: str
    status: str
    created_at: float
    expires_at: float
    resolved_at: float | None = None
    resolved_by: str | None = None
    reason: str | None = None
    denied_until: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "principal": self.principal,
            "tool": self.tool,
            "args_hash": self.args_hash,
            "risk": self.risk,
            "summary": self.summary,
            "status": self.status,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "resolved_at": self.resolved_at,
            "resolved_by": self.resolved_by,
            "reason": self.reason,
            "denied_until": self.denied_until,
        }

    def as_public_dict(self) -> dict[str, Any]:
        """Shape returned to the agent when an approval is required."""
        return {
            "id": self.id,
            "tool": self.tool,
            "summary": self.summary,
            "risk": self.risk,
            "status": self.status,
            "expires_at": self.expires_at,
        }


def args_hash(principal: str, tool: str, arguments: dict[str, Any] | None) -> str:
    """Stable hash of the exact (principal, tool, arguments) triple.

    ``arguments`` must be the raw JSON arguments the client sent, so an agent
    that repeats the identical call reproduces the identical hash.
    """
    canonical = json.dumps(
        arguments or {}, sort_keys=True, separators=(",", ":"), default=str
    )
    digest = hashlib.sha256()
    digest.update(principal.encode("utf-8"))
    digest.update(b"\x00")
    digest.update(tool.encode("utf-8"))
    digest.update(b"\x00")
    digest.update(canonical.encode("utf-8"))
    return digest.hexdigest()


def _first(dct: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in dct and dct[key] is not None:
            return dct[key]
    return None


def _deep_first(value: Any, keys: tuple[str, ...]) -> Any:
    """Find the first non-None value under a nested key path."""
    if isinstance(value, dict):
        for key in keys:
            if key in value and value[key] is not None:
                return value[key]
        for nested in value.values():
            found = _deep_first(nested, keys)
            if found is not None:
                return found
    elif isinstance(value, (list, tuple)):
        for item in value:
            found = _deep_first(item, keys)
            if found is not None:
                return found
    return None


def _iban(value: Any) -> str | None:
    """Extract an IBAN from a SEPA counterpart if one is present."""
    if isinstance(value, dict):
        identifier = value.get("identifier")
        if isinstance(identifier, dict) and identifier.get("iban"):
            return str(identifier["iban"])
        for nested in value.values():
            found = _iban(nested)
            if found:
                return found
    elif isinstance(value, (list, tuple)):
        for item in value:
            found = _iban(item)
            if found:
                return found
    return None


def summarize(tool: str, arguments: dict[str, Any] | None) -> str:
    """Human-readable one-line summary for an approval request."""
    arguments = arguments or {}
    parts: list[str] = []

    amount = _deep_first(arguments, _AMOUNT_KEYS)
    if amount is not None:
        parts.append(f"amount={amount}")
    currency = _deep_first(arguments, _CURRENCY_KEYS)
    if currency is not None:
        parts.append(f"currency={currency}")
    dest = _deep_first(arguments, _DEST_KEYS)
    if dest is not None:
        parts.append(f"destination={dest}")
    iban = _iban(arguments)
    if iban:
        parts.append(f"iban={iban}")
    for key in ("reason", "note", "memo", "description"):
        val = _deep_first(arguments, (key,))
        if val is not None and len(str(val)) <= 120:
            parts.append(f"{key}={val}")

    detail = ", ".join(parts)
    return f"{tool} ({detail})" if detail else tool


def _hmac_sign(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


class ApprovalManager:
    """Thread-safe sqlite-backed approval store with optional callbacks."""

    def __init__(
        self,
        *,
        db_path: str,
        ttl_seconds: int = 600,
        deny_cooldown: int = 300,
        max_pending: int = 100,
        callback_url: str = "",
        webhook_secret: str = "",
        audit=None,
    ) -> None:
        self.db_path = db_path
        self.ttl_seconds = ttl_seconds
        self.deny_cooldown = deny_cooldown
        self.max_pending = max_pending
        self.callback_url = callback_url
        self.webhook_secret = webhook_secret
        self.audit = audit
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None
        self._notify_tasks: set = set()

    # -- connection ---------------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            directory = os.path.dirname(self.db_path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            self._conn = sqlite3.connect(
                self.db_path, check_same_thread=False, timeout=30
            )
            self._conn.row_factory = sqlite3.Row
            self._conn.executescript(_SCHEMA)
        return self._conn

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    # -- internals ----------------------------------------------------------
    def _execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        conn = self._connect()
        with self._lock:
            cur = conn.execute(sql, params)
            conn.commit()
            return cur

    def _row_to_record(self, row: sqlite3.Row) -> ApprovalRecord:
        return ApprovalRecord(**dict(row))

    def _now(self) -> float:
        return time.time()

    def _record_audit(
        self, event: str, principal: str | None, tool: str | None, outcome: str, **extra: Any
    ) -> None:
        if self.audit is not None:
            self.audit.record(
                event=event,
                principal=principal,
                tool=tool,
                outcome=outcome,
                fields=extra,
            )

    # -- lifecycle ----------------------------------------------------------
    def create_pending(
        self, principal: str, tool: str, arguments: dict[str, Any] | None, risk: str
    ) -> ApprovalRecord:
        """Create a PENDING approval; raises ApprovalQuotaError over the cap."""
        now = self._now()
        self.expire_overdue()
        with self._lock:
            conn = self._connect()
            count = conn.execute(
                "SELECT COUNT(*) AS c FROM approvals "
                "WHERE principal=? AND status=?",
                (principal, STATUS_PENDING),
            ).fetchone()["c"]
            if count >= self.max_pending:
                raise ApprovalQuotaError(
                    f"too many pending approvals for this principal "
                    f"({self.max_pending}); resolve or wait for one to expire"
                )
            record = ApprovalRecord(
                id=uuid.uuid4().hex,
                principal=principal,
                tool=tool,
                args_hash=args_hash(principal, tool, arguments),
                risk=risk,
                summary=summarize(tool, arguments),
                status=STATUS_PENDING,
                created_at=now,
                expires_at=now + self.ttl_seconds,
            )
            conn.execute(
                "INSERT INTO approvals (id, principal, tool, args_hash, risk, "
                "summary, status, created_at, expires_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    record.id,
                    record.principal,
                    record.tool,
                    record.args_hash,
                    record.risk,
                    record.summary,
                    record.status,
                    record.created_at,
                    record.expires_at,
                ),
            )
            conn.commit()
        self._record_audit(
            "approval.pending",
            principal,
            tool,
            "pending",
            args=redact(arguments or {}),
            summary=record.summary,
        )
        self._notify_new(record)
        return record

    def matching_approved(
        self, principal: str, tool: str, arguments: dict[str, Any] | None
    ) -> ApprovalRecord | None:
        """Return a live APPROVED record for the identical call, if any."""
        now = self._now()
        digest = args_hash(principal, tool, arguments)
        with self._lock:
            conn = self._connect()
            row = conn.execute(
                "SELECT * FROM approvals WHERE principal=? AND tool=? AND "
                "args_hash=? AND status=? AND expires_at > ? "
                "ORDER BY created_at DESC LIMIT 1",
                (principal, tool, digest, STATUS_APPROVED, now),
            ).fetchone()
        if row is None:
            return None
        record = self._row_to_record(row)
        return record

    def find_pending(
        self, principal: str, tool: str, arguments: dict[str, Any] | None
    ) -> ApprovalRecord | None:
        """Return an existing PENDING record for the identical call, if any."""
        now = self._now()
        digest = args_hash(principal, tool, arguments)
        with self._lock:
            conn = self._connect()
            row = conn.execute(
                "SELECT * FROM approvals WHERE principal=? AND tool=? AND "
                "args_hash=? AND status=? AND expires_at > ? "
                "ORDER BY created_at DESC LIMIT 1",
                (principal, tool, digest, STATUS_PENDING, now),
            ).fetchone()
        return self._row_to_record(row) if row is not None else None

    def consume(self, approval_id: str, by: str) -> ApprovalRecord:
        """Mark an APPROVED record USED (consume-once) and return it."""
        now = self._now()
        with self._lock:
            conn = self._connect()
            row = conn.execute(
                "SELECT * FROM approvals WHERE id=?", (approval_id,)
            ).fetchone()
            if row is None:
                raise ApprovalError(f"unknown approval {approval_id}")
            record = self._row_to_record(row)
            if record.status != STATUS_APPROVED:
                raise ApprovalError(
                    f"approval {approval_id} is {record.status}, not APPROVED"
                )
            if record.expires_at <= now:
                conn.execute(
                    "UPDATE approvals SET status=? WHERE id=?",
                    (STATUS_EXPIRED, approval_id),
                )
                conn.commit()
                raise ApprovalError(f"approval {approval_id} has expired")
            conn.execute(
                "UPDATE approvals SET status=?, resolved_at=?, resolved_by=? "
                "WHERE id=?",
                (STATUS_USED, now, by, approval_id),
            )
            conn.commit()
            record.status = STATUS_USED
            record.resolved_at = now
            record.resolved_by = by
        self._record_audit("approval.used", record.principal, record.tool, "used")
        return record

    def approve(self, approval_id: str, by: str) -> ApprovalRecord:
        """Approve a PENDING approval."""
        now = self._now()
        with self._lock:
            conn = self._connect()
            row = conn.execute(
                "SELECT * FROM approvals WHERE id=?", (approval_id,)
            ).fetchone()
            if row is None:
                raise ApprovalError(f"unknown approval {approval_id}")
            record = self._row_to_record(row)
            if record.status != STATUS_PENDING:
                raise ApprovalError(
                    f"approval {approval_id} is {record.status}, not PENDING"
                )
            if record.expires_at <= now:
                conn.execute(
                    "UPDATE approvals SET status=? WHERE id=?",
                    (STATUS_EXPIRED, approval_id),
                )
                conn.commit()
                raise ApprovalError(f"approval {approval_id} has expired")
            conn.execute(
                "UPDATE approvals SET status=?, resolved_at=?, resolved_by=? "
                "WHERE id=?",
                (STATUS_APPROVED, now, by, approval_id),
            )
            conn.commit()
            record.status = STATUS_APPROVED
            record.resolved_at = now
            record.resolved_by = by
        self._record_audit("approval.approved", record.principal, record.tool, "approved", by=by)
        return record

    def reject(
        self, approval_id: str, by: str, reason: str | None = None
    ) -> ApprovalRecord:
        """Reject a PENDING approval and arm the deny cooldown."""
        now = self._now()
        with self._lock:
            conn = self._connect()
            row = conn.execute(
                "SELECT * FROM approvals WHERE id=?", (approval_id,)
            ).fetchone()
            if row is None:
                raise ApprovalError(f"unknown approval {approval_id}")
            record = self._row_to_record(row)
            if record.status != STATUS_PENDING:
                raise ApprovalError(
                    f"approval {approval_id} is {record.status}, not PENDING"
                )
            denied_until = now + self.deny_cooldown
            conn.execute(
                "UPDATE approvals SET status=?, resolved_at=?, resolved_by=?, "
                "reason=?, denied_until=? WHERE id=?",
                (STATUS_REJECTED, now, by, reason, denied_until, approval_id),
            )
            conn.commit()
            record.status = STATUS_REJECTED
            record.resolved_at = now
            record.resolved_by = by
            record.reason = reason
            record.denied_until = denied_until
        self._record_audit(
            "approval.rejected", record.principal, record.tool, "rejected", by=by, reason=reason
        )
        return record

    def is_blocked_by_denial(
        self, principal: str, tool: str, arguments: dict[str, Any] | None
    ) -> ApprovalRecord | None:
        """Return a REJECTED record still inside its deny cooldown, if any."""
        now = self._now()
        digest = args_hash(principal, tool, arguments)
        with self._lock:
            conn = self._connect()
            row = conn.execute(
                "SELECT * FROM approvals WHERE principal=? AND tool=? AND "
                "args_hash=? AND status=? AND denied_until > ? "
                "ORDER BY denied_until DESC LIMIT 1",
                (principal, tool, digest, STATUS_REJECTED, now),
            ).fetchone()
        return self._row_to_record(row) if row is not None else None

    def expire_overdue(self) -> int:
        now = self._now()
        cur = self._execute(
            "UPDATE approvals SET status=? WHERE status IN (?, ?) AND expires_at <= ?",
            (STATUS_EXPIRED, STATUS_PENDING, STATUS_APPROVED, now),
        )
        return max(cur.rowcount, 0)

    def list(self, status: str | None = None, principal: str | None = None) -> list[dict[str, Any]]:
        """List approvals (newest first) as plain dicts for tool output."""
        self.expire_overdue()
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status=?")
            params.append(status)
        if principal:
            clauses.append("principal=?")
            params.append(principal)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(500)
        with self._lock:
            conn = self._connect()
            rows = conn.execute(
                f"SELECT * FROM approvals {where} ORDER BY created_at DESC LIMIT ?",
                tuple(params),
            ).fetchall()
        return [self._row_to_record(r).as_dict() for r in rows]

    # -- notification channel ----------------------------------------------
    def _notify_new(self, record: ApprovalRecord) -> None:
        """Best-effort, HMAC-signed callback to the operator's UI."""
        if not (self.callback_url and self.webhook_secret):
            return
        payload = {
            "type": "approval.pending",
            "approval": {
                "id": record.id,
                "principal": record.principal,
                "tool": record.tool,
                "summary": record.summary,
                "risk": record.risk,
                "status": record.status,
                "expires_at": record.expires_at,
            },
        }
        body = json.dumps(payload, default=str).encode("utf-8")
        signature = _hmac_sign(body, self.webhook_secret)

        async def _send() -> None:
            import httpx

            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    await client.post(
                        self.callback_url,
                        content=body,
                        headers={
                            "Content-Type": "application/json",
                            "X-BMONI-Signature": signature,
                            "X-BMONI-Event": "approval.pending",
                        },
                    )
            except Exception:  # pragma: no cover - best effort
                return

        try:
            import asyncio

            task = asyncio.create_task(_send())
            self._notify_tasks.add(task)
            task.add_done_callback(self._notify_tasks.discard)
        except RuntimeError:  # pragma: no cover - no running loop
            return


# ---------------------------------------------------------------------------
# Module-level singleton so approval MCP tools and the middleware share one
# store. Tests may swap in an in-memory / temp-file manager.
# ---------------------------------------------------------------------------
_manager: ApprovalManager | None = None


def set_manager(manager: ApprovalManager | None) -> None:
    global _manager
    _manager = manager


def get_manager() -> ApprovalManager:
    global _manager
    if _manager is None:
        from .config import get_settings

        settings = get_settings()
        _manager = ApprovalManager(
            db_path=settings.approval_default_db,
            ttl_seconds=settings.approval_ttl_seconds,
            deny_cooldown=settings.approval_deny_cooldown,
            max_pending=settings.approval_max_pending,
            callback_url=settings.approval_callback_url,
            webhook_secret=settings.approval_webhook_secret,
            audit=None,
        )
    return _manager


def reset_manager() -> None:
    global _manager
    if _manager is not None:
        _manager.close()
    _manager = None
