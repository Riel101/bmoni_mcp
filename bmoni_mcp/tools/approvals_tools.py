"""Human-approver tools for the HITL gate.

These are role=admin tools: a separate approver principal (an operator with a
token whose subject is in ``BMONI_ADMIN_SUBJECTS``) lists pending approvals
and resolves them. They never touch the BMONI API - only the local sqlite
approval store - so they keep working even in read-only mode.
"""

from __future__ import annotations

from typing import Optional

from ..approvals import ApprovalError, get_manager


async def bmoni_approvals_list(
    status: Optional[str] = None,
    principal: Optional[str] = None,
    limit: Optional[int] = None,
) -> dict:
    """List human-in-the-loop approval records.

    Args:
        status: Filter by PENDING, APPROVED, REJECTED, USED or EXPIRED.
        principal: Filter by the requesting principal (user id).
        limit: Cap on rows returned (default 50).

    Returns:
        A list of approval records with id, tool, summary, status and expiry.
    """
    manager = get_manager()
    rows = manager.list(status=status, principal=principal)
    if limit is not None:
        rows = rows[: limit]
    return {"approvals": rows, "count": len(rows)}


async def bmoni_approvals_approve(approval_id: str) -> dict:
    """Approve a pending approval so the identical call may execute.

    Args:
        approval_id: Id of the PENDING approval to approve.

    Returns:
        The approved record. The requester must re-issue the exact same call
        within the TTL; it is consumed once and only then dispatched.
    """
    manager = get_manager()
    try:
        record = manager.approve(approval_id, by="approver")
    except ApprovalError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "approval": record.as_dict()}


async def bmoni_approvals_reject(approval_id: str, reason: Optional[str] = None) -> dict:
    """Reject a pending approval and block identical calls for a cooldown.

    Args:
        approval_id: Id of the PENDING approval to reject.
        reason: Why it was rejected (surfaced to the requester).

    Returns:
        The rejected record.
    """
    manager = get_manager()
    try:
        record = manager.reject(approval_id, by="approver", reason=reason)
    except ApprovalError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "approval": record.as_dict()}


TOOLS = [
    bmoni_approvals_list,
    bmoni_approvals_approve,
    bmoni_approvals_reject,
]
