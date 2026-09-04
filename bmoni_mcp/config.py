"""Runtime configuration.

All configuration is read from environment variables only (optionally
seeded from a local ``.env`` file if python-dotenv is installed). There are
no hard-coded endpoint/credential defaults: the server fails fast with an
actionable message when a required value is missing when a tool that needs
it is invoked.

Every security-sensitive knob is fail-closed by default: the restricted
behavior is what you get when a variable is missing, never the exposed one.

Environment variables
---------------------
BMONI_ENV                      sandbox | production. Chooses which credential
                               pair is active. No default that implies prod;
                               see ``bmoni_mcp/env_guard.py``.
BMONI_BASE_URL / BMONI_API_KEY       Production pair (BMONI_ENV=production).
BMONI_SANDBOX_BASE_URL /             Developer (sandbox) pair
BMONI_SANDBOX_API_KEY                (BMONI_ENV=sandbox). Never production.
BMONI_TIMEOUT_SECONDS           HTTP timeout (default 30).
BMONI_TRANSPORT                 Default MCP transport: stdio | http | sse.
BMONI_HOST / BMONI_PORT         Bind address for http/sse (default 127.0.0.1).
BMONI_READ_ONLY                 1 refuses every mutating request in the client.
BMONI_ERROR_BODY_ECHO           0 | 1 | masked (default masked). How much of a
                               BMONI error body is echoed back to the caller.
BMONI_SCOPED_USER_ID            BMONI user id that a local stdio session is
                               scoped to (identity pinned to the OS user).
BMONI_ADMIN_SUBJECTS            Comma-separated subjects granted role=admin
                               (controls admin tools + approval tools).
BMONI_MCP_TOKENS                Static bearer allowlist as
                               ``sub:token[,sub:token...]`` for http/sse.
BMONI_MCP_JWT_ISSUER /          JWT verification for http/sse: issuer and
BMONI_MCP_JWT_AUDIENCE          audience claims to require, plus a JWKS uri
BMONI_MCP_JWKS_URI /            (BMONI_MCP_JWKS_URI) or a static public key
BMONI_MCP_JWT_PUBLIC_KEY        (BMONI_MCP_JWT_PUBLIC_KEY). The token ``sub``
                               claim is the BMONI user id.
BMONI_ALLOWED_ORIGINS           Comma-separated browser origins allowed to call
                               the http/sse endpoint (CORS + request guard).
BMONI_AUDIT_LOG                 File to append JSONL audit records to, or
                               "stdout". Empty = audit off.
BMONI_AUDIT_LOG_SENSITIVE       0 strips sensitive result fields (default 1).
BMONI_APPROVAL_TTL_SECONDS      Approval validity (default 600).
BMONI_APPROVAL_DENY_COOLDOWN    Seconds a denied call stays blocked (default 300).
BMONI_APPROVAL_MAX_PENDING      Per-principal pending cap (default 100).
BMONI_APPROVAL_DB               sqlite path for approval records. Empty = the
                               default under ~/.bmoni_mcp/ (created on demand).
BMONI_APPROVAL_CALLBACK_URL     Operator UI endpoint notified of new approvals.
BMONI_APPROVAL_WEBHOOK_SECRET   HMAC key for the approval callback.
BMONI_AUTO_APPROVE_TOOLS        Comma-separated tool names whose approvals are
                               auto-granted (operator widening; default empty).
BMONI_HITL_GRAY                 1 widens the "gray" tools to require approval.
BMONI_RATE_LIMIT_RPS /          Per-principal token bucket (default 10 / 20).
BMONI_RATE_LIMIT_BURST
BMONI_MAX_CONCURRENT            Max in-flight tool calls (0 = unlimited).
BMONI_UPLOAD_MAX_MB             Max uploaded file size (default 5).
"""

from __future__ import annotations

import os
from pathlib import Path

try:  # python-dotenv is optional; keep the server importable without it
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv not installed
    pass

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}
ENV_SANDBOX = "sandbox"
ENV_PRODUCTION = "production"


def _get_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    val = raw.strip().lower()
    if val in _TRUE:
        return True
    if val in _FALSE:
        return False
    return default


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return default


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw.strip())
    except ValueError:
        return default


