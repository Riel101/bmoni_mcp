"""Tools that move money: sends, proposals/signatures, exchange,
withdrawals, offramps, SEPA payouts, bank payouts and LATAM pay-outs.
"""

from __future__ import annotations

import base64
from typing import Literal, Optional

from ..models import BankPayoutDetails, EuCounterpart
from .common import get_client, payload

SendCurrency = Literal[
    "USDB", "CNGN", "CADC", "EURe", "GBPe", "MEXe", "USDC", "USDG"
]
ProposalType = Literal[
    "TRANSFER",
    "SWAP",
    "ADD_MEMBER",
    "REMOVE_MEMBER",
    "ADMIN_DEMOTE_OWNER",
    "CHANGE_THRESHOLD",
]


async def bmoni_money_send_named(
    user_id: str,
    from_wallet_id: str,
    to_user_id: str,
    amount: str,
    currency: Optional[SendCurrency] = None,
    note: Optional[str] = None,
) -> dict:
    """Send funds from a named smart wallet to another BMONI user.

    Args:
        user_id: Sender BMONI user id (UUID).
        from_wallet_id: Source smart wallet id (UUID).
        to_user_id: Recipient BMONI user id (UUID).
        amount: Amount to send (decimal string, e.g. "10.50").
        currency: Wallet currency. Omit to let BMONI resolve it.
        note: Optional note (max 500 chars).

    Returns:
        A transfer proposal plus signature request details.
    """
    client = get_client()
    return await client.post(
        f"/v1/users/{user_id}/smart-wallets/fund",
        json_body=payload(
            amount=amount,
            fromWalletId=from_wallet_id,
            toUserId=to_user_id,
            currency=currency,
            note=note,
        ),
    )


async def bmoni_money_send_account(
    user_id: str,
    to_user_id: str,
    amount: str,
    currency: Optional[SendCurrency] = None,
    note: Optional[str] = None,
) -> dict:
    """Send funds from the user's account; BMONI resolves the source wallet.

    Args:
        user_id: Sender BMONI user id (UUID).
        to_user_id: Recipient BMONI user id (UUID).
        amount: Amount to send (decimal string).
        currency: Wallet currency. Omit to let BMONI resolve it.
        note: Optional note (max 500 chars).

    Returns:
        Transfer result / signature request details.
    """
    client = get_client()
    return await client.post(
        f"/v1/users/{user_id}/smart-wallets/account/send",
        json_body=payload(
            amount=amount, toUserId=to_user_id, currency=currency, note=note
        ),
    )


async def bmoni_money_offramp_nigeria(
    user_id: str,
    smart_wallet_id: str,
    bank_account_id: str,
    from_amount: str,
) -> dict:
    """Offramp funds from a smart wallet to a linked Nigerian bank account.

    USDB is auto-swapped to NGN; cNGN is sent directly.

    Args:
        user_id: BMONI user id (UUID).
        smart_wallet_id: Smart wallet id (UUID) to debit.
        bank_account_id: Nigerian bank account id (UUID).
        from_amount: Amount to offramp (decimal string).

    Returns:
        Offramp result / signature request.
    """
    client = get_client()
    return await client.post(
        f"/v1/users/{user_id}/smart-wallets/{smart_wallet_id}/offramp/nigeria",
        json_body=payload(bankAccountId=bank_account_id, fromAmount=from_amount),
    )


# ----------------------------------------------------------------- proposals


async def bmoni_money_create_proposal(
    user_id: str,
    smart_wallet_id: str,
    type: ProposalType,
    details: Optional[dict] = None,
) -> dict:
    """Create a multi-sig proposal on a smart wallet.

    Args:
        user_id: BMONI user id (UUID).
        smart_wallet_id: Smart wallet id (UUID).
        type: Proposal type: TRANSFER, SWAP, ADD_MEMBER, REMOVE_MEMBER,
            ADMIN_DEMOTE_OWNER or CHANGE_THRESHOLD.
        details: Additional proposal fields required by the type. For
            TRANSFER/SWAP typical fields are amount and currency; for member
            changes a target member/address; for CHANGE_THRESHOLD a new
            threshold. See BMONI API docs for the exact shape.

    Returns:
        The created proposal.
    """
    client = get_client()
    body = payload(type=type)
    if details:
        body.update(details)
    return await client.post(
        f"/v1/users/{user_id}/smart-wallets/{smart_wallet_id}/proposals",
        json_body=body,
    )


