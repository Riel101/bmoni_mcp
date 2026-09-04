"""Fail-closed guardrail for the sandbox/production credential pair.

``BMONI_ENV`` must be an explicit ``sandbox`` or ``production`` choice. The
developer (sandbox) API link + developer API key are the ONLY credentials a
live pre-production test may ever use; mixing a production key into a sandbox
run (or vice versa) is a hard startup/runtime error, never a silent fallback.

Used by ``config.py``, ``cli.py`` and the sandbox smoke suite.
"""

from __future__ import annotations

from .config import ENV_PRODUCTION, ENV_SANDBOX

_ACTIVE_ENVS = (ENV_SANDBOX, ENV_PRODUCTION)


def is_sandbox() -> bool:
    """True when ``BMONI_ENV=sandbox`` is set explicitly."""
    from .config import get_settings

    return get_settings().env == ENV_SANDBOX


def is_production() -> bool:
    from .config import get_settings

    return get_settings().env == ENV_PRODUCTION


def active_env() -> str:
    """Return the active env label or raise if BMONI_ENV is unset/invalid."""
    from .config import get_settings

    env = get_settings().env
    if env not in _ACTIVE_ENVS:
        raise RuntimeError(
            "BMONI_ENV must be set to 'sandbox' or 'production' (no default that "
            "implies production). No live request was made."
        )
    return env


def assert_env_pair(settings=None) -> str:
    """Validate the active credential pair; raise RuntimeError on any mix.

    Returns the resolved env label (``sandbox`` or ``production``) on success.
    """
    if settings is None:
        from .config import get_settings

        settings = get_settings()

    env = settings.env
    if env not in _ACTIVE_ENVS:
        raise RuntimeError(
            "BMONI_ENV must be 'sandbox' or 'production'. "
            "Refusing to guess a production environment."
        )

    if env == ENV_SANDBOX:
        if settings.api_key or settings.base_url:
            raise RuntimeError(
                "BMONI_ENV=sandbox but a production credential is set in the same "
                "process (BMONI_API_KEY/BMONI_BASE_URL). Unset the production pair "
                "before running against the developer API - refusing to continue."
            )
        if not settings.sandbox_base_url or not settings.sandbox_api_key:
            raise RuntimeError(
                "BMONI_ENV=sandbox requires BMONI_SANDBOX_BASE_URL and "
                "BMONI_SANDBOX_API_KEY (developer API link + developer API key)."
            )
        return ENV_SANDBOX

    # production
    if not settings.base_url or not settings.api_key:
        if settings.sandbox_base_url and not settings.base_url:
            raise RuntimeError(
                "BMONI_ENV=production but only sandbox credentials are present "
                "(BMONI_SANDBOX_*). Set the production BMONI_BASE_URL/BMONI_API_KEY."
            )
        raise RuntimeError(
            "BMONI_ENV=production requires BMONI_BASE_URL and BMONI_API_KEY "
            "(the production Embedded API link + partner key)."
        )
    return ENV_PRODUCTION


def resolve_credentials(settings=None) -> tuple[str, str]:
    """Return the active ``(base_url, api_key)`` for BMONI_ENV, or raise."""
    if settings is None:
        from .config import get_settings

        settings = get_settings()
    env = assert_env_pair(settings)
    if env == ENV_SANDBOX:
        return settings.sandbox_base_url, settings.sandbox_api_key
    return settings.base_url, settings.api_key
