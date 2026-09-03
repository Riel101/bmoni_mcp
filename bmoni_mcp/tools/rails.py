"""Tools that activate funding rails for a user.

After KYC, activation of a region rail goes through region onboarding
(Nigeria/Canada/EU/Mexico/USA) plus, where relevant, linking a virtual
bank account (VBA) so money can flow in/out of the smart wallet.
"""

from __future__ import annotations

from typing import Optional

from .common import get_client, payload


async def bmoni_rails_start_nigeria(
    user_id: str, bvn: str, ngn_wallet_address: str, ngn_wallet_index: int
) -> dict:
    """Start Nigeria rail onboarding (cNGN).

    Args:
        user_id: BMONI user id (UUID).
        bvn: The user's 11-digit Nigerian BVN.
        ngn_wallet_address: NGN smart wallet address.
        ngn_wallet_index: NGN wallet index.

    Returns:
        Onboarding workflow result for Nigeria.
    """
    client = get_client()
    return await client.post(
        f"/v1/users/{user_id}/onboarding/start-nigeria",
        json_body=payload(
            bvn=bvn, ngnWalletAddress=ngn_wallet_address, ngnWalletIndex=ngn_wallet_index
        ),
    )


async def bmoni_rails_start_canada(
    user_id: str, cad_wallet_address: str, cad_wallet_index: int
) -> dict:
    """Start Canada rail onboarding (CAD via PayTrie).

    Args:
        user_id: BMONI user id (UUID).
        cad_wallet_address: CAD smart wallet address.
        cad_wallet_index: CAD wallet index.

    Returns:
        Onboarding workflow result for Canada.
    """
    client = get_client()
    return await client.post(
        f"/v1/users/{user_id}/onboarding/start-canada",
        json_body=payload(
            cadWalletAddress=cad_wallet_address, cadWalletIndex=cad_wallet_index
        ),
    )


async def bmoni_rails_start_monerium(
    user_id: str, eur_wallet_address: str, eur_wallet_index: int
) -> dict:
    """Start EU rail onboarding (EUR via Monerium SEPA).

    Args:
        user_id: BMONI user id (UUID).
        eur_wallet_address: EUR smart wallet address.
        eur_wallet_index: EUR wallet index.

    Returns:
        Onboarding workflow result for the EU.
    """
    client = get_client()
    return await client.post(
        f"/v1/users/{user_id}/onboarding/start-monerium",
        json_body=payload(
            eurWalletAddress=eur_wallet_address, eurWalletIndex=eur_wallet_index
        ),
    )


async def bmoni_rails_start_mexico(
    user_id: str, mxn_wallet_address: str, mxn_wallet_index: int
) -> dict:
    """Start Mexico rail onboarding (MXN).

    Args:
        user_id: BMONI user id (UUID).
        mxn_wallet_address: MXN smart wallet address.
        mxn_wallet_index: MXN wallet index.

    Returns:
        Onboarding workflow result for Mexico.
    """
    client = get_client()
    return await client.post(
        f"/v1/users/{user_id}/onboarding/start-mexico",
        json_body=payload(
            mxnWalletAddress=mxn_wallet_address, mxnWalletIndex=mxn_wallet_index
        ),
    )


async def bmoni_rails_start_usa(user_id: str, smart_wallet_id: str) -> dict:
    """Start USA rail onboarding (USD virtual bank account).

    Idempotent. Requires the KYC USD-readiness check to pass first.

    Args:
        user_id: BMONI user id (UUID).
        smart_wallet_id: Smart wallet id (UUID) that the VBA feeds.

    Returns:
        A workflowId for the USD VBA provisioning workflow.
    """
    client = get_client()
    return await client.post(
        f"/v1/users/{user_id}/onboarding/start-usa",
        json_body=payload(smartWalletId=smart_wallet_id),
    )


async def bmoni_rails_onboarding_status(user_id: str) -> dict:
    """Get onboarding/rail status across all providers.

    Args:
        user_id: BMONI user id (UUID).

    Returns:
        anchorStatus, moneriumStatus, paytrieStatus, etherfuseStatus and
        any rejection reasons.
    """
    client = get_client()
    return await client.get(f"/v1/users/{user_id}/onboarding/status")


async def bmoni_rails_usd_vba_status(user_id: str) -> dict:
    """Get the status of the user's USD virtual bank account.

    Args:
        user_id: BMONI user id (UUID).

    Returns:
        VBA status and, when active, account details (account number,
        routing number, bank name, SWIFT, deposit message); otherwise the
        rejection reason.
    """
    client = get_client()
    return await client.get(f"/v1/users/{user_id}/vba/usd")


async def bmoni_rails_provision_usd_vba(user_id: str, smart_wallet_id: str) -> dict:
    """Provision a USD virtual bank account on the Graph Finance rail.

    Args:
        user_id: BMONI user id (UUID).
        smart_wallet_id: Smart wallet id (UUID) linked to the VBA.

    Returns:
        Provisioning workflow result.
    """
    client = get_client()
    return await client.post(
        f"/v1/users/{user_id}/smart-wallets/{smart_wallet_id}/onramp/vba/usd/provision"
    )