async def bmoni_money_list_proposals(user_id: str, smart_wallet_id: str) -> dict:
    """List all proposals on a smart wallet.

    Args:
        user_id: BMONI user id (UUID).
        smart_wallet_id: Smart wallet id (UUID).

    Returns:
        List of proposals.
    """
    client = get_client()
    return await client.get(
        f"/v1/users/{user_id}/smart-wallets/{smart_wallet_id}/proposals"
    )


async def bmoni_money_get_proposal(user_id: str, proposal_id: str) -> dict:
    """Get a single proposal.

    Args:
        user_id: BMONI user id (UUID).
        proposal_id: Proposal id (UUID).

    Returns:
        Proposal details.
    """
    client = get_client()
    return await client.get(f"/v1/users/{user_id}/smart-wallets/proposals/{proposal_id}")


async def bmoni_money_proposal_sign_payload(user_id: str, proposal_id: str) -> dict:
    """Get the EIP-712 typed data an owner must sign for a proposal.

    Args:
        user_id: BMONI user id (UUID).
        proposal_id: Proposal id (UUID).

    Returns:
        Typed-data payload to sign with the owner's EVM wallet.
    """
    client = get_client()
    return await client.get(
        f"/v1/users/{user_id}/smart-wallets/proposals/{proposal_id}/sign-payload"
    )


async def bmoni_money_submit_signature(user_id: str, proposal_id: str, signature: str) -> dict:
    """Submit an owner's ECDSA signature for a proposal.

    When the threshold is reached the proposal is executed via the bundler.

    Args:
        user_id: BMONI user id (UUID).
        proposal_id: Proposal id (UUID).
        signature: Hex ECDSA signature over the sign payload / tx hash.

    Returns:
        Execution/approval result.
    """
    client = get_client()
    return await client.post(
        f"/v1/users/{user_id}/smart-wallets/proposals/{proposal_id}/sign",
        json_body=payload(signature=signature),
    )


async def bmoni_money_reject_proposal(
    user_id: str, proposal_id: str, reason: Optional[str] = None
) -> dict:
    """Reject a proposal.

    Args:
        user_id: BMONI user id (UUID).
        proposal_id: Proposal id (UUID).
        reason: Optional rejection reason.

    Returns:
        Rejection result.
    """
    client = get_client()
    return await client.post(
        f"/v1/users/{user_id}/smart-wallets/proposals/{proposal_id}/reject",
        json_body=payload(reason=reason),
    )


# ------------------------------------------------------------------ exchange


async def bmoni_money_exchange_rate(
    user_id: str, from_currency: str, to_currency: str
) -> dict:
    """Get the current exchange rate between two currencies.

    Args:
        user_id: BMONI user id (UUID).
        from_currency: Source currency (USDB, USDC, cNGN, USD, NGN, EUR,
            GBP, CAD, CNY...).
        to_currency: Target currency.

    Returns:
        The exchange rate.
    """
    client = get_client()
    return await client.get(
        f"/v1/users/{user_id}/exchange/rate/{from_currency}/{to_currency}"
    )


async def bmoni_money_exchange_convert(
    user_id: str, amount: float, from_currency: str, to_currency: str
) -> dict:
    """Convert an amount between currencies using the live rate.

    Args:
        user_id: BMONI user id (UUID).
        amount: Amount greater than zero.
        from_currency: Source currency.
        to_currency: Target currency.

    Returns:
        exchangeRate and convertedAmount.
    """
    client = get_client()
    return await client.post(
        f"/v1/users/{user_id}/exchange/convert",
        json_body={"amount": amount, "from": from_currency, "to": to_currency},
    )


