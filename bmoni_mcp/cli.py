"""Command-line entrypoint with transport selection."""

from __future__ import annotations

import argparse
import sys

from .config import get_settings
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
        "--list-tools",
        action="store_true",
        help="Print every registered tool name and exit (no server started).",
    )
    return parser


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

    mcp = build_server()

    if transport == "stdio":
        mcp.run(transport="stdio")
        return

    host = args.host or settings.host
    port = args.port or settings.port
    try:
        mcp.run(transport=transport, host=host, port=port)
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
