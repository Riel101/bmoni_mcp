"""Live smoke suite against the developer (sandbox) BMONI API.

Run with:  python tests/test_sandbox_smoke.py

Rules (fail closed):
- Runs ONLY when ``BMONI_ENV=sandbox`` AND the sandbox credential pair is set.
- Skipped otherwise (exit 0, message printed).
- Hard-refuses (exit non-zero) if production credentials are also present in
  the same process - a mixed/dev .env is an explicit error, never a silent
  switch to the production host.

Covers a representative read-only journey (create user -> KYC options ->
balances/readiness -> read-only checks) against the developer API. Run before
every production deploy.
"""

from __future__ import annotations

import asyncio
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from bmoni_mcp.api import BmoniClient  # noqa: E402
from bmoni_mcp.config import get_settings  # noqa: E402
from bmoni_mcp.env_guard import resolve_credentials  # noqa: E402

PASSED: list[str] = []
FAILED: list[str] = []


def check(label: str, condition: bool, extra: str = "") -> None:
    if condition:
        PASSED.append(label)
        print(f"  ok     {label}")
    else:
        FAILED.append(label)
        print(f"  FAILED {label} {extra}")


def gate() -> int:
    settings = get_settings()
    if settings.api_key or settings.base_url:
        print(
            "REFUSED: BMONI_ENV=sandbox but production credentials are set in "
            "this process (BMONI_API_KEY/BMONI_BASE_URL). This smoke suite must "
            "never run against production - unset the production pair first."
        )
        return 3
    if settings.env != "sandbox":
        print(
            "SKIPPED: test_sandbox_smoke.py only runs with BMONI_ENV=sandbox "
            "and the sandbox credential pair set."
        )
        return 0
    if not settings.sandbox_base_url or not settings.sandbox_api_key:
        print(
            "SKIPPED: BMONI_SANDBOX_BASE_URL / BMONI_SANDBOX_API_KEY are not set."
        )
        return 0
    return -1  # run


async def journey() -> None:
    settings = get_settings()
    base_url, api_key = resolve_credentials(settings)
    client = BmoniClient(
        base_url,
        api_key,
        timeout=settings.timeout,
        error_body_echo="1",
    )
    print(f"\nRunning sandbox smoke against {base_url}")

    # Global read-only checks first.
    try:
        health = await client.get("/v1/health")
        check("health endpoint reachable", health is not None)
    except Exception as exc:  # noqa: BLE001
        check("health endpoint reachable", False, str(exc)[:200])

    try:
        supported = await client.get("/v1/smart-wallets/supported-currencies")
        check("supported currencies reachable", isinstance(supported, list))
    except Exception as exc:  # noqa: BLE001
        check("supported currencies reachable", False, str(exc)[:200])

    try:
        assets = await client.get("/v1/deposit/supported-assets")
        check("deposit supported assets reachable", assets is not None)
    except Exception as exc:  # noqa: BLE001
        check("deposit supported assets reachable", False, str(exc)[:200])

    # User journey (creates a throwaway sandbox user).
    user_id = None
    email = f"smoke.{os.getpid()}@example.test"
    try:
        created = await client.post(
            "/v1/users",
            json_body={
                "email": email,
                "firstName": "Smoke",
                "phoneNumber": "+2348012345678",
            },
        )
        if isinstance(created, dict) and created.get("id"):
            user_id = created["id"]
            check("create sandbox user", True)
            print(f"  user_id  = {user_id}")
        else:
            check("create sandbox user", False, f"unexpected: {created!r}"[:200])
    except Exception as exc:  # noqa: BLE001
        check("create sandbox user", False, str(exc)[:300])

    if user_id:
        for label, coro in (
            ("KYC options", client.get(f"/v1/users/{user_id}/kyc/options")),
            ("KYC readiness", client.get(f"/v1/users/{user_id}/kyc/readiness")),
            ("wallet balances", client.get(f"/v1/users/{user_id}/smart-wallets/account/balances")),
            ("exchange rate USDB->NGN", client.get(f"/v1/users/{user_id}/exchange/rate/USDB/NGN")),
        ):
            try:
                result = await coro
                check(label, result is not None)
            except Exception as exc:  # noqa: BLE001
                check(label, False, str(exc)[:200])


def main() -> int:
    code = gate()
    if code >= 0:
        return code
    try:
        asyncio.run(journey())
    except Exception as exc:  # noqa: BLE001
        print(f"UNHANDLED failure: {exc}")
        FAILED.append("journey")
    print(
        f"\n{len(PASSED)} sandbox checks passed, {len(FAILED)} failed"
    )
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