async def bmoni_money_exchange_quote(
    user_id: str,
    from_currency: Literal["USD", "NGN", "CAD", "EUR", "GBP", "MXN", "CNY"],
    to_currency: Literal["USD", "NGN", "CAD", "EUR", "GBP", "MXN", "CNY"],
    amount: float,
    exact: Literal["exactIn", "exactOut"] = "exactIn",
) -> dict:
    """Get a swap quote between fiat-like currencies.

    Args:
        user_id: BMONI user id (UUID).
        from_currency: Source currency.
        to_currency: Target currency.
        amount: The swap amount.
        exact: Whether the amount is an exact input (exactIn) or exact
            output (exactOut).

    Returns:
        quoteId, output amounts, fees, expiry.
    """
    client = get_client()
    return await client.post(
        f"/v1/users/{user_id}/exchange/quote",
        json_body=payload(
            fromCurrency=from_currency,
            toCurrency=to_currency,
            swapAmount={exact: amount},
        ),
    )


# ---------------------------------------------------------------- withdrawals


async def bmoni_money_withdraw_nigeria_bank(
    user_id: str,
    source_smart_wallet_id: str,
    bank_account_id: str,
    from_amount: str,
) -> dict:
    """Withdraw from a smart wallet to a Nigerian bank account.

    Creates an offramp proposal and auto-approves it.

    Args:
        user_id: BMONI user id (UUID).
        source_smart_wallet_id: Smart wallet id (UUID) to debit.
        bank_account_id: Nigerian withdrawal bank account id (UUID).
        from_amount: Amount to withdraw (decimal string).

    Returns:
        proposalId and signPayload to sign/submit.
    """
    client = get_client()
    return await client.post(
        f"/v1/users/{user_id}/withdrawal/wallet/nigeria",
        json_body=payload(
            bankAccountId=bank_account_id,
            fromAmount=from_amount,
            sourceSmartWalletId=source_smart_wallet_id,
        ),
    )


async def bmoni_money_crypto_withdrawal_supported(
    user_id: str, currency: str
) -> dict:
    """List supported crypto withdrawal destinations for a currency.

    Args:
        user_id: BMONI user id (UUID).
        currency: Currency to withdraw.

    Returns:
        Supported destination chains/currencies (via Bridge).
    """
    client = get_client()
    return await client.get(
        f"/v1/users/{user_id}/withdrawal/smart-wallet/crypto/supported/{currency}"
    )


async def bmoni_money_withdraw_crypto(
    user_id: str,
    source_smart_wallet_id: str,
    amount: str,
    destination_address: str,
    destination_chain: str,
    destination_currency: str,
) -> dict:
    """Withdraw crypto from a smart wallet to an external address via Bridge.

    Auto-approves and returns a sign payload.

    Args:
        user_id: BMONI user id (UUID).
        source_smart_wallet_id: Smart wallet id (UUID) to debit.
        amount: Amount to withdraw (decimal string).
        destination_address: External destination address.
        destination_chain: Destination chain.
        destination_currency: Destination currency.

    Returns:
        proposalId and signPayload.
    """
    client = get_client()
    return await client.post(
        f"/v1/users/{user_id}/withdrawal/smart-wallet/crypto",
        json_body=payload(
            amount=amount,
            destinationAddress=destination_address,
            destinationChain=destination_chain,
            destinationCurrency=destination_currency,
            sourceSmartWalletId=source_smart_wallet_id,
        ),
    )


async def bmoni_money_withdraw_card(
    user_id: str,
    smart_wallet_id: str,
    card_id: str,
    amount: str,
    currency: Literal["NGN", "USD"],
) -> dict:
    """Move money from a card back into the smart wallet (no signature).

    Args:
        user_id: BMONI user id (UUID).
        smart_wallet_id: Smart wallet id (UUID) to credit.
        card_id: Card id (UUID) to debit.
        amount: Amount to move (decimal string).
        currency: Card currency (NGN or USD).

    Returns:
        Withdrawal result.
    """
    client = get_client()
    return await client.post(
        f"/v1/users/{user_id}/withdrawal/card",
        json_body=payload(
            amount=amount, cardId=card_id, currency=currency, smartWalletId=smart_wallet_id
        ),
    )


# -------------------------------------------------------------- transactions


