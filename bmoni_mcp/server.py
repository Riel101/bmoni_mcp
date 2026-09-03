"""FastMCP server that exposes BMONI Embedded API capabilities as tools."""

from __future__ import annotations

from fastmcp import FastMCP

from . import __version__
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
- bmoni_webhooks_*   webhook configuration
- bmoni_employer_*   employee invitations (employer link)

Configuration is read from the environment: BMONI_BASE_URL (API host) and
BMONI_API_KEY (partner key, sent as x-api-key). Both are required before
any tool can call the API.

Typical agent flow: bmoni_users_create -> bmoni_wallets_owner_proof_challenge
+ bmoni_wallets_create_managed -> bmoni_kyc_update_profile +
bmoni_kyc_upload_identification -> bmoni_kyc_activate ->
bmoni_rails_start_* / bmoni_rails_provision_usd_vba ->
bmoni_fund_deposit_crypto -> bmoni_money_send_account.
"""


def build_server() -> FastMCP:
    mcp = FastMCP(
        SERVER_NAME,
        instructions=_INSTRUCTIONS,
        version=__version__,
    )
    tools = all_tools()
    for fn in tools:
        mcp.add_tool(fn)
    return mcp


def tool_names() -> list[str]:
    """Names of every registered tool (without creating a server)."""
    return [getattr(fn, "__name__", str(fn)) for fn in all_tools()]
