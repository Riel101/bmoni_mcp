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
import contextlib
import json
import os
import sys
import tempfile

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

# A real JPEG magic-byte header followed by filler, so upload guards pass.
VALID_JPEG_B64 = base64.b64encode(b"\xff\xd8\xff\xe0" + b"\x00" * 16 + b"fakejpeg").decode()
VALID_PDF_B64 = base64.b64encode(b"%PDF-1.4\n" + b"fake-pdf-body").decode()

PASSED: list[str] = []


def check(label: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(f"FAILED: {label}")
    PASSED.append(label)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ENV_KEYS = (
    "BMONI_BASE_URL",
    "BMONI_API_KEY",
    "BMONI_SANDBOX_BASE_URL",
    "BMONI_SANDBOX_API_KEY",
    "BMONI_ENV",
    "BMONI_READ_ONLY",
    "BMONI_ERROR_BODY_ECHO",
    "BMONI_SCOPED_USER_ID",
    "BMONI_ADMIN_SUBJECTS",
    "BMONI_MCP_TOKENS",
    "BMONI_MCP_TOKEN",
    "BMONI_MCP_JWT_ISSUER",
    "BMONI_MCP_JWT_AUDIENCE",
    "BMONI_MCP_JWKS_URI",
    "BMONI_MCP_JWT_PUBLIC_KEY",
    "BMONI_AUTO_APPROVE_TOOLS",
    "BMONI_HITL_GRAY",
    "BMONI_APPROVAL_TTL_SECONDS",
    "BMONI_APPROVAL_DENY_COOLDOWN",
    "BMONI_APPROVAL_DB",
    "BMONI_RATE_LIMIT_RPS",
    "BMONI_RATE_LIMIT_BURST",
    "BMONI_MAX_CONCURRENT",
    "BMONI_UPLOAD_MAX_MB",
)


@contextlib.contextmanager
def env_patch(**updates):
    """Temporarily set/clear the BMONI_* environment for one block."""
    keys = set(_ENV_KEYS) | set(updates)
    old = {k: os.environ.get(k) for k in keys}
    for k in keys:
        os.environ.pop(k, None)
    for k, v in updates.items():
        if v is not None:
            os.environ[k] = v
    try:
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


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


def _text_of(result) -> str:
    blocks = getattr(result, "content", None) or []
    return "".join(str(getattr(b, "text", "")) for b in blocks)


async def test_registration() -> None:
    # List as an admin principal so every registered tool is visible.
    saved = {}
    for key in ("BMONI_SCOPED_USER_ID", "BMONI_ADMIN_SUBJECTS"):
        saved[key] = os.environ.get(key)
    os.environ["BMONI_SCOPED_USER_ID"] = "u-admin-1"
    os.environ["BMONI_ADMIN_SUBJECTS"] = "u-admin-1"
    try:
        server = build_server()
        tools = await server.list_tools()
    finally:
        for key, value in saved.items():
            if value is not None:
                os.environ[key] = value
            else:
                os.environ.pop(key, None)
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

    b64 = VALID_JPEG_B64
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


# ---------------------------------------------------------------------------
# New security tests
# ---------------------------------------------------------------------------


def _make_manager(path: str, **kw) -> "object":
    from bmoni_mcp.approvals import ApprovalManager

    return ApprovalManager(
        db_path=path,
        ttl_seconds=kw.pop("ttl_seconds", 600),
        deny_cooldown=kw.pop("deny_cooldown", 300),
        max_pending=kw.pop("max_pending", 50),
        callback_url="",
        webhook_secret="",
    )


def _make_middleware(tmpdir, manager=None, *, audit=None, rps=50.0, burst=100, max_concurrent=0):
    from bmoni_mcp.approvals import ApprovalManager
    from bmoni_mcp.config import get_settings as _gs
    from bmoni_mcp.limits import ConcurrencyLimiter, RateLimiter
    from bmoni_mcp.middleware import EnforcementMiddleware

    settings = _gs()
    if manager is None:
        manager = ApprovalManager(db_path=f"{tmpdir}/approvals.sqlite3", audit=audit)
    elif audit is not None:
        manager.audit = audit
    mw = EnforcementMiddleware(
        settings=settings,
        approvals=manager,
        rate_limiter=RateLimiter(rps=rps, burst=burst),
        concurrency=ConcurrencyLimiter(max_concurrent),
    )
    return mw, manager


async def test_read_only_client() -> None:
    from bmoni_mcp.api import BmoniError

    hits: list = []

    def handler(request):
        hits.append(request)
        return Response(200, json={"ok": True})

    client = BmoniClient(
        "http://bmoni.test", "key", read_only=True, transport=MockTransport(handler)
    )
    await client.get("/v1/health")
    check("read-only allows GET", len(hits) == 1)

    ok = await client.post(
        "/v1/users/u-1/cards/sensitive-data", json_body={"cardId": "c1"}
    )
    check("read-only allows pure-read POST allowlist", ok.get("ok") is True)

    hits.clear()
    for method in ("post", "put", "patch", "delete"):
        with_ = {"json_body": {"amount": "5"}} if method != "delete" else {}
        hits.clear()
        try:
            await getattr(client, method)("/v1/users/u-1/transfer", **with_)
            check(f"read-only refuses {method.upper()}", False)
        except BmoniError as exc:
            check(
                f"read-only refuses {method.upper()}",
                exc.status_code == 403 and "read-only" in str(exc).lower(),
            )

    # Environment-level read-only can not be bypassed by a fresh client.
    with env_patch(BMONI_READ_ONLY="1", BMONI_BASE_URL="http://x", BMONI_API_KEY="k"):
        env_client = BmoniClient(
            "http://bmoni.test", "key", transport=MockTransport(handler)
        )
        try:
            await env_client.post("/v1/users/u-1/transfer", json_body={"a": 1})
            check("env read-only enforced", False)
        except BmoniError as exc:
            check("env read-only enforced", "read-only" in str(exc).lower())


async def test_error_redaction_and_key_not_logged() -> None:
    from bmoni_mcp.api import BmoniError

    pan = "1111-2222-3333-4444"
    secrets = {
        "pan": pan,
        "cvv": "123",
        "pin": "4321",
        "signature": "0xdeadbeefsig",
        "bvn": "22113344556",
        "nin": "99887766554",
        "fileBase64": "aGVsbG8=",
        "dataBase64": "aGVsbG8=",
        "otp": "999999",
        "secret": "s3cret!",
    }

    def handler(request):
        return Response(400, json=secrets)

    # echo=1 -> body present but fully redacted.
    client = BmoniClient(
        "http://bmoni.test",
        "prod-secret-key-abc",
        error_body_echo="1",
        transport=MockTransport(handler),
    )
    try:
        await client.post("/v1/users/u-1/cards", json_body={"x": 1})
        check("error raised", False)
    except BmoniError as exc:
        text = str(exc)
        for value in secrets.values():
            check(f"echo=1 body redacts {value!r}", value not in text)
        check("redacted marker present", "[REDACTED]" in text)
        check("api key not in echo=1 error", "prod-secret-key-abc" not in text)

    # masked default -> no body echoed at all.
    client = BmoniClient(
        "http://bmoni.test", "prod-secret-key-abc", transport=MockTransport(handler)
    )
    try:
        await client.post("/v1/users/u-1/cards", json_body={"x": 1})
        check("masked error raised", False)
    except BmoniError as exc:
        text = str(exc)
        check("masked suppresses PAN", pan not in text)
        check("masked suppresses cvv", "123" not in text)
        check("api key not in masked error", "prod-secret-key-abc" not in text)

    # Sandbox key must never leak either.
    def key_handler(request):
        return Response(500, text="boom secret-sandbox-key-xyz")

    client = BmoniClient(
        "http://bmoni.test",
        "secret-sandbox-key-xyz",
        error_body_echo="1",
        transport=MockTransport(key_handler),
    )
    try:
        await client.post("/v1/users/u-1/cards", json_body={"x": 1})
    except BmoniError as exc:
        check("sandbox key not in error", "secret-sandbox-key-xyz" not in str(exc))

    # Success responses are scrubbed too: a proxying upstream that echoes the
    # key never surfaces it in a tool result.
    def echo_handler(request):
        return Response(200, json={"probe": {"sentKey": "prod-secret-key-abc", "ok": True}})

    client = BmoniClient(
        "http://bmoni.test",
        "prod-secret-key-abc",
        error_body_echo="1",
        transport=MockTransport(echo_handler),
    )
    out = await client.get("/v1/health")
    check("success responses scrub the api key", json.dumps(out).find("prod-secret-key-abc") == -1)


async def test_upload_guard_rejects_bad_files() -> None:
    from bmoni_mcp.uploads import validate_upload

    # Oversize file.
    try:
        validate_upload(
            base64.b64encode(b"\xff\xd8\xff\xe0" + b"a" * 6000).decode(),
            filename="big.jpg",
            max_mb=0.005,
        )
        check("oversize upload rejected", False)
    except ValueError as exc:
        check("oversize upload rejected", "limit" in str(exc))

    # Wrong magic bytes for the declared extension.
    try:
        validate_upload(VALID_PDF_B64, filename="image.jpg")
        check("extension/magic mismatch rejected", False)
    except ValueError as exc:
        check("extension/magic mismatch rejected", "does not match" in str(exc))

    # Unrecognized magic bytes.
    try:
        validate_upload(base64.b64encode(b"not-an-image-or-pdf-at-all").decode())
        check("unknown magic rejected", False)
    except ValueError as exc:
        check("unknown magic rejected", "magic bytes" in str(exc))

    # Wire into the EU file upload tool: no request is ever made.
    from bmoni_mcp.tools.money import bmoni_money_upload_eu_file

    recorded: list = []

    def boom(request):
        recorded.append(request)
        raise AssertionError("upload should never reach the network")

    common._client = BmoniClient(
        "http://bmoni.test", "k", transport=MockTransport(boom)
    )
    try:
        await bmoni_money_upload_eu_file(
            user_id="u-1", file_base64=base64.b64encode(b"garbage").decode()
        )
        check("eu upload guard raises", False)
    except ValueError:
        check("eu upload guard raises", True)
    finally:
        common.reset_client()
    check("eu upload guard makes no request", not recorded)


async def test_env_pair_guards() -> None:
    from bmoni_mcp import env_guard

    # Sandbox refuses a production key in the same process.
    with env_patch(
        BMONI_ENV="sandbox",
        BMONI_SANDBOX_BASE_URL="https://sandbox.bmoni.example",
        BMONI_SANDBOX_API_KEY="sandbox-key",
        BMONI_BASE_URL="https://prod.bmoni.example",
        BMONI_API_KEY="prod-key",
    ):
        settings = get_settings()
        try:
            env_guard.assert_env_pair(settings)
            check("sandbox refuses prod key", False)
        except RuntimeError:
            check("sandbox refuses prod key", True)
        check(
            "config flags prod key in sandbox",
            any("BMONI_API_KEY" in item for item in settings.missing()),
        )

    # Production refuses missing creds.
    with env_patch(
        BMONI_ENV="production",
        BMONI_SANDBOX_BASE_URL="https://sandbox.bmoni.example",
        BMONI_SANDBOX_API_KEY="sandbox-key",
    ):
        settings = get_settings()
        try:
            env_guard.assert_env_pair(settings)
            check("production refuses sandbox-only", False)
        except RuntimeError:
            check("production refuses sandbox-only", True)

    # Valid sandbox pair resolves to the sandbox credentials.
    with env_patch(
        BMONI_ENV="sandbox",
        BMONI_SANDBOX_BASE_URL="https://sandbox.bmoni.example",
        BMONI_SANDBOX_API_KEY="sandbox-key",
    ):
        settings = get_settings()
        check("sandbox pair valid", env_guard.assert_env_pair(settings) == "sandbox")
        base_url, api_key = env_guard.resolve_credentials(settings)
        check(
            "sandbox resolves developer API link",
            base_url == "https://sandbox.bmoni.example" and api_key == "sandbox-key",
        )
        check("sandbox flag is_sandbox()", env_guard.is_sandbox())

    # Valid production pair resolves to production credentials.
    with env_patch(
        BMONI_ENV="production",
        BMONI_BASE_URL="https://prod.bmoni.example",
        BMONI_API_KEY="prod-key",
    ):
        settings = get_settings()
        check("production pair valid", env_guard.assert_env_pair(settings) == "production")
        base_url, api_key = env_guard.resolve_credentials(settings)
        check(
            "production resolves prod pair",
            base_url == "https://prod.bmoni.example" and api_key == "prod-key",
        )


async def _invoke(mw, tool: str, arguments: dict, *, called: list):
    """Run a tool call through middleware with a fake dispatcher."""
    from fastmcp.server.middleware import MiddlewareContext
    import mcp_types as mt

    params = mt.CallToolRequestParams(name=tool, arguments=arguments)
    context = MiddlewareContext(message=params, method="tools/call", type="request")

    async def dispatcher(_context):
        called.append(tool)
        return mt.CallToolResult(
            content=[mt.TextContent(type="text", text="dispatched-ok")],
            is_error=False,
        )

    return await mw.on_call_tool(context, call_next=dispatcher)


async def test_approval_gate_flow() -> None:
    from bmoni_mcp.approvals import STATUS_APPROVED, STATUS_PENDING, STATUS_USED
    from bmoni_mcp.audit import AuditLogger, set_audit

    tmp = tempfile.mkdtemp()
    audit_path = f"{tmp}/audit.jsonl"
    set_audit(AuditLogger(audit_path, sensitive=True))
    try:
        with env_patch(BMONI_SCOPED_USER_ID="u-1", BMONI_AUTO_APPROVE_TOOLS=""):
            mw, manager = _make_middleware(tmp, audit=AuditLogger(audit_path, sensitive=True))
            args = {"user_id": "u-1", "to_user_id": "u-2", "amount": "10.00"}

            # Harmful call with no approval -> approval_required, no dispatch.
            called: list = []
            result = await _invoke(mw, "bmoni_money_send_account", args, called=called)
            check("HITL refuses without approval", "approval_required" in _text_of(result))
            check("HITL result is not an error", getattr(result, "is_error") is False)
            check("HITL does not dispatch", not called)

            pending = manager.list(status=STATUS_PENDING)
            check("pending record created", len(pending) == 1)
            check("pending record carries summary", "amount=10.00" in pending[0]["summary"])
            approval_id = pending[0]["id"]

            # Approve, then the identical call dispatches once.
            manager.approve(approval_id, by="approver")
            called.clear()
            result = await _invoke(mw, "bmoni_money_send_account", args, called=called)
            check("approved call dispatches", called == ["bmoni_money_send_account"])
            check("approved call result ok", "dispatched-ok" in _text_of(result))
            check("approval consumed", manager.list(status=STATUS_USED)[0]["id"] == approval_id)

            # Third identical call -> approval_required again (consume-once).
            called.clear()
            result = await _invoke(mw, "bmoni_money_send_account", args, called=called)
            check("no double execution (consume-once)", not called)
            check("consume-once requests approval again", "approval_required" in _text_of(result))
    finally:
        set_audit(None)

    lines = open(audit_path).read().strip().splitlines()
    events = [json.loads(line) for line in lines]
    check("audit records approval pending", any(e["event"] == "approval.pending" for e in events))
    check("audit records approved execution", any(e["event"] == "tool.executing" for e in events))
    check("audit records used", any(e["event"] == "approval.used" for e in events))


async def test_approval_deny_cooldown_and_expiry() -> None:
    from bmoni_mcp.approvals import ApprovalError, STATUS_EXPIRED, STATUS_REJECTED

    tmp = tempfile.mkdtemp()
    with env_patch(BMONI_SCOPED_USER_ID="u-1", BMONI_AUTO_APPROVE_TOOLS=""):
        mw, manager = _make_middleware(tmp)
        args = {"user_id": "u-1", "to_user_id": "u-2", "amount": "99.00"}

        # Deny cooldown blocks an identical retry.
        called: list = []
        result = await _invoke(mw, "bmoni_money_send_account", args, called=called)
        pending = manager.list(status="PENDING")[0]
        manager.reject(pending["id"], by="approver", reason="not authorized")

        called.clear()
        result = await _invoke(mw, "bmoni_money_send_account", args, called=called)
        check("denied call stays blocked", getattr(result, "is_error") is True)
        check("denied message cites reason", "not authorized" in _text_of(result))
        check("denied call does not dispatch", not called)
        check("rejected record kept", len(manager.list(status=STATUS_REJECTED)) == 1)

        # Expiry: an approved record older than the TTL is not usable.
        mw2, manager2 = _make_middleware(tmp + "/db2")
        args2 = {"user_id": "u-1", "amount": "5.00"}
        pending2 = manager2.create_pending("u-1", "bmoni_money_send_account", args2, "hitl")
        manager2.approve(pending2.id, by="approver")
        manager2._execute(
            "UPDATE approvals SET expires_at=? WHERE id=?",
            (manager2._now() - 10, pending2.id),
        )
        check("expired approval not matchable", manager2.matching_approved("u-1", "bmoni_money_send_account", args2) is None)
        try:
            manager2.consume(pending2.id, by="tool:test")
            check("expired approval cannot be consumed", False)
        except ApprovalError:
            check("expired approval cannot be consumed", True)
        manager2.expire_overdue()
        check("expired approval marked EXPIRED", manager2.list(status=STATUS_EXPIRED)[0]["id"] == pending2.id)


async def test_role_gating_and_user_pinning() -> None:
    tmp = tempfile.mkdtemp()
    # Non-admin principal.
    with env_patch(BMONI_SCOPED_USER_ID="u-1", BMONI_AUTO_APPROVE_TOOLS="", BMONI_READ_ONLY="0"):
        mw, _ = _make_middleware(tmp)

        called: list = []
        result = await _invoke(
            mw, "bmoni_employer_invite_employee",
            {"email": "a@b.co", "name": "A"}, called=called,
        )
        check("admin tool rejected for non-admin", getattr(result, "is_error") is True)
        check("admin tool message", "admin tool" in _text_of(result))
        check("admin tool does not dispatch", not called)

        # user_id pinning: principal u-1 may not act on u-2.
        called.clear()
        result = await _invoke(
            mw, "bmoni_money_transactions",
            {"user_id": "u-2", "smart_wallet_id": "w-1"}, called=called,
        )
        check("user_id pinning rejects foreign user", getattr(result, "is_error") is True)
        check("pinning message cites scope", "scoped to user 'u-1'" in _text_of(result))
        check("pinned call does not dispatch", not called)

        # Own user works (a read -> dispatches).
        called.clear()
        result = await _invoke(
            mw, "bmoni_money_transactions",
            {"user_id": "u-1", "smart_wallet_id": "w-1"}, called=called,
        )
        check("own-user read dispatches", called == ["bmoni_money_transactions"])


async def test_admin_list_tools_filtering() -> None:
    from fastmcp.server.middleware import MiddlewareContext
    import mcp_types as mt

    tmp = tempfile.mkdtemp()
    tools = [
        mt.Tool(name="bmoni_info_health", description="d", inputSchema={"type": "object", "properties": {}}),
        mt.Tool(name="bmoni_money_send_account", description="d", inputSchema={"type": "object", "properties": {}}),
        mt.Tool(name="bmoni_webhooks_register_config", description="d", inputSchema={"type": "object", "properties": {}}),
        mt.Tool(name="bmoni_employer_offboard", description="d", inputSchema={"type": "object", "properties": {}}),
        mt.Tool(name="bmoni_approvals_approve", description="d", inputSchema={"type": "object", "properties": {}}),
    ]

    context = MiddlewareContext(message={"none": True}, method="tools/list", type="request")

    async def return_all(_context):
        return list(tools)

    with env_patch(BMONI_SCOPED_USER_ID="u-1"):
        mw, _ = _make_middleware(tmp)
        visible = await mw.on_list_tools(context, call_next=return_all)
        names = [t.name for t in visible]
        check("non-admin sees user tools", "bmoni_money_send_account" in names)
        check("non-admin hides webhooks", "bmoni_webhooks_register_config" not in names)
        check("non-admin hides employer", "bmoni_employer_offboard" not in names)
        check("non-admin hides approvals", "bmoni_approvals_approve" not in names)

    with env_patch(
        BMONI_SCOPED_USER_ID="u-admin-1", BMONI_ADMIN_SUBJECTS="u-admin-1"
    ):
        mw, _ = _make_middleware(tmp)
        visible = await mw.on_list_tools(context, call_next=return_all)
        names = [t.name for t in visible]
        check("admin sees admin tools", "bmoni_webhooks_register_config" in names)
        check("admin sees all tools", len(names) == len(tools))


async def test_rate_limiter_trips_after_burst() -> None:
    tmp = tempfile.mkdtemp()
    with env_patch(BMONI_SCOPED_USER_ID="u-1", BMONI_READ_ONLY="0"):
        mw, _ = _make_middleware(tmp, rps=0.01, burst=2)
        called: list = []
        ok_count = 0
        for _ in range(3):
            result = await _invoke(
                mw, "bmoni_money_transactions",
                {"user_id": "u-1", "smart_wallet_id": "w-1"}, called=called,
            )
            if getattr(result, "is_error") is False:
                ok_count += 1
            else:
                check("rate limit message after burst", "rate limit exceeded" in _text_of(result))
        check("burst allows first N calls", ok_count == 2)
        check("burst dispatch count", len(called) == 2)


async def test_audit_redacts_arguments() -> None:
    from bmoni_mcp.audit import AuditLogger, set_audit

    tmp = tempfile.mkdtemp()
    audit_path = f"{tmp}/audit.jsonl"
    secret_sig = "0xTHISISATOTALLYREALSIGNATURE"
    set_audit(AuditLogger(audit_path, sensitive=True))
    try:
        with env_patch(BMONI_SCOPED_USER_ID="u-1", BMONI_AUTO_APPROVE_TOOLS="bmoni_money_submit_signature"):
            mw, _ = _make_middleware(tmp)
            called: list = []
            result = await _invoke(
                mw, "bmoni_money_submit_signature",
                {"user_id": "u-1", "proposal_id": "p-1", "signature": secret_sig},
                called=called,
            )
            check("auto-approved tool dispatches", called == ["bmoni_money_submit_signature"])
    finally:
        set_audit(None)
    transcript = open(audit_path).read()
    check("audit hook emitted tool.call", "tool.call" in transcript)
    check("audit redacts signature arg", secret_sig not in transcript)


async def test_auth_provider_build() -> None:
    from bmoni_mcp.authn import build_auth_provider

    with env_patch(BMONI_MCP_TOKEN="u-1:tok123", BMONI_ADMIN_SUBJECTS="u-1"):
        settings = get_settings()
        check("auth_configured with static token", settings.auth_configured)
        provider = build_auth_provider(settings)
        check("static verifier built", provider is not None)
        tok = await provider.verify_token("tok123")
        check("static token resolves subject", tok is not None and tok.subject == "u-1")
        check("bad static token rejected", await provider.verify_token("wrong") is None)

    with env_patch():
        settings = get_settings()
        check("auth_configured false without tokens", not settings.auth_configured)
        check("no provider without auth config", build_auth_provider(settings) is None)


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
        test_read_only_client,
        test_error_redaction_and_key_not_logged,
        test_upload_guard_rejects_bad_files,
        test_env_pair_guards,
        test_approval_gate_flow,
        test_approval_deny_cooldown_and_expiry,
        test_role_gating_and_user_pinning,
        test_admin_list_tools_filtering,
        test_rate_limiter_trips_after_burst,
        test_audit_redacts_arguments,
        test_auth_provider_build,
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
