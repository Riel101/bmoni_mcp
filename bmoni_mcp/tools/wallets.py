"""Tools to provision and inspect BMONI smart (multi-sig) wallets.

Provisioning a managed smart wallet follows three steps:
1. ``bmoni_wallets_owner_proof_challenge`` - obtain an EIP-191 message.
2. Have the user owner sign it with their EVM wallet (off-chain).
3. ``bmoni_wallets_create_managed`` - submit challenge + signature.
"""

from __future__ import annotations

from typing import Literal, Optional

from .common import get_client, payload

SmartWalletCurrency = Literal["USDB", "CNGN", "CADC", "EURe", "GBPe", "MEXe"]


async def bmoni_wallets_supported_currencies() -> list:
    """List the currencies supported for smart wallets.

    Returns:
        Currencies such as USDB, CNGN, CADC, EURe, GBPe and MEXe.
    """
    client = get_client()
    return await client.get("/v1/smart-wallets/supported-currencies")


async def bmoni_wallets_owner_proof_challenge(
    user_id: str, currency: SmartWalletCurrency, user_owner_address: str
) -> dict:
    """Create an owner-proof challenge needed before deploying a smart wallet.

    Args:
        user_id: BMONI user id (UUID).
        currency: Smart wallet currency (e.g. USDB).
        user_owner_address: EVM address of the wallet owner.

    Returns:
        An EIP-191 challenge (challengeId, groupId, message, expiresAt).
        The ``message`` must be signed by the owner and the signature sent
        to bmoni_wallets_create_managed within 10 minutes.
    """
    client = get_client()
    return await client.post(
        f"/v1/users/{user_id}/smart-wallets/owner-proof-challenges",
        json_body=payload(currency=currency, userOwnerAddress=user_owner_address),
    )


async def bmoni_wallets_create_managed(
    user_id: str,
    currency: SmartWalletCurrency,
    owner_proof_challenge_id: str,
    owner_proof_signature: str,
    user_owner_address: str,
) -> dict:
    """Create (provision) a managed smart wallet for the user.

    Atomic prepare, KMS-sign, deploy and owner registration.

    Args:
        user_id: BMONI user id (UUID).
        currency: Smart wallet currency (e.g. USDB).
        owner_proof_challenge_id: Id from bmoni_wallets_owner_proof_challenge.
        owner_proof_signature: EIP-191 signature from the owner over the
            challenge message.
        user_owner_address: EVM address of the wallet owner.

    Returns:
        The created smart wallet.
    """
    client = get_client()
    return await client.post(
        f"/v1/users/{user_id}/smart-wallets/create-managed",
        json_body=payload(
            currency=currency,
            ownerProofChallengeId=owner_proof_challenge_id,
            ownerProofSignature=owner_proof_signature,
            userOwnerAddress=user_owner_address,
        ),
    )


async def bmoni_wallets_list_account(user_id: str) -> dict:
    """List all smart wallets on the user's account.

    Args:
        user_id: BMONI user id (UUID).

    Returns:
        The user's smart wallets.
    """
    client = get_client()
    return await client.get(f"/v1/users/{user_id}/smart-wallets/account/wallets")


async def bmoni_wallets_account_balances(user_id: str) -> dict:
    """Get balances across all of the user's active per-currency wallets.

    Args:
        user_id: BMONI user id (UUID).

    Returns:
        Balances queried in parallel across active smart wallets.
    """
    client = get_client()
    return await client.get(f"/v1/users/{user_id}/smart-wallets/account/balances")


async def bmoni_wallets_get(user_id: str, smart_wallet_id: str) -> dict:
    """Get a smart wallet by id.

    Args:
        user_id: BMONI user id (UUID).
        smart_wallet_id: Smart wallet id (UUID).

    Returns:
        Smart wallet details.
    """
    client = get_client()
    return await client.get(f"/v1/users/{user_id}/smart-wallets/{smart_wallet_id}")


async def bmoni_wallets_balance(user_id: str, smart_wallet_id: str) -> dict:
    """Get a single smart wallet's balance.

    Args:
        user_id: BMONI user id (UUID).
        smart_wallet_id: Smart wallet id (UUID).

    Returns:
        The wallet balance.
    """
    client = get_client()
    return await client.get(
        f"/v1/users/{user_id}/smart-wallets/{smart_wallet_id}/balance"
    )


async def bmoni_wallets_transactions(
    user_id: str, smart_wallet_id: str, size: Optional[int] = None, status: Optional[str] = None
) -> dict:
    """List a smart wallet's transactions.

    Args:
        user_id: BMONI user id (UUID).
        smart_wallet_id: Smart wallet id (UUID).
        size: Page size.
        status: Filter by transaction status.

    Returns:
        List of smart wallet transactions.
    """
    client = get_client()
    return await client.get(
        f"/v1/users/{user_id}/smart-wallets/{smart_wallet_id}/transactions",
        params=payload(size=size, status=status),
    )


async def bmoni_wallets_transaction_detail(
    user_id: str, smart_wallet_id: str, transaction_id: str
) -> dict:
    """Get a single smart wallet transaction, including approvals.

    Args:
        user_id: BMONI user id (UUID).
        smart_wallet_id: Smart wallet id (UUID).
        transaction_id: Transaction id (UUID).

    Returns:
        Transaction details and approvals.
    """
    client = get_client()
    return await client.get(
        f"/v1/users/{user_id}/smart-wallets/{smart_wallet_id}/transactions/{transaction_id}"
    )


TOOLS = [
    bmoni_wallets_supported_currencies,
    bmoni_wallets_owner_proof_challenge,
    bmoni_wallets_create_managed,
    bmoni_wallets_list_account,
    bmoni_wallets_account_balances,
    bmoni_wallets_get,
    bmoni_wallets_balance,
    bmoni_wallets_transactions,
    bmoni_wallets_transaction_detail,
]
