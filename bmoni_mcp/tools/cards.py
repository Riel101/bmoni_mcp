"""Tools to create and manage BMONI cards."""

from __future__ import annotations

from typing import Literal, Optional

from ..models import CardCreateInput
from .common import get_client, payload


async def bmoni_cards_create(user_id: str, body: CardCreateInput) -> dict:
    """Create a physical or virtual card linked to a smart wallet.

    Journey A (in-hand): supply ``pan`` for immediate activation.
    Journey B (delivery): omit ``pan`` and provide the delivery fields;
    activate later via OTP.

    Args:
        user_id: BMONI user id (UUID).
        body: Card details (color, name, currency, smartWalletId, type and
            optional BVN/NIN/PAN/delivery fields).

    Returns:
        workflowId, proposalId and feeAmount.
    """
    client = get_client()
    return await client.post(
        f"/v1/users/{user_id}/cards",
        json_body=body.model_dump(exclude_none=True),
    )


async def bmoni_cards_status(user_id: str, workflow_id: str) -> dict:
    """Poll the card creation workflow status.

    Args:
        user_id: BMONI user id (UUID).
        workflow_id: workflowId from bmoni_cards_create.

    Returns:
        Current card creation status.
    """
    client = get_client()
    return await client.get(
        f"/v1/users/{user_id}/cards/status", params={"workflowId": workflow_id}
    )


async def bmoni_cards_sensitive_data(user_id: str, card_id: str, identity_id: str) -> dict:
    """Get sensitive card data (PAN, CVV, expiry, billing).

    Args:
        user_id: BMONI user id (UUID).
        card_id: Card id (UUID).
        identity_id: The card's identity id.

    Returns:
        PAN, CVV, expiry and billing details. Handle with care.
    """
    client = get_client()
    return await client.post(
        f"/v1/users/{user_id}/cards/sensitive-data",
        json_body=payload(cardId=card_id, identityId=identity_id),
    )


async def bmoni_cards_request_activation_otp(
    user_id: str,
    card_id: str,
    channel: Literal["sms", "email"],
    pan: Optional[str] = None,
) -> dict:
    """Request an OTP to activate a delivered physical card.

    Args:
        user_id: BMONI user id (UUID).
        card_id: Card id (UUID).
        channel: sms or email.
        pan: Card PAN (required if not yet activated).

    Returns:
        An otpId to use with the confirm step.
    """
    client = get_client()
    return await client.post(
        f"/v1/users/{user_id}/cards/{card_id}/activate/request",
        json_body=payload(channel=channel, pan=pan),
    )


async def bmoni_cards_confirm_activation_otp(
    user_id: str, card_id: str, otp_id: str, code: str
) -> dict:
    """Confirm the OTP and activate a physical card.

    Args:
        user_id: BMONI user id (UUID).
        card_id: Card id (UUID).
        otp_id: otpId from bmoni_cards_request_activation_otp.
        code: 6-digit OTP code.

    Returns:
        Activation result.
    """
    client = get_client()
    return await client.post(
        f"/v1/users/{user_id}/cards/{card_id}/activate/confirm",
        json_body=payload(otpId=otp_id, code=code),
    )


async def bmoni_cards_set_status(
    user_id: str, card_id: str, status: Literal["ACTIVE", "BLOCKED"]
) -> dict:
    """Freeze (BLOCKED) or unfreeze (ACTIVE) a card.

    Args:
        user_id: BMONI user id (UUID).
        card_id: Card id (UUID).
        status: ACTIVE or BLOCKED.

    Returns:
        Updated card status.
    """
    client = get_client()
    return await client.put(
        f"/v1/users/{user_id}/cards/{card_id}/status", json_body=payload(status=status)
    )


async def bmoni_cards_set_pin(user_id: str, card_id: str, pin: str) -> dict:
    """Set the card PIN.

    Args:
        user_id: BMONI user id (UUID).
        card_id: Card id (UUID).
        pin: 4-digit PIN.

    Returns:
        Result.
    """
    client = get_client()
    return await client.put(
        f"/v1/users/{user_id}/cards/{card_id}/pin", json_body=payload(pin=pin)
    )


async def bmoni_cards_reset_pin(user_id: str, card_id: str, pin: str) -> dict:
    """Reset the card PIN.

    Args:
        user_id: BMONI user id (UUID).
        card_id: Card id (UUID).
        pin: New 4-digit PIN.

    Returns:
        Result.
    """
    client = get_client()
    return await client.post(
        f"/v1/users/{user_id}/cards/{card_id}/reset", json_body=payload(pin=pin)
    )


