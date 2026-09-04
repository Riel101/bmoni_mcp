"""Tool groups for the BMONI MCP server."""

from . import (
    approvals_tools,
    bank_accounts,
    cards,
    employer,
    fund,
    info,
    kyc,
    money,
    rails,
    users,
    wallets,
    webhooks,
)

TOOL_GROUPS: list[tuple[str, list]] = [
    ("users", users.TOOLS),
    ("kyc", kyc.TOOLS),
    ("wallets", wallets.TOOLS),
    ("rails", rails.TOOLS),
    ("fund", fund.TOOLS),
    ("money", money.TOOLS),
    ("info", info.TOOLS),
    ("bank_accounts", bank_accounts.TOOLS),
    ("cards", cards.TOOLS),
    ("employer", employer.TOOLS),
    ("webhooks", webhooks.TOOLS),
    ("approvals", approvals_tools.TOOLS),
]


def all_tools() -> list:
    tools: list = []
    for _, group in TOOL_GROUPS:
        tools.extend(group)
    return tools
