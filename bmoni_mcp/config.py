"""Runtime configuration.

All configuration is read from environment variables only (optionally
seeded from a local ``.env`` file if python-dotenv is installed). There
are no hard-coded endpoint/credential defaults: the server fails fast
with an actionable message if a required variable is missing when a
tool that needs it is invoked.

Environment variables
---------------------
BMONI_BASE_URL           Base URL of the BMONI Embedded API.
                         Example: https://embedded.api.bmoni.com
BMONI_API_KEY            Partner API key sent as the ``x-api-key`` header.
BMONI_TIMEOUT_SECONDS    HTTP timeout (default 30).
BMONI_TRANSPORT          Default MCP transport: stdio | http | sse.
BMONI_HOST               Host to bind for http/sse transports (default 127.0.0.1).
BMONI_PORT               Port to bind for http/sse transports (default 8000).
"""

import os

try:  # python-dotenv is optional; keep the server importable without it
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv not installed
    pass


class Settings:
    """Read-only view over the BMONI_* environment."""

    def __init__(self) -> None:
        self.base_url: str = os.getenv("BMONI_BASE_URL", "").strip().rstrip("/")
        self.api_key: str = os.getenv("BMONI_API_KEY", "").strip()
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

    def missing(self) -> list[str]:
        """Names of required-but-unset configuration values."""
        missing: list[str] = []
        if not self.base_url:
            missing.append("BMONI_BASE_URL")
        if not self.api_key:
            missing.append("BMONI_API_KEY")
        return missing

    def configuration_error(self) -> str:
        return (
            "The BMONI MCP server is not configured. Set the following "
            f"environment variables: {', '.join(self.missing())}. "
            "For example:\n"
            "  export BMONI_BASE_URL='https://<your-bmoni-host>'   # BMONI Embedded API host\n"
            "  export BMONI_API_KEY='<your partner api key>'       # sent as x-api-key"
        )


def get_settings() -> Settings:
    return Settings()