async def bmoni_money_transactions(user_id: str, smart_wallet_id: str) -> dict:
    """List transactions for a smart wallet (user-facing view).

    Includes direction, amount, status, counterparty, narration type,
    exchange rate and failure details.

    Args:
        user_id: BMONI user id (UUID).
        smart_wallet_id: Smart wallet id (UUID).

    Returns:
        Ordered list of transactions.
    """
    client = get_client()
    return await client.get(f"/v1/users/{user_id}/transactions/{smart_wallet_id}")


async def bmoni_money_transactions_with_user(user_id: str, other_user_id: str) -> dict:
    """List transactions between the user and another user.

    Args:
        user_id: BMONI user id (UUID).
        other_user_id: The other BMONI user id (UUID).

    Returns:
        Transactions with direction, amount, currency, timestamp and the
        other user's details.
    """
    client = get_client()
    return await client.get(
        f"/v1/users/{user_id}/transactions/user/{other_user_id}"
    )


async def bmoni_money_transaction_fees(
    user_id: str, smart_wallet_id: str, transaction_id: str
) -> dict:
    """Get the fee breakdown for a transaction.

    Args:
        user_id: BMONI user id (UUID).
        smart_wallet_id: Smart wallet id (UUID).
        transaction_id: Transaction id (UUID).

    Returns:
        Visible fees and per-currency totals.
    """
    client = get_client()
    return await client.get(
        f"/v1/users/{user_id}/transactions/{smart_wallet_id}/{transaction_id}/fees"
    )


async def bmoni_money_receipt_pdf(
    user_id: str, smart_wallet_id: str, transaction_id: str, timezone: str
) -> dict:
    """Generate a transaction receipt PDF (base64).

    Args:
        user_id: BMONI user id (UUID).
        smart_wallet_id: Smart wallet id (UUID).
        transaction_id: Transaction id (UUID).
        timezone: IANA timezone for the receipt (e.g. Africa/Lagos).

    Returns:
        Binary PDF encoded as base64 under dataBase64.
    """
    client = get_client()
    return await client.post(
        f"/v1/users/{user_id}/transactions/receipt/pdf",
        json_body=payload(
            smartWalletId=smart_wallet_id,
            transactionId=transaction_id,
            timezone=timezone,
        ),
    )


async def bmoni_money_group_receipt_pdf(
    user_id: str, smart_wallet_id: str, transaction_id: str, timezone: str
) -> dict:
    """Generate a group-wallet transaction receipt PDF (base64).

    Args:
        user_id: BMONI user id (UUID).
        smart_wallet_id: Group smart wallet id (UUID).
        transaction_id: Transaction id (UUID).
        timezone: IANA timezone.

    Returns:
        Binary PDF encoded as base64 under dataBase64.
    """
    client = get_client()
    return await client.post(
        f"/v1/users/{user_id}/transactions/group-wallet/receipt/pdf",
        json_body=payload(
            smartWalletId=smart_wallet_id,
            transactionId=transaction_id,
            timezone=timezone,
        ),
    )


# --------------------------------------------------------------------- SEPA


async def bmoni_money_eu_kyc(user_id: str, code: str, signature: str) -> dict:
    """Complete the EU (Monerium) KYC step.

    Args:
        user_id: BMONI user id (UUID).
        code: Auth code returned by Monerium.
        signature: Wallet ownership proof signature.

    Returns:
        EU KYC completion result.
    """
    client = get_client()
    return await client.post(
        f"/v1/users/{user_id}/eu/kyc", json_body=payload(code=code, signature=signature)
    )


async def bmoni_money_sepa_prepare(
    user_id: str,
    smart_wallet_id: str,
    amount: str,
    counterpart: EuCounterpart,
    memo: Optional[str] = None,
    note: Optional[str] = None,
    supporting_document_id: Optional[str] = None,
) -> dict:
    """Prepare a EUR SEPA payout to an IBAN counterparty.

    Args:
        user_id: BMONI user id (UUID).
        smart_wallet_id: Smart wallet id (UUID) debited.
        amount: Amount in EUR (decimal string, 2dp).
        counterpart: Beneficiary: identifier.iban plus details
            (firstName/lastName/country).
        memo: Optional memo (5-140 chars).
        note: Optional note.
        supporting_document_id: Required for amounts >= EUR 15,000.

    Returns:
        workflowId, messageToSign and an optional signatureRequest when an
        international fee applies.
    """
    client = get_client()
    return await client.post(
        f"/v1/users/{user_id}/eu/orders/prepare",
        json_body=payload(
            smartWalletId=smart_wallet_id,
            amount=amount,
            counterpart=counterpart.model_dump(exclude_none=True),
            memo=memo,
            note=note,
            supportingDocumentId=supporting_document_id,
        ),
    )


