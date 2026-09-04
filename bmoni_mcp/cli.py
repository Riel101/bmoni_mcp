"""Command-line entrypoint with transport selection and fail-closed guards."""

from __future__ import annotations

import argparse
import sys

from .authn import is_loopback_host
from .config import get_settings
from .env_guard import assert_env_pair
from .server import build_server

TRANSPORTS = ("stdio", "http", "sse")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bmoni-mcp",
        description="MCP server for the BMONI Embedded API.",
    )
    parser.add_argument(
        "--transport",
        choices=TRANSPORTS,
        default=None,
        help="MCP transport. Defaults to BMONI_TRANSPORT env or 'stdio'.",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Host to bind for http/sse. Defaults to BMONI_HOST or 127.0.0.1.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port to bind for http/sse. Defaults to BMONI_PORT or 8000.",
    )
    parser.add_argument(
        "--allowed-origins",
        default=None,
        help="Comma-separated browser origins allowed to reach an http/sse "
        "endpoint. Overrides BMONI_ALLOWED_ORIGINS. Required when binding a "
        "non-loopback host.",
    )
    parser.add_argument(
        "--list-tools",
        action="store_true",
        help="Print every registered tool name and exit (no server started).",
    )
    return parser


def _fail_closed_http(parser: argparse.ArgumentParser, settings, host: str, origins: list[str]) -> None:
    """Refuse to expose an unauthenticated non-loopback MCP endpoint."""
    if is_loopback_host(host):
        return
    if not settings.auth_configured:
        parser.error(
            "Refusing to bind a non-loopback host without authentication. "
            "Configure BMONI_MCP_TOKENS (static allowlist) or the "
            "BMONI_MCP_JWT_* issuer/audience/JWKS vars first, then set "
            "BMONI_ALLOWED_ORIGINS."
        )
    if not origins:
        parser.error(
            "Refusing to bind a non-loopback host without allowed origins. "
            "Set BMONI_ALLOWED_ORIGINS (or pass --allowed-origins)."
        )


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    settings = get_settings()

    if args.list_tools:
        from .server import tool_names

        for name in tool_names():
            print(name)
        return

    transport = args.transport or settings.transport
    if transport not in TRANSPORTS:
        parser = build_parser()
        parser.error(f"Unknown transport '{transport}'. Choose from {TRANSPORTS}.")

    if transport == "stdio":
        # Identity pinned from BMONI_SCOPED_USER_ID (trust = OS user). Credential
        # pairing is checked eagerly so a mixed .env is an explicit startup error.
        try:
            assert_env_pair(settings)
        except RuntimeError as exc:
            build_parser().error(f"{exc}\n{settings.configuration_error()}")
        mcp = build_server()
        mcp.run(transport="stdio")
        return

    host = args.host or settings.host
    port = args.port or settings.port
    origins = settings.allowed_origins
    if args.allowed_origins:
        origins = [o.strip() for o in args.allowed_origins.split(",") if o.strip()]

    try:
        assert_env_pair(settings)
    except RuntimeError as exc:
        build_parser().error(f"{exc}\n{settings.configuration_error()}")

    _fail_closed_http(build_parser(), settings, host, origins)

    mcp = build_server()
    try:
        mcp.run(
            transport=transport,
            host=host,
            port=port,
            allowed_origins=origins or None,
        )
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
