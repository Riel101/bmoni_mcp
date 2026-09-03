"""Contract + registration tests for the BMONI MCP server.

Run with:  python tests/test_server.py

These tests validate that every tool is registered with a clean schema,
that the required end-to-end capabilities exist, and that representative
calls produce HTTP requests matching the BMONI Embedded API reference
(method, path, query string and JSON body) - without hitting a live API.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from httpx import MockTransport, Response  # noqa: E402

from bmoni_mcp.api import BmoniClient  # noqa: E402
from bmoni_mcp.config import get_settings  # noqa: E402
from bmoni_mcp.server import build_server, tool_names  # noqa: E402
from bmoni_mcp.tools import common  # noqa: E402
from bmoni_mcp.tools import all_tools  # noqa: E402
from bmoni_mcp.models import (  # noqa: E402
    BankPayoutDetails,
    EuCounterpart,
    KycAddress,
    KycUpdateInput,
)

PASSED: list[str] = []


def check(label: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(f"FAILED: {label}")
    PASSED.append(label)


async def _run_with_mock(fn, **kwargs) -> tuple[object, list]:
    """Run a tool fn against a recording mock transport."""
    recorded: list = []

    def handler(request):
        recorded.append(request)
        return Response(200, json={"ok": True, "requestedPath": str(request.url)})

    client = BmoniClient(
        "http://bmoni.test", "test-key", timeout=5, transport=MockTransport(handler)
    )
    common._client = client
    try:
        result = await fn(**kwargs)
    finally:
        common._client = None
        common.reset_client()
    return result, recorded


def _single(req) -> None:
    assert len(req) == 1, f"expected exactly 1 request, got {len(req)}"


async def test_registration() -> None:
    server = build_server()
    tools = await server.list_tools()
    names = [t.name for t in tools]
    check("all tool names are unique", len(set(names)) == len(names))
    check("tools are namespaced with bmoni_ prefix", all(n.startswith("bmoni_") for n in names))
    check("total tool count is sane", len(names) >= 100)
    for t in tools:
        assert t.parameters.get("type") == "object", t.name
        assert t.description, f"{t.name} has no description"

    # Every required end-to-end capability must be reachable.
    required = {
        "create the user": ["bmoni_users_create"],
        "provision the smart wallet": [
            "bmoni_wallets_owner_proof_challenge",
            "bmoni_wallets_create_managed",
        ],
        "verify identity (KYC)": [
            "bmoni_kyc_update_profile",
            "bmoni_kyc_activate",
            "bmoni_kyc_status",
        ],
        "activate the rail": [
            "bmoni_rails_start_usa",
            "bmoni_rails_provision_usd_vba",
            "bmoni_rails_onboarding_status",
        ],
        "fund the wallet": [
            "bmoni_fund_deposit_crypto",
            "bmoni_fund_card",
        ],
        "move money": [
            "bmoni_money_send_account",
            "bmoni_money_submit_signature",
            "bmoni_money_withdraw_nigeria_bank",
        ],
        "information about BMONI": [
            "bmoni_info_health",
            "bmoni_wallets_supported_currencies",
        ],
    }
    for capability, wanted in required.items():
        for tool in wanted:
            check(f"capability '{capability}' exposes {tool}", tool in names)
    check("list-tools matches registered tools", set(tool_names()) == set(names))


async def test_create_user() -> None:
    from bmoni_mcp.tools.users import bmoni_users_create

    _, req = await _run_with_mock(
        bmoni_users_create,
        email="ada@example.com",
        first_name="Ada",
        phone_number="+2348012345678",
        bvn="12345678901",
        identity_id=None,
    )
    _single(req)
    check("create user -> POST /v1/users", req[0].method == "POST" and req[0].url.path == "/v1/users")
    body = req[0].read()
    data = json.loads(body)
    for key in ("email", "firstName", "phoneNumber", "bvn"):
        check(f"create user body has {key}", key in data)
    check("create user omits unset optional fields", "identityId" not in data)
    check("create user camelCases firstName", data["firstName"] == "Ada")


async def test_kyc_contract() -> None:
    from bmoni_mcp.tools.kyc import (
        bmoni_kyc_activate,
        bmoni_kyc_options,
        bmoni_kyc_update_profile,
        bmoni_kyc_upload_biometric,
    )

    uid = "u-1"
    _, req = await _run_with_mock(bmoni_kyc_options, user_id=uid)
    _single(req)
    check("kyc options GET path", req[0].method == "GET" and req[0].url.path == f"/v1/users/{uid}/kyc/options")

    _, req = await _run_with_mock(
        bmoni_kyc_update_profile,
        user_id=uid,
        body=KycUpdateInput(
            accountPurpose="personal",
            sourceOfFunds="salary",
            address=KycAddress(city="Lagos", countryCode="NG"),
        ),
    )
    _single(req)
    data = json.loads(req[0].read())
    check("kyc update PATCH path", req[0].method == "PATCH" and req[0].url.path == f"/v1/users/{uid}/kyc")
    check("kyc update has accountPurpose", data.get("accountPurpose") == "personal")
    check("kyc update nests address", data.get("address", {}).get("city") == "Lagos")

    _, req = await _run_with_mock(
        bmoni_kyc_activate, user_id=uid, sumsub_level_name="id-and-liveness"
    )
    _single(req)
    data = json.loads(req[0].read())
    check("kyc activate body level", data.get("sumsubLevelName") == "id-and-liveness")

    b64 = base64.b64encode(b"fake-jpeg-bytes").decode()
    _, req = await _run_with_mock(
        bmoni_kyc_upload_biometric, user_id=uid, type="selfie", file_base64=b64
    )
    _single(req)
    check("kyc biometric multipart path", req[0].url.path == f"/v1/users/{uid}/kyc/documents/biometric")


async def test_smart_wallet_provision() -> None:
    from bmoni_mcp.tools.wallets import bmoni_wallets_create_managed, bmoni_wallets_supported_currencies

    _, req = await _run_with_mock(bmoni_wallets_supported_currencies)
    _single(req)
    check("supported currencies GET", req[0].url.path == "/v1/smart-wallets/supported-currencies")

    _, req = await _run_with_mock(
        bmoni_wallets_create_managed,
        user_id="u-1",
        currency="USDB",
        owner_proof_challenge_id="c-1",
        owner_proof_signature="0xsig",
        user_owner_address="0xabc",
    )
    _single(req)
    data = json.loads(req[0].read())
    check(
        "create-managed path",
        req[0].url.path == "/v1/users/u-1/smart-wallets/create-managed",
    )
    for key in ("currency", "ownerProofChallengeId", "ownerProofSignature", "userOwnerAddress"):
        check(f"create-managed body has {key}", key in data)


async def test_activate_rail() -> None:
    from bmoni_mcp.tools.rails import bmoni_rails_provision_usd_vba, bmoni_rails_start_usa

    _, req = await _run_with_mock(
        bmoni_rails_start_usa, user_id="u-1", smart_wallet_id="w-1"
    )
    _single(req)
    data = json.loads(req[0].read())
    check("start-usa path", req[0].url.path == "/v1/users/u-1/onboarding/start-usa")
    check("start-usa body smartWalletId", data.get("smartWalletId") == "w-1")

    _, req = await _run_with_mock(
        bmoni_rails_provision_usd_vba, user_id="u-1", smart_wallet_id="w-1"
    )
    _single(req)
    check(
        "provision usd vba path",
        req[0].url.path == "/v1/users/u-1/smart-wallets/w-1/onramp/vba/usd/provision",
    )


async def test_fund() -> None:
    from bmoni_mcp.tools.fund import bmoni_fund_deposit_crypto

    _, req = await _run_with_mock(
        bmoni_fund_deposit_crypto,
        user_id="u-1",
        smart_wallet_id="w-1",
        chain="Base",
        currency="USDC",
    )
    _single(req)
    data = json.loads(req[0].read())
    check("deposit crypto path", req[0].url.path == "/v1/users/u-1/deposit/wallet")
    check("deposit crypto body chain", data.get("chain") == "Base")
    check("deposit crypto body currency", data.get("currency") == "USDC")


async def test_move_money() -> None:
    from bmoni_mcp.tools.money import (
        bmoni_money_exchange_convert,
        bmoni_money_send_account,
        bmoni_money_submit_signature,
        bmoni_money_withdraw_nigeria_bank,
    )

    _, req = await _run_with_mock(
        bmoni_money_send_account,
        user_id="u-1",
        to_user_id="u-2",
        amount="10.50",
        note="lunch",
    )
    _single(req)
    data = json.loads(req[0].read())
    check("send account path", req[0].url.path == "/v1/users/u-1/smart-wallets/account/send")
    check("send body amount", data.get("amount") == "10.50")
    check("send body toUserId", data.get("toUserId") == "u-2")

    _, req = await _run_with_mock(
        bmoni_money_exchange_convert,
        user_id="u-1",
        amount=5.0,
        from_currency="USDB",
        to_currency="NGN",
    )
    _single(req)
    data = json.loads(req[0].read())
    check("convert body has 'from' key", "from" in data and data["from"] == "USDB")
    check("convert body has 'to' key", data["to"] == "NGN")

    _, req = await _run_with_mock(
        bmoni_money_submit_signature,
        user_id="u-1",
        proposal_id="p-1",
        signature="0xdeadbeef",
    )
    _single(req)
    check(
        "submit signature path",
        req[0].url.path == "/v1/users/u-1/smart-wallets/proposals/p-1/sign",
    )

    _, req = await _run_with_mock(
        bmoni_money_withdraw_nigeria_bank,
        user_id="u-1",
        source_smart_wallet_id="w-1",
        bank_account_id="ba-1",
        from_amount="2000.00",
    )
    _single(req)
    data = json.loads(req[0].read())
    check("withdraw ngn path", req[0].url.path == "/v1/users/u-1/withdrawal/wallet/nigeria")
    for key in ("bankAccountId", "fromAmount", "sourceSmartWalletId"):
        check(f"withdraw body has {key}", key in data)


async def test_bank_payout_and_sepa() -> None:
    from bmoni_mcp.tools.money import bmoni_money_create_bank_payout, bmoni_money_sepa_prepare

    _, req = await _run_with_mock(
        bmoni_money_create_bank_payout,
        user_id="u-1",
        source_smart_wallet_id="w-1",
        amount="10000",
        country="USA",
        currency="USD",
        bank_details=BankPayoutDetails(
            bankId="bk-1",
            accountNumber="123456789",
            accountHolderName="Ada",
            routingNumber="021000021",
        ),
    )
    _single(req)
    data = json.loads(req[0].read())
    check("bank payout path", req[0].url.path == "/v1/users/u-1/payouts")
    check("bank payout nests bankDetails", data.get("bankDetails", {}).get("accountNumber") == "123456789")

    _, req = await _run_with_mock(
        bmoni_money_sepa_prepare,
        user_id="u-1",
        smart_wallet_id="w-1",
        amount="99.90",
        counterpart=EuCounterpart(
            identifier={"iban": "DE89370400440532013000"},
            details={"firstName": "Ada", "lastName": "Lovelace", "country": "DE"},
        ),
    )
    _single(req)
    data = json.loads(req[0].read())
    check("sepa prepare path", req[0].url.path == "/v1/users/u-1/eu/orders/prepare")
    check("sepa counterpart iban", data["counterpart"]["identifier"]["iban"].startswith("DE89"))


async def test_info_and_misc() -> None:
    from bmoni_mcp.tools.info import bmoni_info_health
    from bmoni_mcp.tools.cards import bmoni_cards_set_status
    from bmoni_mcp.tools.bank_accounts import bmoni_bank_accounts_verify_nigeria

    _, req = await _run_with_mock(bmoni_info_health)
    _single(req)
    check("health GET /v1/health", req[0].url.path == "/v1/health")

    _, req = await _run_with_mock(
        bmoni_cards_set_status, user_id="u-1", card_id="c-1", status="BLOCKED"
    )
    _single(req)
    data = json.loads(req[0].read())
    check("card set-status PUT", req[0].method == "PUT")
    check("card set-status path", req[0].url.path == "/v1/users/u-1/cards/c-1/status")
    check("card set-status body", data.get("status") == "BLOCKED")

    _, req = await _run_with_mock(
        bmoni_bank_accounts_verify_nigeria,
        user_id="u-1",
        account_number="0123456789",
        bank_code="058",
    )
    _single(req)
    data = json.loads(req[0].read())
    check("verify ngn body", data.get("accountNumber") == "0123456789" and data.get("bankCode") == "058")


async def test_auth_header_and_config_error() -> None:
    from bmoni_mcp.tools.users import bmoni_users_create

    recorded: list = []

    def handler(request):
        recorded.append(request)
        return Response(200, json={"ok": True})

    client = BmoniClient(
        "http://bmoni.test", "secret-key", transport=MockTransport(handler)
    )
    common._client = client
    try:
        await bmoni_users_create(email="a@b.co", first_name="A", phone_number="+10000000000")
    finally:
        common.reset_client()
    check("x-api-key header is sent", recorded[0].headers.get("x-api-key") == "secret-key")

    # Configuration error: temporarily hide env vars.
    import importlib

    old = {k: os.environ.get(k) for k in ("BMONI_BASE_URL", "BMONI_API_KEY")}
    for k in old:
        os.environ.pop(k, None)
    try:
        importlib.reload(importlib.import_module("bmoni_mcp.config"))
        settings = get_settings()
        check("config flags missing vars", set(settings.missing()) >= {"BMONI_BASE_URL", "BMONI_API_KEY"})
        check("config error is actionable", "BMONI_BASE_URL" in settings.configuration_error())
    finally:
        for k, v in old.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)


def main() -> None:
    coros = [
        test_registration,
        test_create_user,
        test_kyc_contract,
        test_smart_wallet_provision,
        test_activate_rail,
        test_fund,
        test_move_money,
        test_bank_payout_and_sepa,
        test_info_and_misc,
        test_auth_header_and_config_error,
    ]
    failures = 0
    for coro in coros:
        try:
            asyncio.run(coro())
            print(f"ok     {coro.__name__}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAILED {coro.__name__}: {exc}")
    print(f"\n{len(PASSED)} assertions passed, {failures} test(s) failed")
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