async def bmoni_money_sepa_complete(
    user_id: str, workflow_id: str, signature: str
) -> dict:
    """Complete a prepared EUR SEPA payout with the wallet signature.

    Args:
        user_id: BMONI user id (UUID).
        workflow_id: workflowId from bmoni_money_sepa_prepare.
        signature: Signature over the returned messageToSign.

    Returns:
        Payout completion result.
    """
    client = get_client()
    return await client.post(
        f"/v1/users/{user_id}/eu/orders/complete",
        json_body=payload(workflowId=workflow_id, signature=signature),
    )


async def bmoni_money_upload_eu_file(
    user_id: str, file_base64: str, filename: str = "document.pdf"
) -> dict:
    """Upload a supporting document for EU flows (max 5MB PDF/JPEG).

    Args:
        user_id: BMONI user id (UUID).
        file_base64: Base64-encoded PDF or JPEG file.
        filename: Filename with extension hint.

    Returns:
        A fileId to reference in KYC or SEPA order requests.
    """
    client = get_client()
    try:
        content = base64.b64decode(file_base64)
    except Exception as exc:
        raise ValueError("file_base64 must be valid base64") from exc
    files = [("file", (filename, content, "application/pdf"))]
    return await client.post(f"/v1/users/{user_id}/eu/files", files=files)


# ---------------------------------------------------------------- LATAM cash


async def bmoni_money_latam_cash_send(
    user_id: str,
    smart_wallet_id: str,
    country: Literal["MX", "CL", "CO"],
    price: str,
    price_currency: Literal["MXN", "CLP", "COP"],
    description: str,
) -> dict:
    """Create a LATAM cash pay-out order (cash send).

    Args:
        user_id: BMONI user id (UUID).
        smart_wallet_id: Smart wallet id (UUID) debited.
        country: Cash order country (MX, CL, CO).
        price: Amount in the local currency (string).
        price_currency: Local currency (MXN, CLP, COP).
        description: Order description.

    Returns:
        A signatureRequest to sign and submit.
    """
    client = get_client()
    return await client.post(
        f"/v1/users/{user_id}/latam/cash/orders/send",
        json_body=payload(
            smartWalletId=smart_wallet_id,
            country=country,
            price=price,
            priceCurrency=price_currency,
            description=description,
        ),
    )


async def bmoni_money_latam_cash_orders(
    user_id: str, type: Optional[Literal["FUND", "SEND"]] = None
) -> dict:
    """List LATAM cash orders.

    Args:
        user_id: BMONI user id (UUID).
        type: Filter by FUND or SEND (default FUND).

    Returns:
        List of cash orders.
    """
    client = get_client()
    return await client.get(
        f"/v1/users/{user_id}/latam/cash/orders", params=payload(type=type)
    )


async def bmoni_money_latam_cash_order(user_id: str, order_id: str) -> dict:
    """Get a single LATAM cash order.

    Args:
        user_id: BMONI user id (UUID).
        order_id: Cash order id.

    Returns:
        Cash order details.
    """
    client = get_client()
    return await client.get(f"/v1/users/{user_id}/latam/cash/orders/{order_id}")


# ------------------------------------------------------------ bank payouts


async def bmoni_money_payout_countries(user_id: str) -> dict:
    """List countries supported for bank payouts.

    Args:
        user_id: BMONI user id (UUID).

    Returns:
        Supported payout countries.
    """
    client = get_client()
    return await client.get(f"/v1/users/{user_id}/payouts/countries")