async def bmoni_rails_link_vba_nigeria(
    user_id: str,
    smart_wallet_id: str,
    bank_account_id: str,
    restore_sweep_to_wallet_id: Optional[str] = None,
) -> dict:
    """Link a Nigerian VBA to the smart wallet (cNGN onramp rail).

    Args:
        user_id: BMONI user id (UUID).
        smart_wallet_id: Smart wallet id (UUID).
        bank_account_id: Nigerian deposit bank account id (UUID).
        restore_sweep_to_wallet_id: Optional wallet to sweep restored funds to.

    Returns:
        Link result.
    """
    client = get_client()
    return await client.post(
        f"/v1/users/{user_id}/smart-wallets/{smart_wallet_id}/onramp/vba/nigeria",
        json_body=payload(
            bankAccountId=bank_account_id,
            restoreSweepToWalletId=restore_sweep_to_wallet_id,
        ),
    )


async def bmoni_rails_unlink_vba_nigeria(user_id: str, smart_wallet_id: str) -> dict:
    """Unlink the Nigerian VBA from the smart wallet.

    Args:
        user_id: BMONI user id (UUID).
        smart_wallet_id: Smart wallet id (UUID).

    Returns:
        Unlink result.
    """
    client = get_client()
    return await client.delete(
        f"/v1/users/{user_id}/smart-wallets/{smart_wallet_id}/onramp/vba/nigeria"
    )


async def bmoni_rails_link_vba_eu(
    user_id: str,
    smart_wallet_id: str,
    bank_account_id: str,
    restore_sweep_to_wallet_id: Optional[str] = None,
) -> dict:
    """Link an EU IBAN to the smart wallet (Monerium SEPA -> EURe rail).

    Args:
        user_id: BMONI user id (UUID).
        smart_wallet_id: Smart wallet id (UUID).
        bank_account_id: EU deposit IBAN account id (UUID).
        restore_sweep_to_wallet_id: Optional wallet to sweep restored funds to.

    Returns:
        Link result.
    """
    client = get_client()
    return await client.post(
        f"/v1/users/{user_id}/smart-wallets/{smart_wallet_id}/onramp/vba/eu",
        json_body=payload(
            bankAccountId=bank_account_id,
            restoreSweepToWalletId=restore_sweep_to_wallet_id,
        ),
    )


async def bmoni_rails_unlink_vba_eu(user_id: str, smart_wallet_id: str) -> dict:
    """Unlink the EU IBAN from the smart wallet.

    Args:
        user_id: BMONI user id (UUID).
        smart_wallet_id: Smart wallet id (UUID).

    Returns:
        Unlink result.
    """
    client = get_client()
    return await client.delete(
        f"/v1/users/{user_id}/smart-wallets/{smart_wallet_id}/onramp/vba/eu"
    )


async def bmoni_rails_link_vba_usd(
    user_id: str,
    smart_wallet_id: str,
    bank_account_id: str,
    restore_sweep_to_wallet_id: Optional[str] = None,
) -> dict:
    """Link a USD VBA to the smart wallet.

    Args:
        user_id: BMONI user id (UUID).
        smart_wallet_id: Smart wallet id (UUID).
        bank_account_id: USD VBA account id (UUID).
        restore_sweep_to_wallet_id: Optional wallet to sweep restored funds to.

    Returns:
        Link result.
    """
    client = get_client()
    return await client.post(
        f"/v1/users/{user_id}/smart-wallets/{smart_wallet_id}/onramp/vba/usd",
        json_body=payload(
            bankAccountId=bank_account_id,
            restoreSweepToWalletId=restore_sweep_to_wallet_id,
        ),
    )


async def bmoni_rails_unlink_vba_usd(user_id: str, smart_wallet_id: str) -> dict:
    """Unlink the USD VBA from the smart wallet.

    Args:
        user_id: BMONI user id (UUID).
        smart_wallet_id: Smart wallet id (UUID).

    Returns:
        Unlink result.
    """
    client = get_client()
    return await client.delete(
        f"/v1/users/{user_id}/smart-wallets/{smart_wallet_id}/onramp/vba/usd"
    )


TOOLS = [
    bmoni_rails_start_nigeria,
    bmoni_rails_start_canada,
    bmoni_rails_start_monerium,
    bmoni_rails_start_mexico,
    bmoni_rails_start_usa,
    bmoni_rails_onboarding_status,
    bmoni_rails_usd_vba_status,
    bmoni_rails_provision_usd_vba,
    bmoni_rails_link_vba_nigeria,
    bmoni_rails_unlink_vba_nigeria,
    bmoni_rails_link_vba_eu,
    bmoni_rails_unlink_vba_eu,
    bmoni_rails_link_vba_usd,
    bmoni_rails_unlink_vba_usd,
]
