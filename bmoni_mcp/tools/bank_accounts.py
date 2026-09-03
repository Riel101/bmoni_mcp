"""Tools to manage the bank accounts used for deposits and withdrawals."""

from __future__ import annotations

from typing import Literal, Optional

from .common import get_client, payload

WithdrawalCurrency = Literal["NGN", "USD", "CAD", "EUR", "GBP", "MXN"]


async def bmoni_bank_accounts_list(user_id: str) -> dict:
    """List all of the user's bank accounts (deposit + withdrawal).

    Args:
        user_id: BMONI user id (UUID).

    Returns:
        depositAccounts (nigerian, activation, european) and
        withdrawalAccounts (nigerian, european).
    """
    client = get_client()
    return await client.get(f"/v1/users/{user_id}/bank-accounts")


async def bmoni_bank_accounts_deposit(user_id: str) -> dict:
    """List the user's deposit bank accounts.

    Args:
        user_id: BMONI user id (UUID).

    Returns:
        Deposit accounts grouped by region.
    """
    client = get_client()
    return await client.get(f"/v1/users/{user_id}/bank-accounts/deposit-accounts")


async def bmoni_bank_accounts_deposit_currency(user_id: str, currency: str) -> dict:
    """List deposit accounts for a currency (account numbers to receive money).

    Args:
        user_id: BMONI user id (UUID).
        currency: NGN, USD, CAD, EUR, GBP or MXN (NGN includes regular and
            activation accounts).

    Returns:
        Deposit account details for the currency.
    """
    client = get_client()
    return await client.get(
        f"/v1/users/{user_id}/bank-accounts/deposit-accounts/{currency}"
    )


async def bmoni_bank_accounts_withdrawal(user_id: str) -> dict:
    """List the user's withdrawal bank accounts.

    Args:
        user_id: BMONI user id (UUID).

    Returns:
        Withdrawal accounts grouped by region (nigerianAccounts,
        europeanAccounts).
    """
    client = get_client()
    return await client.get(f"/v1/users/{user_id}/bank-accounts/withdrawal-accounts")


async def bmoni_bank_accounts_withdrawal_currency(
    user_id: str, currency: WithdrawalCurrency
) -> dict:
    """List withdrawal accounts for a currency.

    Args:
        user_id: BMONI user id (UUID).
        currency: NGN, USD, CAD, EUR, GBP or MXN.

    Returns:
        Withdrawal accounts for the currency.
    """
    client = get_client()
    return await client.get(
        f"/v1/users/{user_id}/bank-accounts/withdrawal-accounts/{currency}"
    )


async def bmoni_bank_accounts_nigerian_banks(user_id: str) -> dict:
    """List supported Nigerian banks.

    Args:
        user_id: BMONI user id (UUID).

    Returns:
        List of banks with bankName and bankCode.
    """
    client = get_client()
    return await client.get(f"/v1/users/{user_id}/bank-accounts/nigerian-banks")


async def bmoni_bank_accounts_verify_nigeria(
    user_id: str, account_number: str, bank_code: str
) -> dict:
    """Verify a Nigerian bank account (NUBAN name lookup).

    Args:
        user_id: BMONI user id (UUID).
        account_number: 10-digit NUBAN account number.
        bank_code: CBN bank code from bmoni_bank_accounts_nigerian_banks.

    Returns:
        The registered accountName, if the account is valid.
    """
    client = get_client()
    return await client.post(
        f"/v1/users/{user_id}/bank-accounts/verify-nigerian-account",
        json_body=payload(accountNumber=account_number, bankCode=bank_code),
    )


async def bmoni_bank_accounts_add_nigeria_withdrawal(
    user_id: str,
    account_holder_name: str,
    account_number: str,
    bank_code: str,
    bank_name: Optional[str] = None,
) -> dict:
    """Register a Nigerian bank account for withdrawals.

    Args:
        user_id: BMONI user id (UUID).
        account_holder_name: Name on the account (verify first).
        account_number: 10-digit NUBAN account number.
        bank_code: CBN bank code.
        bank_name: Bank name.

    Returns:
        The registered withdrawal account.
    """
    client = get_client()
    return await client.post(
        f"/v1/users/{user_id}/bank-accounts/withdrawal-accounts/nigeria",
        json_body=payload(
            accountHolderName=account_holder_name,
            accountNumber=account_number,
            bankCode=bank_code,
            bankName=bank_name,
        ),
    )


async def bmoni_bank_accounts_deactivate_deposit_eu(
    user_id: str, account_id: str
) -> dict:
    """Deactivate an EU deposit (virtual bank) account with Monerium upstream.

    Args:
        user_id: BMONI user id (UUID).
        account_id: Deposit account id (UUID).

    Returns:
        Deactivation result.
    """
    client = get_client()
    return await client.put(
        f"/v1/users/{user_id}/bank-accounts/deposit-accounts/{account_id}/deactivate"
    )


async def bmoni_bank_accounts_deactivate_nigeria_withdrawal(
    user_id: str, account_id: str
) -> dict:
    """Deactivate a Nigerian withdrawal bank account.

    Args:
        user_id: BMONI user id (UUID).
        account_id: Withdrawal account id (UUID).

    Returns:
        Deactivation result.
    """
    client = get_client()
    return await client.put(
        f"/v1/users/{user_id}/bank-accounts/withdrawal-accounts/nigeria/{account_id}/deactivate"
    )


TOOLS = [
    bmoni_bank_accounts_list,
    bmoni_bank_accounts_deposit,
    bmoni_bank_accounts_deposit_currency,
    bmoni_bank_accounts_withdrawal,
    bmoni_bank_accounts_withdrawal_currency,
    bmoni_bank_accounts_nigerian_banks,
    bmoni_bank_accounts_verify_nigeria,
    bmoni_bank_accounts_add_nigeria_withdrawal,
    bmoni_bank_accounts_deactivate_deposit_eu,
    bmoni_bank_accounts_deactivate_nigeria_withdrawal,
]