async def bmoni_money_payout_banks(user_id: str, country: str) -> dict:
    """List banks available for payouts in a country.

    Args:
        user_id: BMONI user id (UUID).
        country: ISO alpha3 country code.

    Returns:
        List of banks with bankId/bank details.
    """
    client = get_client()
    return await client.get(
        f"/v1/users/{user_id}/payouts/banks", params=payload(country=country)
    )


async def bmoni_money_payout_bank_branches(user_id: str, bank_id: str) -> dict:
    """List branches for a payout bank.

    Args:
        user_id: BMONI user id (UUID).
        bank_id: Bank id from bmoni_money_payout_banks.

    Returns:
        List of branches with branchId.
    """
    client = get_client()
    return await client.get(
        f"/v1/users/{user_id}/payouts/bank-branches", params=payload(bankId=bank_id)
    )


async def bmoni_money_validate_payout_account(
    user_id: str,
    country: str,
    currency: str,
    account_number: str,
    bank_id: Optional[str] = None,
    routing_number: Optional[str] = None,
) -> dict:
    """Validate a destination account for a bank payout.

    Args:
        user_id: BMONI user id (UUID).
        country: ISO alpha3 country code.
        currency: ISO 4217 currency code.
        account_number: Destination account number.
        bank_id: Bank id when required.
        routing_number: Routing number when required.

    Returns:
        Validation result (e.g. account holder name).
    """
    client = get_client()
    return await client.post(
        f"/v1/users/{user_id}/payouts/validate-account",
        json_body=payload(
            country=country,
            currency=currency,
            accountNumber=account_number,
            bankId=bank_id,
            routingNumber=routing_number,
        ),
    )


async def bmoni_money_create_bank_payout(
    user_id: str,
    source_smart_wallet_id: str,
    amount: str,
    country: str,
    currency: str,
    bank_details: BankPayoutDetails,
    note: Optional[str] = None,
) -> dict:
    """Create a bank payout from a USDB smart wallet to a bank account.

    Args:
        user_id: BMONI user id (UUID).
        source_smart_wallet_id: USDB smart wallet id (UUID) to debit.
        amount: Amount in USDB minor units (string).
        country: ISO alpha3 destination country.
        currency: ISO 4217 destination currency.
        bank_details: Destination bank account details.
        note: Optional note (max 500 chars).

    Returns:
        A signatureRequest and quote. Sign and submit it via
        bmoni_money_submit_signature to execute the payout.
    """
    client = get_client()
    return await client.post(
        f"/v1/users/{user_id}/payouts",
        json_body=payload(
            sourceSmartWalletId=source_smart_wallet_id,
            amount=amount,
            country=country,
            currency=currency,
            bankDetails=bank_details.model_dump(exclude_none=True),
            note=note,
        ),
    )


TOOLS = [
    bmoni_money_send_named,
    bmoni_money_send_account,
    bmoni_money_offramp_nigeria,
    bmoni_money_create_proposal,
    bmoni_money_list_proposals,
    bmoni_money_get_proposal,
    bmoni_money_proposal_sign_payload,
    bmoni_money_submit_signature,
    bmoni_money_reject_proposal,
    bmoni_money_exchange_rate,
    bmoni_money_exchange_convert,
    bmoni_money_exchange_quote,
    bmoni_money_withdraw_nigeria_bank,
    bmoni_money_crypto_withdrawal_supported,
    bmoni_money_withdraw_crypto,
    bmoni_money_withdraw_card,
    bmoni_money_transactions,
    bmoni_money_transactions_with_user,
    bmoni_money_transaction_fees,
    bmoni_money_receipt_pdf,
    bmoni_money_group_receipt_pdf,
    bmoni_money_eu_kyc,
    bmoni_money_sepa_prepare,
    bmoni_money_sepa_complete,
    bmoni_money_upload_eu_file,
    bmoni_money_latam_cash_send,
    bmoni_money_latam_cash_orders,
    bmoni_money_latam_cash_order,
    bmoni_money_payout_countries,
    bmoni_money_payout_banks,
    bmoni_money_payout_bank_branches,
    bmoni_money_validate_payout_account,
    bmoni_money_create_bank_payout,
]