async def bmoni_cards_transactions(
    user_id: str,
    card_id: str,
    size: Optional[int] = None,
    status: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> dict:
    """List card transactions.

    Args:
        user_id: BMONI user id (UUID).
        card_id: Card id (UUID).
        size: Page size.
        status: Transaction status filter.
        from_date: Start date.
        to_date: End date.

    Returns:
        List of card transactions.
    """
    client = get_client()
    query = {"size": size, "status": status, "from": from_date, "to": to_date}
    return await client.get(
        f"/v1/users/{user_id}/cards/{card_id}/transactions",
        params={k: v for k, v in query.items() if v is not None},
    )


async def bmoni_cards_set_limits(
    user_id: str,
    card_id: str,
    max_single_transaction_amount: float,
    total_daily_limit: float,
) -> dict:
    """Set card spending limits.

    Args:
        user_id: BMONI user id (UUID).
        card_id: Card id (UUID).
        max_single_transaction_amount: Max per single transaction.
        total_daily_limit: Total daily spend limit.

    Returns:
        Updated limits.
    """
    client = get_client()
    return await client.put(
        f"/v1/users/{user_id}/cards/{card_id}/set-limit",
        json_body=payload(
            maxSingleTransactionAmount=max_single_transaction_amount,
            totalDailyLimit=total_daily_limit,
        ),
    )


async def bmoni_cards_limits(user_id: str, card_id: str) -> dict:
    """Get card spending limits.

    Args:
        user_id: BMONI user id (UUID).
        card_id: Card id (UUID).

    Returns:
        totalDailyLimit, availableDailyLimit, maxSingleTransactionAmount
        and provider caps.
    """
    client = get_client()
    return await client.get(f"/v1/users/{user_id}/cards/{card_id}/limits")


async def bmoni_cards_deactivate(user_id: str, card_id: str) -> dict:
    """Deactivate a card (irreversible).

    Args:
        user_id: BMONI user id (UUID).
        card_id: Card id (UUID).

    Returns:
        Deactivation result.
    """
    client = get_client()
    return await client.put(f"/v1/users/{user_id}/cards/{card_id}/deactivate")


async def bmoni_cards_identity(user_id: str, card_id: str) -> dict:
    """Get provider card identity metadata (no PAN/CVV).

    Args:
        user_id: BMONI user id (UUID).
        card_id: Card id (UUID).

    Returns:
        Card identity metadata from the provider.
    """
    client = get_client()
    return await client.get(
        f"/v1/users/{user_id}/smart-wallets/account/cards/{card_id}/sensitive"
    )


async def bmoni_cards_list_for_wallet(user_id: str, smart_wallet_id: str) -> dict:
    """List cards issued on a smart wallet.

    Args:
        user_id: BMONI user id (UUID).
        smart_wallet_id: Smart wallet id (UUID).

    Returns:
        List of cards.
    """
    client = get_client()
    return await client.get(
        f"/v1/users/{user_id}/smart-wallets/{smart_wallet_id}/cards"
    )


async def bmoni_cards_get_with_ledger(user_id: str, smart_wallet_id: str, card_id: str) -> dict:
    """Get a smart wallet card with its balance and ledger.

    Args:
        user_id: BMONI user id (UUID).
        smart_wallet_id: Smart wallet id (UUID).
        card_id: Card id (UUID).

    Returns:
        Card details, balanceMinor and the last 100 ledger entries.
    """
    client = get_client()
    return await client.get(
        f"/v1/users/{user_id}/smart-wallets/{smart_wallet_id}/cards/{card_id}"
    )


async def bmoni_cards_identity_wallet(
    user_id: str, smart_wallet_id: str, card_id: str
) -> dict:
    """Get card identity metadata scoped to a smart wallet (no PAN/CVV).

    Args:
        user_id: BMONI user id (UUID).
        smart_wallet_id: Smart wallet id (UUID).
        card_id: Card id (UUID).

    Returns:
        Card identity metadata.
    """
    client = get_client()
    return await client.get(
        f"/v1/users/{user_id}/smart-wallets/{smart_wallet_id}/cards/{card_id}/sensitive"
    )


TOOLS = [
    bmoni_cards_create,
    bmoni_cards_status,
    bmoni_cards_sensitive_data,
    bmoni_cards_request_activation_otp,
    bmoni_cards_confirm_activation_otp,
    bmoni_cards_set_status,
    bmoni_cards_set_pin,
    bmoni_cards_reset_pin,
    bmoni_cards_transactions,
    bmoni_cards_set_limits,
    bmoni_cards_limits,
    bmoni_cards_deactivate,
    bmoni_cards_identity,
    bmoni_cards_list_for_wallet,
    bmoni_cards_get_with_ledger,
    bmoni_cards_identity_wallet,
]
