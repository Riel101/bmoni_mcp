"""Webhook configuration tools.

The BMONI platform pushes events (wallet.deposit.*, card.*, kyc.*,
onboarding.*, employee.*) to your callback URL, signed with the
``x-webhook-signature`` header.
"""

from __future__ import annotations

from typing import Optional

from .common import get_client, payload

WEBHOOK_EVENTS = [
    "wallet.deposit.completed",
    "wallet.deposit.failed",
    "wallet.deposit.refunded",
    "wallet.withdrawal.completed",
    "wallet.withdrawal.failed",
    "wallet.withdrawal.processing",
    "card.fulfillment.updated",
    "card.transaction.created",
    "onboarding.completed",
    "onboarding.failed",
    "kyc.action_required",
    "employee.linked",
    "employee.vba.registered",
    "employee.unlinked",
    "employee.deposit.completed",
    "employee.deposit.failed",
    "employee.deposit.refunded",
    "employee.withdrawal.completed",
    "employee.withdrawal.failed",
    "employee.withdrawal.processing",
]


async def bmoni_webhooks_get_config() -> dict:
    """Get the current webhook configuration.

    Returns:
        The active webhook config (callbackUrl, events, active).
    """
    client = get_client()
    return await client.get("/v1/webhooks/config")


async def bmoni_webhooks_register_config(
    callback_url: str, events: list[str], active: bool = True
) -> dict:
    """Register a webhook configuration.

    Args:
        callback_url: HTTPS URL that will receive signed webhook events.
        events: Event types to subscribe to (e.g. wallet.deposit.completed).
        active: Whether the webhook is active.

    Returns:
        Registered webhook config.
    """
    client = get_client()
    return await client.post(
        "/v1/webhooks/config",
        json_body=payload(active=active, callbackUrl=callback_url, events=events),
    )


async def bmoni_webhooks_update_config(
    callback_url: Optional[str] = None,
    events: Optional[list[str]] = None,
    active: Optional[bool] = None,
) -> dict:
    """Update the webhook configuration.

    Args:
        callback_url: New callback URL.
        events: New event subscription list.
        active: Whether the webhook is active.

    Returns:
        Updated webhook config.
    """
    client = get_client()
    return await client.patch(
        "/v1/webhooks/config",
        json_body=payload(active=active, callbackUrl=callback_url, events=events),
    )


async def bmoni_webhooks_rotate_secret() -> dict:
    """Rotate the webhook signing secret.

    Returns:
        New signing secret. Past events signed with the old secret will no
        longer verify.
    """
    client = get_client()
    return await client.post("/v1/webhooks/config/rotate-secret")


TOOLS = [
    bmoni_webhooks_get_config,
    bmoni_webhooks_register_config,
    bmoni_webhooks_update_config,
    bmoni_webhooks_rotate_secret,
]
