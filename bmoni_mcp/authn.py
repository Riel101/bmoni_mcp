"""Principal + role resolution and FastMCP auth provider construction.

Identity model (agreed):
- http/sse: the bearer token's ``sub`` claim is the BMONI ``user_id``. The
  server only validates tokens - it never mints or persists them.
- stdio: identity is pinned from ``BMONI_SCOPED_USER_ID``; trust = the OS user.
- role=admin is granted when the subject is in ``BMONI_ADMIN_SUBJECTS`` (or the
  token carries an ``admin`` scope). Everything else is role=user by default.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .policy import ROLE_ADMIN, ROLE_USER


@dataclass
class Principal:
    subject: str | None = None
    role: str = ROLE_USER
    authenticated: bool = False
    source: str = "unknown"  # token | stdio-env | none
    scopes: list[str] = field(default_factory=list)

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN

    def label(self) -> str:
        return self.subject or "<unauthenticated>"


def _claims_from_token(token: Any) -> dict[str, Any]:
    claims = getattr(token, "claims", None) or {}
    if not isinstance(claims, dict):
        claims = {}
    return claims


def _subject_from_token(token: Any, claims: dict[str, Any]) -> str | None:
    sub = claims.get("sub")
    if sub:
        return str(sub)
    subject = getattr(token, "subject", None)
    if subject:
        return str(subject)
    client_id = getattr(token, "client_id", None)
    return str(client_id) if client_id else None


def resolve_principal() -> Principal:
    """Resolve the current caller from token claims, or stdio env fallback.

    Returns an unauthenticated ``Principal(None, 'user', authenticated=False)``
    when neither a token nor ``BMONI_SCOPED_USER_ID`` is present - callers
    treat that as the fail-closed restricted path.
    """
    from .config import get_settings

    settings = get_settings()

    try:  # http/sse bearer token (stdlib-only when absent)
        from fastmcp.server.dependencies import get_access_token

        token = get_access_token()
    except Exception:  # pragma: no cover - defensive
        token = None

    if token is not None:
        claims = _claims_from_token(token)
        subject = _subject_from_token(token, claims)
        scopes = list(getattr(token, "scopes", []) or [])
        admin = (
            bool(subject and settings.is_admin_subject(subject))
            or "admin" in scopes
        )
        return Principal(
            subject=subject,
            role=ROLE_ADMIN if admin else ROLE_USER,
            authenticated=subject is not None,
            source="token",
            scopes=scopes,
        )

    # stdio fallback: identity pinned from env; trust = the OS user.
    scoped = settings.scoped_user_id
    if scoped:
        return Principal(
            subject=scoped,
            role=ROLE_ADMIN if settings.is_admin_subject(scoped) else ROLE_USER,
            authenticated=True,
            source="stdio-env",
        )

    return Principal(role=ROLE_USER, authenticated=False, source="none")


def is_loopback_host(host: str) -> bool:
    lowered = host.strip().lower()
    if lowered in ("localhost", "::1", "0:0:0:0:0:0:0:1"):
        return True
    if lowered.startswith("127."):
        return True
    return False


def build_auth_provider(settings) -> Any | None:
    """Build the FastMCP AuthProvider for http/sse, or None if unconfigured.

    Static tokens: ``BMONI_MCP_TOKENS=sub:token[,sub:token...]``.
    JWT: requires BMONI_MCP_JWT_ISSUER plus a JWKS uri or a public key.
    """
    if getattr(settings, "mcp_tokens", []):
        from fastmcp.server.auth.providers.jwt import StaticTokenVerifier

        tokens: dict[str, dict[str, Any]] = {}
        for entry in settings.mcp_tokens:
            if ":" in entry:
                subject, token = entry.split(":", 1)
            else:
                subject, token = entry, entry
            subject = subject.strip()
            token = token.strip()
            if not token:
                continue
            tokens[token] = {
                "client_id": "bmoni-mcp",
                "sub": subject,
                "scopes": ["admin"] if settings.is_admin_subject(subject) else [],
            }
        if tokens:
            return StaticTokenVerifier(tokens)
        return None

    if getattr(settings, "jwt_issuer", "") and (
        getattr(settings, "jwks_uri", "") or getattr(settings, "jwt_public_key", "")
    ):
        from fastmcp.server.auth.providers.jwt import JWTVerifier

        kwargs: dict[str, Any] = {
            "issuer": settings.jwt_issuer,
        }
        if settings.jwt_audience:
            kwargs["audience"] = settings.jwt_audience
        if settings.jwks_uri:
            kwargs["jwks_uri"] = settings.jwks_uri
        if settings.jwt_public_key:
            kwargs["public_key"] = settings.jwt_public_key
        if settings.jwt_algorithm:
            kwargs["algorithm"] = settings.jwt_algorithm
        return JWTVerifier(**kwargs)

    return None
