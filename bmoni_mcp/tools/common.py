"""Shared helpers for tool implementations."""

from __future__ import annotations

from typing import Any

from ..api import BmoniClient
from ..config import get_settings

_client: BmoniClient | None = None


def get_client(transport: Any | None = None) -> BmoniClient:
    """Return a lazily-created, env-configured BMONI client.

    Fails with an actionable message when BMONI_BASE_URL/BMONI_API_KEY
    have not been provided. Configuration is read lazily so the server
    can be imported and inspected without credentials being present.
    """
    global _client
    if _client is None or transport is not None:
        settings = get_settings()
        missing = settings.missing()
        if missing:
            raise RuntimeError(settings.configuration_error())
        client = BmoniClient(
            settings.base_url,
            settings.api_key,
            timeout=settings.timeout,
            transport=transport,
        )
        if transport is None:
            _client = client
        return client
    return _client


def reset_client() -> None:
    """Drop the cached client (used mainly by tests)."""
    global _client
    _client = None


def payload(**fields: Any) -> dict[str, Any]:
    """Build a request body, dropping any field the agent left unset."""
    return {k: v for k, v in fields.items() if v is not None}
