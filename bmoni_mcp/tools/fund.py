"""Tools that fund a BMONI smart wallet (or its card)."""

from __future__ import annotations

from typing import Literal

from .common import get_client, payload

Chain = Literal[
    "Arbitrum",
    "Avalanche",
    "Base",
    "Ethereum",
    "Optimism",
    "Polygon",
    "Solana",
    "Stellar",
    "Tron",
]
CryptoCurrency = Literal["DAI", "EURC", "PYUSD", "USDB", "USDC", "USDP", "USDT"]


async def bmoni_fund_deposit_crypto(
    user_id: str,
    smart_wallet_id: str,
    chain: Chain,
    currency: CryptoCurrency,
) -> dict:
    """Get a one-time deposit address to fund the wallet from another chain.

    The deposited crypto is auto-converted and credited to the smart wallet.
    No signature is required.

    Args:
        user_id: BMONI user id (UUID).
        smart_wallet_id: Smart wallet id (UUID) to credit.
        chain: Source chain to deposit from.
        currency: Token/currency to deposit.

    Returns:
        A one-time deposit address.
    """
    client = get_client()
    return await client.post(
        f"/v1/users/{user_id}/deposit/wallet",
        json_body=payload(
            chain=chain, currency=currency, smartWalletId=smart_wallet_id
        ),
    )


async def bmoni_fund_card(
    user_id: str, smart_wallet_id: str, card_id: str, amount: str
) -> dict:
    """Fund a card from the user's smart wallet.

    Creates a FUND_CARD proposal that is auto-approved. Returns a
    signature request; sign it (bmoni_money_submit_signature) to execute.

    Args:
        user_id: BMONI user id (UUID).
        smart_wallet_id: Smart wallet id (UUID) funding the card.
        card_id: Card id (UUID) to fund.
        amount: Amount to move from wallet to card (decimal string).

    Returns:
        Proposal/signature request details (signPayload).
    """
    client = get_client()
    return await client.post(
        f"/v1/users/{user_id}/deposit/card",
        json_body=payload(
            amount=amount, cardId=card_id, smartWalletId=smart_wallet_id
        ),
    )


async def bmoni_fund_supported_assets() -> dict:
    """List chains and tokens enabled for crypto deposits.

    Returns:
        Deposit assets grouped by chain.
    """
    client = get_client()
    return await client.get("/v1/deposit/supported-assets")


async def bmoni_fund_latam_cash(
    user_id: str,
    smart_wallet_id: str,
    country: Literal["MX", "CL", "CO"],
    price: str,
    price_currency: Literal["MXN", "CLP", "COP"],
    description: str,
) -> dict:
    """Create a LATAM cash pay-in order (cash funding).

    The user pays cash at a local provider; the wallet is credited once the
    provider confirms.

    Args:
        user_id: BMONI user id (UUID).
        smart_wallet_id: Smart wallet id (UUID) to credit.
        country: Cash order country (MX, CL, CO).
        price: Amount in the local currency (string).
        price_currency: Local currency (MXN, CLP, COP).
        description: Order description.

    Returns:
        redirect_url for the cash payment.
    """
    client = get_client()
    return await client.post(
        f"/v1/users/{user_id}/latam/cash/orders/fund",
        json_body=payload(
            smartWalletId=smart_wallet_id,
            country=country,
            price=price,
            priceCurrency=price_currency,
            description=description,
        ),
    )


TOOLS = [
    bmoni_fund_deposit_crypto,
    bmoni_fund_card,
    bmoni_fund_supported_assets,
    bmoni_fund_latam_cash,
]
