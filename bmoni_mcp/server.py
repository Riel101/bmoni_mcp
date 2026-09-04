"""FastMCP server that exposes BMONI Embedded API capabilities as tools."""

from __future__ import annotations

from fastmcp import FastMCP

from . import __version__
from .approvals import get_manager
from .audit import AuditLogger, set_audit
from .authn import build_auth_provider
from .config import get_settings
from .limits import ConcurrencyLimiter, RateLimiter
from .middleware import EnforcementMiddleware
from .tools import all_tools

SERVER_NAME = "bmoni-mcp"

_INSTRUCTIONS = """\
MCP server for the BMONI Embedded API (wallet + card services).

Tools are grouped by lifecycle stage:
- bmoni_users_*      create users / look them up
- bmoni_kyc_*        verify identity (KYC) and reach activation-readiness
- bmoni_wallets_*    provision & inspect smart (multi-sig) wallets
- bmoni_rails_*      activate regional funding rails (NG/CA/EU/MX/US) + VBAs
- bmoni_fund_*       fund wallets (crypto deposits, card funding, cash)
- bmoni_money_*      move money: sends, proposals+signatures, exchange,
                     withdrawals, offramps, SEPA, bank payouts, LATAM
- bmoni_cards_*      create/manage physical & virtual cards
- bmoni_bank_accounts_*  deposit/withdrawal bank accounts
- bmoni_info_*       platform & location information
- bmoni_webhooks_*   webhook configuration (admin)
- bmoni_employer_*   employee invitations - employer link (admin)
- bmoni_approvals_*  human-in-the-loop approval queue (admin)

Security model: every session is scoped to an authenticated BMONI user (the
bearer token 'sub' for http/sse, or BMONI_SCOPED_USER_ID for stdio). Actions
that move money, are irreversible/control-changing or are partner/admin
writes require a human-approved approval (HITL) - see bmoni_approvals_list /
approve / reject. Money never moves on a purely agent-initiated call.

Typical agent flow: bmoni_users_create -> bmoni_wallets_owner_proof_challenge
+ bmoni_wallets_create_managed -> bmoni_kyc_update_profile +
bmoni_kyc_upload_identification -> bmoni_kyc_activate ->
bmoni_rails_start_* / bmoni_rails_provision_usd_vba ->
bmoni_fund_deposit_crypto -> bmoni_money_send_account (approval-gated).
"""


def build_server() -> FastMCP:
    settings = get_settings()

    mcp = FastMCP(
        SERVER_NAME,
        instructions=_INSTRUCTIONS,
        version=__version__,
        auth=build_auth_provider(settings),
        mask_error_details=True,
        strict_input_validation=True,
    )
    tools = all_tools()
    for fn in tools:
        mcp.add_tool(fn)

    set_audit(AuditLogger(settings.audit_log, sensitive=settings.audit_log_sensitive))
    middleware = EnforcementMiddleware(
        settings=settings,
        approvals=get_manager(),
        rate_limiter=RateLimiter(
            rps=settings.rate_limit_rps, burst=settings.rate_limit_burst
        ),
        concurrency=ConcurrencyLimiter(settings.max_concurrent),
    )
    mcp.add_middleware(middleware)
    return mcp


def tool_names() -> list[str]:
    """Names of every registered tool (without creating a server)."""
    return [getattr(fn, "__name__", str(fn)) for fn in all_tools()]
