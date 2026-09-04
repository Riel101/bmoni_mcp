"""Shared helpers for tool implementations."""

from __future__ import annotations

from typing import Any

from ..api import BmoniClient
from ..config import get_settings
from ..env_guard import resolve_credentials

_client: BmoniClient | None = None


def get_client(transport: Any | None = None) -> BmoniClient:
    """Return a lazily-created, env-configured BMONI client.

    The active endpoint + API key pair is resolved purely from ``BMONI_ENV``
    (sandbox -> developer API link/key, production -> production pair) and is
    fail-closed: a missing/inconsistent environment raises an actionable
    error and no live request is ever attempted against the wrong host.
    Configuration is read lazily so the server can be imported and inspected
    without credentials being present.
    """
    global _client
    if _client is None or transport is not None:
        settings = get_settings()
        missing = settings.missing()
        if missing:
            raise RuntimeError(settings.configuration_error())
        try:
            base_url, api_key = resolve_credentials(settings)
        except RuntimeError as exc:
            raise RuntimeError(settings.configuration_error()) from exc
        client = BmoniClient(
            base_url,
            api_key,
            timeout=settings.timeout,
            transport=transport,
            read_only=settings.read_only,
            error_body_echo=settings.error_body_echo,
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