def _get_list(name: str) -> list[str]:
    raw = os.getenv(name, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


class Settings:
    """Read-only view over the BMONI_* environment."""

    def __init__(self) -> None:
        # Environment selector ("" means "not chosen yet" -> restricted).
        self.env: str = (os.getenv("BMONI_ENV", "") or "").strip().lower()

        # Production pair.
        self.base_url: str = os.getenv("BMONI_BASE_URL", "").strip().rstrip("/")
        self.api_key: str = os.getenv("BMONI_API_KEY", "").strip()

        # Developer (sandbox) pair. Stored only in the operator's env; never
        # logged, never returned by any tool.
        self.sandbox_base_url: str = (
            os.getenv("BMONI_SANDBOX_BASE_URL", "").strip().rstrip("/")
        )
        self.sandbox_api_key: str = os.getenv("BMONI_SANDBOX_API_KEY", "").strip()

        try:
            self.timeout: float = float(os.getenv("BMONI_TIMEOUT_SECONDS", "30"))
        except ValueError:
            self.timeout = 30.0
        self.transport: str = (os.getenv("BMONI_TRANSPORT", "stdio") or "stdio").lower()
        self.host: str = os.getenv("BMONI_HOST", "127.0.0.1") or "127.0.0.1"
        try:
            self.port: int = int(os.getenv("BMONI_PORT", "8000"))
        except ValueError:
            self.port = 8000

        # -- security knobs -------------------------------------------------
        self.read_only: bool = _get_bool("BMONI_READ_ONLY", False)
        self.error_body_echo: str = (
            os.getenv("BMONI_ERROR_BODY_ECHO", "masked") or "masked"
        ).strip().lower()
        if self.error_body_echo not in ("0", "1", "masked"):
            self.error_body_echo = "masked"

        self.scoped_user_id: str = os.getenv("BMONI_SCOPED_USER_ID", "").strip()
        self.admin_subjects: list[str] = _get_list("BMONI_ADMIN_SUBJECTS")
        mcp_tokens: list[str] = _get_list("BMONI_MCP_TOKENS")
        single_token: str = os.getenv("BMONI_MCP_TOKEN", "").strip()
        if single_token:
            mcp_tokens.append(single_token)
        self.mcp_tokens: list[str] = mcp_tokens
        self.jwt_issuer: str = os.getenv("BMONI_MCP_JWT_ISSUER", "").strip()
        self.jwt_audience: str = os.getenv("BMONI_MCP_JWT_AUDIENCE", "").strip()
        self.jwks_uri: str = os.getenv("BMONI_MCP_JWKS_URI", "").strip()
        self.jwt_public_key: str = os.getenv("BMONI_MCP_JWT_PUBLIC_KEY", "").strip()
        self.jwt_algorithm: str = os.getenv("BMONI_MCP_JWT_ALGORITHM", "").strip()
        self.allowed_origins: list[str] = _get_list("BMONI_ALLOWED_ORIGINS")

        # -- audit ----------------------------------------------------------
        self.audit_log: str = os.getenv("BMONI_AUDIT_LOG", "").strip()
        self.audit_log_sensitive: bool = _get_bool("BMONI_AUDIT_LOG_SENSITIVE", True)

        # -- approvals ------------------------------------------------------
        self.approval_ttl_seconds: int = _get_int("BMONI_APPROVAL_TTL_SECONDS", 600)
        self.approval_deny_cooldown: int = _get_int(
            "BMONI_APPROVAL_DENY_COOLDOWN", 300
        )
        self.approval_max_pending: int = _get_int("BMONI_APPROVAL_MAX_PENDING", 100)
        self.approval_db: str = os.getenv("BMONI_APPROVAL_DB", "").strip()
        self.approval_callback_url: str = os.getenv(
            "BMONI_APPROVAL_CALLBACK_URL", ""
        ).strip()
        self.approval_webhook_secret: str = os.getenv(
            "BMONI_APPROVAL_WEBHOOK_SECRET", ""
        ).strip()
        self.auto_approve_tools: list[str] = _get_list("BMONI_AUTO_APPROVE_TOOLS")
        self.hitl_gray: bool = _get_bool("BMONI_HITL_GRAY", False)

        # -- limits ---------------------------------------------------------
        try:
            self.rate_limit_rps: float = float(os.getenv("BMONI_RATE_LIMIT_RPS", "10"))
        except ValueError:
            self.rate_limit_rps = 10.0
        try:
            self.rate_limit_burst: int = int(os.getenv("BMONI_RATE_LIMIT_BURST", "20"))
        except ValueError:
            self.rate_limit_burst = 20
        self.max_concurrent: int = _get_int("BMONI_MAX_CONCURRENT", 0)
        try:
            self.upload_max_mb: float = float(os.getenv("BMONI_UPLOAD_MAX_MB", "5"))
        except ValueError:
            self.upload_max_mb = 5.0

    # -- derived helpers ----------------------------------------------------
    @property
    def auth_configured(self) -> bool:
        """True when http/sse bearer auth is configured (static or JWT)."""
        return bool(self.mcp_tokens) or bool(self.jwt_issuer and self.jwks_uri) or bool(
            self.jwt_issuer and self.jwt_public_key
        )

    @property
    def approval_default_db(self) -> str:
        if self.approval_db:
            return self.approval_db
        return str(Path.home() / ".bmoni_mcp" / "approvals.sqlite3")

    def is_admin_subject(self, subject: str) -> bool:
        return subject in self.admin_subjects

    def missing(self) -> list[str]:
        """Names of configuration values that are missing or inconsistent."""
        return _missing_for_env(self)

    def configuration_error(self) -> str:
        missing = self.missing()
        return (
            "The BMONI MCP server is not configured. "
            + _explain_missing(missing)
        )


def _missing_for_env(settings: Settings) -> list[str]:
    """Compute the missing/unsafe config for the active BMONI_ENV."""
    from . import env_guard  # local import to avoid cycles

    missing: list[str] = []
    env = settings.env
    if env not in (ENV_SANDBOX, ENV_PRODUCTION):
        missing.append("BMONI_ENV (choose 'sandbox' or 'production')")
        # Without a chosen env the legacy single-pair layout is the only
        # permitted form: production creds only, nothing else set.
        if not settings.base_url:
            missing.append("BMONI_BASE_URL")
        if not settings.api_key:
            missing.append("BMONI_API_KEY")
        if settings.sandbox_base_url or settings.sandbox_api_key:
            missing.append("BMONI_ENV (sandbox credentials set without a choice)")
        return missing

    if env == ENV_SANDBOX:
        if not settings.sandbox_base_url:
            missing.append("BMONI_SANDBOX_BASE_URL")
        if not settings.sandbox_api_key:
            missing.append("BMONI_SANDBOX_API_KEY")
        if settings.api_key:
            missing.append("BMONI_API_KEY (production key must not be set in sandbox)")
        if settings.base_url:
            missing.append("BMONI_BASE_URL (production URL must not be set in sandbox)")
    else:  # production
        if not settings.base_url:
            missing.append("BMONI_BASE_URL")
        if not settings.api_key:
            missing.append("BMONI_API_KEY")
        if not settings.base_url and not settings.api_key and settings.sandbox_base_url:
            missing.append("BMONI_BASE_URL (only sandbox credentials are present)")
    return missing


def _explain_missing(missing: list[str]) -> str:
    return (
        "Set the following environment variables: "
        f"{', '.join(missing)}. "
        "For example:\n"
        "  export BMONI_ENV='sandbox'                       # dev / smoke tests\n"
        "  export BMONI_SANDBOX_BASE_URL='https://<dev-host>'"
        "  # developer API link\n"
        "  export BMONI_SANDBOX_API_KEY='<developer api key>'\n"
        "  # or for production:\n"
        "  # export BMONI_ENV='production'\n"
        "  # export BMONI_BASE_URL='https://<prod-host>'\n"
        "  # export BMONI_API_KEY='<partner api key>'\n"
        "See .env.example for the full runbook."
    )


def get_settings() -> Settings:
    return Settings()
