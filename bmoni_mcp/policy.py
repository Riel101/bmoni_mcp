"""HITL + role policy: which tools need a human, and who may call them.

This is the classification inventory agreed in the security review. Tools
that move money, are irreversible/control-changing, or are partner/admin
writes require a human-approved, attributable approval before dispatch. Reads
and protective actions do not. Everything is overridable by explicit operator
knobs - the defaults are strict.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

RISK_SAFE = "safe"
RISK_GRAY = "gray"
RISK_HITL = "hitl"
RISK_ADMIN = "admin"
ROLE_USER = "user"
ROLE_ADMIN = "admin"

# -- partner/admin role: hidden from tools/list, rejected for non-admins -----
ADMIN_PREFIXES = ("bmoni_webhooks_", "bmoni_employer_", "bmoni_approvals_")

# Admin tools that ALSO move money / reconfigure data flow (need approval).
ADMIN_WRITES = frozenset(
    {
        "bmoni_webhooks_register_config",
        "bmoni_webhooks_update_config",
        "bmoni_webhooks_rotate_secret",
        "bmoni_employer_invite_employee",
        "bmoni_employer_batch_upsert",
        "bmoni_employer_offboard",
    }
)

# HITL required - moves money.
HITL_MONEY = frozenset(
    {
        "bmoni_money_send_named",
        "bmoni_money_send_account",
        "bmoni_money_offramp_nigeria",
        "bmoni_money_withdraw_nigeria_bank",
        "bmoni_money_withdraw_crypto",
        "bmoni_money_withdraw_card",
        "bmoni_money_sepa_prepare",
        "bmoni_money_sepa_complete",
        "bmoni_money_latam_cash_send",
        "bmoni_money_create_bank_payout",
        "bmoni_money_submit_signature",
        "bmoni_money_create_proposal",
        "bmoni_fund_card",
        "bmoni_cards_set_limits",
    }
)

# HITL required - harmful / irreversible / control-changing.
HITL_HARMFUL = frozenset(
    {
        "bmoni_cards_deactivate",
        "bmoni_cards_sensitive_data",
        "bmoni_cards_set_pin",
        "bmoni_cards_reset_pin",
        "bmoni_cards_create",
        "bmoni_bank_accounts_add_nigeria_withdrawal",
        "bmoni_bank_accounts_deactivate_deposit_eu",
        "bmoni_bank_accounts_deactivate_nigeria_withdrawal",
        "bmoni_rails_link_vba_nigeria",
        "bmoni_rails_link_vba_eu",
        "bmoni_rails_link_vba_usd",
    }
)

# Gray: default config-safe, operator can widen via BMONI_HITL_GRAY=1.
GRAY_TOOLS = frozenset(
    {
        "bmoni_kyc_activate",
        "bmoni_kyc_retry",
        "bmoni_kyc_upload_identification",
        "bmoni_kyc_upload_proof_of_address",
        "bmoni_kyc_upload_biometric",
        "bmoni_rails_start_nigeria",
        "bmoni_rails_start_canada",
        "bmoni_rails_start_monerium",
        "bmoni_rails_start_mexico",
        "bmoni_rails_start_usa",
        "bmoni_rails_provision_usd_vba",
        "bmoni_cards_request_activation_otp",
        "bmoni_cards_confirm_activation_otp",
        "bmoni_money_eu_kyc",
        "bmoni_wallets_create_managed",
        "bmoni_users_create",
    }
)

# Conditional tools whose risk depends on the arguments.
_ACTIVATE_CARD_STATUS = frozenset({"ACTIVE", "active"})


@dataclass
class Analysis:
    """Policy verdict for a single tool invocation."""

    tool: str
    role: str = ROLE_USER  # ROLE_USER | ROLE_ADMIN
    risk: str = RISK_SAFE  # RISK_SAFE | RISK_GRAY | RISK_HITL | RISK_ADMIN
    requires_approval: bool = False
    auto_approved: bool = False
    reason: str = field(default="read/informational - no approval needed")

    @property
    def admin_only(self) -> bool:
        return self.role == ROLE_ADMIN

    @property
    def blocked_by_read_only(self) -> bool:
        """Writes are refused outright in read-only mode.

        Admin *reads* (e.g. webhook config / employee list) are GETs and stay
        allowed; admin writes and every user-side write are blocked.
        """
        if self.risk in (RISK_HITL, RISK_GRAY):
            return True
        if self.risk == RISK_ADMIN:
            return self.tool in ADMIN_WRITES
        return False


def is_admin_role_tool(tool: str) -> bool:
    return tool.startswith(ADMIN_PREFIXES)


def analyze(tool: str, arguments: dict[str, Any] | None, settings) -> Analysis:
    """Classify one tool invocation.

    ``settings`` exposes the operator knobs (``auto_approve_tools``,
    ``hitl_gray``) and is duck-typed so tests may pass a lightweight stub.
    """
    arguments = arguments or {}
    reason = ""

    role = ROLE_ADMIN if is_admin_role_tool(tool) else ROLE_USER

    # Auto-approve exceptions (operator widening; empty by default).
    auto_approved = tool in getattr(settings, "auto_approve_tools", [])

    if is_admin_role_tool(tool):
        risk = RISK_ADMIN
        if tool in ADMIN_WRITES:
            reason = "partner/admin write (webhook redirect or employer change)"
        else:
            reason = "partner/admin read - admin role required"
    elif tool in HITL_MONEY:
        risk = RISK_HITL
        reason = "moves money"
    elif tool in HITL_HARMFUL:
        risk = RISK_HITL
        reason = "irreversible / control-changing / exposes card secrets"
    elif tool == "bmoni_cards_set_status":
        if str(arguments.get("status", "")).upper() in _ACTIVATE_CARD_STATUS:
            risk = RISK_HITL
            reason = "unfreezing a card (ACTIVE) is a control change"
        else:
            risk = RISK_SAFE
            reason = "freezing a card (BLOCKED) is protective"
    elif tool in GRAY_TOOLS:
        risk = RISK_GRAY
        reason = (
            "gray action - config-safe by default; widen with BMONI_HITL_GRAY=1 "
            "or BMONI_AUTO_APPROVE_TOOLS"
        )
    else:
        risk = RISK_SAFE
        reason = "read/informational - no approval needed"

    if risk == RISK_HITL:
        requires_approval = True
    elif risk == RISK_ADMIN:
        requires_approval = tool in ADMIN_WRITES
    elif risk == RISK_GRAY:
        requires_approval = bool(getattr(settings, "hitl_gray", False))
    else:
        requires_approval = False
    if auto_approved:
        requires_approval = False

    return Analysis(
        tool=tool,
        role=role,
        risk=risk,
        requires_approval=requires_approval,
        auto_approved=auto_approved,
        reason=reason,
    )
