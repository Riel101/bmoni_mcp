"""FastMCP middleware that enforces the security contract.

Every ``tools/call`` runs through: principal resolution -> scope pinning ->
role gate -> rate limit -> HITL approval gate -> audit -> dispatch. ``tools/
list`` hides admin tools from non-admin principals.

This is one of the two choke points (the other is ``BmoniClient.request``);
no tool can reach the BMONI API without passing through here when the server
is run through a transport.
"""

from __future__ import annotations

import json
import time
from typing import Any

from fastmcp.server.middleware import Middleware

from . import audit as audit_mod
from . import policy as policy_mod
from .approvals import ApprovalManager, ApprovalQuotaError
from .authn import Principal, resolve_principal
from .config import Settings
from .limits import ConcurrencyLimiter, RateLimiter, tool_weight
from .redact import redact

# Tools that carry no BMONI user context and are safe for any caller
# (including an unauthenticated stdio session / pre-auth probes).
GLOBAL_PUBLIC_TOOLS = frozenset(
    {
        "bmoni_info_health",
        "bmoni_wallets_supported_currencies",
        "bmoni_fund_supported_assets",
        "bmoni_info_location_countries",
        "bmoni_info_location_country",
        "bmoni_info_location_subdivisions",
        "bmoni_info_location_cities",
    }
)

# These manage the HITL store only - never a BMONI call - so read-only mode
# must not block them.
_ADMIN_ONLY_LOCAL_PREFIX = "bmoni_approvals_"


