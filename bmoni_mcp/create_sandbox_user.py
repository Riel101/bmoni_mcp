"""Create a BMONI sandbox (developer) test user and print how to scope to it.

Run with:  python -m bmoni_mcp.create_sandbox_user

Every session is scoped to an existing BMONI user id, so to run a live test
you first need a user id to put in ``BMONI_SCOPED_USER_ID`` (stdio) or to map
into ``BMONI_MCP_TOKENS`` (http/sse). This helper creates that test user under
your developer key and prints the exact lines to add to ``.env``.

Fail-closed guards mirror the smoke suite:
- only runs when ``BMONI_ENV=sandbox`` and the sandbox credential pair is set;
- hard-refuses if production credentials are present in the same process.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from bmoni_mcp.api import BmoniClient  # noqa: E402
from bmoni_mcp.config import get_settings  # noqa: E402
from bmoni_mcp.env_guard import resolve_credentials  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m bmoni_mcp.create_sandbox_user",
        description=(
            "Create a sandbox test user under your developer API key and print "
            "how to scope a session to it."
        ),
    )
    parser.add_argument(
        "--email",
        default=None,
        help="Unique email for the test user (default: auto-generated).",
    )
    parser.add_argument(
        "--first-name",
        default=None,
        help="First name (default: 'Sandbox').",
    )
    parser.add_argument(
        "--phone-number",
        default=None,
        help="E.164 phone (default: auto-generated +2348xxxxxxxxx).",
    )
    parser.add_argument(
        "--no-env-hints",
        action="store_true",
        help="Print only the created user, not the .env export lines.",
    )
    return parser


def _fail(message: str) -> int:
    print(message, file=sys.stderr)
    return 2


def _random_phone() -> str:
    digits = "".join(str(uuid.uuid4().int)[-9:] for _ in range(2))[:10]
    return f"+2348{digits[-9:]}"


async def create_user(email: str, first_name: str, phone_number: str) -> dict:
    settings = get_settings()
    base_url, api_key = resolve_credentials(settings)
    client = BmoniClient(
        base_url,
        api_key,
        timeout=settings.timeout,
        error_body_echo="1",
    )
    created = await client.post(
        "/v1/users",
        json_body={
            "email": email,
            "firstName": first_name,
            "phoneNumber": phone_number,
        },
    )
    return created if isinstance(created, dict) else {"raw": created}


async def _run(args) -> int:
    settings = get_settings()
    if settings.api_key or settings.base_url:
        return _fail(
            "REFUSED: production credentials are set in this process "
            "(BMONI_API_KEY/BMONI_BASE_URL). Test users must only be created on "
            "the developer (sandbox) API. Unset the production pair first."
        )
    if settings.env != "sandbox":
        return _fail(
            "BMONI_ENV must be 'sandbox' to create a sandbox test user."
        )
    if not settings.sandbox_base_url or not settings.sandbox_api_key:
        return _fail(
            "BMONI_SANDBOX_BASE_URL / BMONI_SANDBOX_API_KEY are not set "
            "(developer API link + developer API key)."
        )

    email = args.email or f"mcp.sandbox.{uuid.uuid4().hex[:12]}@example.test"
    first_name = args.first_name or "Sandbox"
    phone_number = args.phone_number or _random_phone()

    print(f"Creating sandbox user on {settings.sandbox_base_url} ...")
    try:
        created = await create_user(email, first_name, phone_number)
    except Exception as exc:  # noqa: BLE001
        return _fail(f"User creation failed: {exc}")

    user_id = created.get("id")
    if not user_id:
        return _fail(f"User creation did not return an id: {created!r}")

    print("\nSandbox test user created:")
    print(f"  user_id   = {user_id}")
    print(f"  email     = {email}")
    print(f"  first_name= {first_name}")
    print(f"  phone     = {phone_number}")

    if not args.no_env_hints:
        print("\nAdd to .env to run a stdio live test scoped to this user:")
        print(f"  BMONI_SCOPED_USER_ID={user_id}")
        print("\nOr, for an http/sse client, map this user to a bearer token:")
        print(f"  BMONI_MCP_TOKENS={user_id}:<a-long-random-token>")
    print("\nRe-run this helper to create another test user when needed.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return asyncio.run(_run(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