class EnforcementMiddleware(Middleware):
    """Middleware enforcing the security contract at the transport choke point."""

    def __init__(
        self,
        *,
        settings: Settings,
        approvals: ApprovalManager,
        rate_limiter: RateLimiter,
        concurrency: ConcurrencyLimiter,
    ) -> None:
        self.settings = settings
        self.approvals = approvals
        self.rate_limiter = rate_limiter
        self.concurrency = concurrency

    # -- result helpers -----------------------------------------------------
    @staticmethod
    def _error_result(message: str) -> Any:
        from mcp_types import CallToolResult, TextContent

        return CallToolResult(
            content=[TextContent(type="text", text=message)], is_error=True
        )

    @staticmethod
    def _approval_required_result(record) -> Any:
        from mcp_types import CallToolResult, TextContent

        payload = {
            "status": "approval_required",
            "message": (
                "This action needs a human-approved approval before it runs. "
                "Relay the approval below to your user; once APPROVED, repeat "
                "the identical call."
            ),
            "approval": record.as_public_dict(),
        }
        return CallToolResult(
            content=[
                TextContent(type="text", text=json.dumps(payload, default=str))
            ],
            structured_content=payload,
            is_error=False,
        )

    # -- shared gate helpers ------------------------------------------------
    def _audit(
        self,
        *,
        event: str,
        principal: Principal,
        tool: str | None,
        outcome: str,
        fields: dict[str, Any] | None = None,
    ) -> None:
        audit = audit_mod.get_audit()
        if audit is not None:
            audit.record(
                event=event,
                principal=principal.label(),
                tool=tool,
                outcome=outcome,
                fields=fields,
            )

    def _scope_check(self, tool: str, arguments: dict, principal: Principal) -> str | None:
        """Return an error message when the call violates user scoping."""
        if not principal.authenticated and tool not in GLOBAL_PUBLIC_TOOLS:
            return (
                "authentication required: no principal is bound. For stdio set "
                "BMONI_SCOPED_USER_ID; for http/sse present a bearer token whose "
                "'sub' is the BMONI user id."
            )
        if principal.role == policy_mod.ROLE_ADMIN:
            return None
        user_arg = arguments.get("user_id")
        if user_arg is not None and str(user_arg) != principal.subject:
            return (
                f"forbidden: this session is scoped to user "
                f"'{principal.subject}', not '{user_arg}'"
            )
        return None

    # -- tools/call ---------------------------------------------------------
    async def on_call_tool(self, context, call_next) -> Any:
        from mcp_types import CallToolResult

        params = context.message
        tool: str = params.name
        arguments: dict[str, Any] = params.arguments or {}
        principal = resolve_principal()

        analysis = policy_mod.analyze(tool, arguments, self.settings)

        if not self._is_registered_tool(tool):
            return await call_next(context)

        # Role gate first (admin tools are admin-only).
        if analysis.role == policy_mod.ROLE_ADMIN and not principal.is_admin:
            message = (
                f"forbidden: '{tool}' is an admin tool and this principal "
                f"('{principal.label()}') is not an admin."
            )
            self._audit(
                event="tool.denied",
                principal=principal,
                tool=tool,
                outcome="denied_admin_role",
                fields={"args": redact(arguments)},
            )
            return self._error_result(message)

        # Per-user scoping.
        scope_error = self._scope_check(tool, arguments, principal)
        if scope_error:
            self._audit(
                event="tool.denied",
                principal=principal,
                tool=tool,
                outcome="denied_scope",
                fields={"args": redact(arguments)},
            )
            return self._error_result(f"forbidden: {scope_error}")

        # Rate limit.
        weight = tool_weight(tool)
        allowed, retry_after = self.rate_limiter.allow(principal.label(), weight=weight)
        if not allowed:
            message = (
                f"rate limit exceeded for '{principal.label()}'. "
                f"Retry after {retry_after:.1f}s."
            )
            self._audit(
                event="tool.denied",
                principal=principal,
                tool=tool,
                outcome="denied_rate_limit",
                fields={},
            )
            return self._error_result(message)

        # Read-only short-circuit for writes.
        if (
            self.settings.read_only
            and analysis.blocked_by_read_only
            and not tool.startswith(_ADMIN_ONLY_LOCAL_PREFIX)
        ):
            message = (
                f"'{tool}' is not allowed: the server is in read-only mode "
                f"(BMONI_READ_ONLY=1)."
            )
            self._audit(
                event="tool.denied",
                principal=principal,
                tool=tool,
                outcome="denied_read_only",
                fields={},
            )
            return self._error_result(message)

        # HITL gate.
        if analysis.requires_approval:
            blocked = self.approvals.is_blocked_by_denial(
                principal.label(), tool, arguments
            )
            if blocked is not None:
                until = blocked.denied_until or 0
                message = (
                    f"denied: this exact call was rejected by an approver"
                    + (f" ({blocked.reason})" if blocked.reason else "")
                    + f". Retry after {max(until - time.time(), 0):.0f}s."
                )
                self._audit(
                    event="tool.denied",
                    principal=principal,
                    tool=tool,
                    outcome="denied_cooldown",
                    fields={"args": redact(arguments), "approval_id": blocked.id},
                )
                return self._error_result(message)

            approved = self.approvals.matching_approved(
                principal.label(), tool, arguments
            )
            if approved is not None:
                try:
                    self.approvals.consume(approved.id, by=f"tool:{tool}")
                except Exception:
                    return self._error_result(
                        "approval could not be consumed; request it again"
                    )
                self._audit(
                    event="tool.executing",
                    principal=principal,
                    tool=tool,
                    outcome="approved_execution",
                    fields={"args": redact(arguments), "approval_id": approved.id},
                )
                return await self._dispatch(
                    context, call_next, tool, arguments, principal
                )

            pending = self.approvals.find_pending(principal.label(), tool, arguments)
            if pending is None:
                try:
                    pending = self.approvals.create_pending(
                        principal.label(), tool, arguments, analysis.risk
                    )
                except ApprovalQuotaError as exc:
                    self._audit(
                        event="tool.denied",
                        principal=principal,
                        tool=tool,
                        outcome="denied_pending_quota",
                        fields={"args": redact(arguments)},
                    )
                    return self._error_result(str(exc))
            else:
                self._audit(
                    event="approval.pending_again",
                    principal=principal,
                    tool=tool,
                    outcome="pending",
                    fields={"approval_id": pending.id},
                )
            return self._approval_required_result(pending)

        # Not harmful / protective: dispatch straight away.
        return await self._dispatch(context, call_next, tool, arguments, principal)

    async def _dispatch(self, context, call_next, tool, arguments, principal) -> Any:
        started = time.monotonic()
        outcome = "ok"
        result_snippet: str | None = None
        async with self.concurrency.guard():
            try:
                result = await call_next(context)
            except Exception as exc:  # audit + re-raise for FastMCP to mask
                self._audit(
                    event="tool.call",
                    principal=principal,
                    tool=tool,
                    outcome="error",
                    fields={"args": redact(arguments), "error": str(exc)[:500]},
                )
                raise
        if hasattr(result, "is_error") and getattr(result, "is_error"):
            outcome = "error"
            result_snippet = self._result_text(result)
        self._audit(
            event="tool.call",
            principal=principal,
            tool=tool,
            outcome=outcome,
            fields={
                "args": redact(arguments),
                "duration_ms": int((time.monotonic() - started) * 1000),
                "result": result_snippet,
            },
        )
        return result

    @staticmethod
    def _result_text(result: Any) -> str | None:
        content = getattr(result, "content", None)
        if isinstance(content, (list, tuple)):
            parts = []
            for block in content:
                text = getattr(block, "text", None)
                if text:
                    parts.append(str(text))
            snippet = " | ".join(parts)
            return snippet[:1000] if snippet else None
        return None

    # -- tools/list ---------------------------------------------------------
    async def on_list_tools(self, context, call_next) -> Any:
        tools = await call_next(context)
        principal = resolve_principal()
        if principal.is_admin:
            return tools
        filtered = [t for t in tools if not _is_admin_tool(t)]
        return filtered

    @staticmethod
    def _is_registered_tool(tool: str) -> bool:
        from .server import tool_names as _all_names

        names = getattr(EnforcementMiddleware, "_registered", None)
        if names is None:
            names = set(_all_names())
            EnforcementMiddleware._registered = names
        return tool in names


def _is_admin_tool(tool: Any) -> bool:
    name = getattr(tool, "name", None)
    if not isinstance(name, str):
        return False
    from . import policy as p

    return name.startswith(p.ADMIN_PREFIXES)
