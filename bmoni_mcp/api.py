"""Thin async HTTP client for the BMONI Embedded API.

Every request authenticates with the ``x-api-key`` header, as required by
the API reference. Responses are returned as parsed JSON (dict/list). The
two PDF endpoints are returned as base64 text so the result stays a valid
JSON-serializable MCP tool return value.
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any

import httpx

from .redact import redact

# Pure-read POST endpoints permitted in read-only mode (everything else that
# is not a GET is a mutation and is refused).
_READONLY_ALLOWED_POST = (
    "/cards/sensitive-data",
    "/payouts/validate-account",
)


class BmoniError(Exception):
    """Raised when the BMONI API returns an error or is unreachable."""

    def __init__(
        self,
        message: str,
        *,
        method: str | None = None,
        path: str | None = None,
        status_code: int | None = None,
        body: Any = None,
    ) -> None:
        self.method = method
        self.path = path
        self.status_code = status_code
        self.body = body
        detail = f"{message}"
        if method and path:
            detail += f" ({method} {path})"
        if status_code is not None:
            detail += f" [HTTP {status_code}]"
        if body is not None and body not in ("", None):
            if isinstance(body, (dict, list)):
                body = json.dumps(body, ensure_ascii=False)[:2000]
            detail += f": {body}"
        super().__init__(detail)


class BmoniClient:
    """Stateless wrapper around the BMONI REST API.

    ``read_only`` / ``error_body_echo`` may be passed explicitly; when left as
    None the process environment is consulted on every request so a tool can
    never construct a client that bypasses read-only mode or error redaction.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
        read_only: bool | None = None,
        error_body_echo: str | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._transport = transport
        self._read_only = read_only
        self._error_body_echo = error_body_echo

    # -- low level ---------------------------------------------------------
    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
    ) -> Any:
        if self._read_only_effective() and not self._allowed_readonly(method, path):
            raise BmoniError(
                "Refused: the BMONI MCP server is in read-only mode "
                "(BMONI_READ_ONLY=1) and this request would mutate state",
                method=method,
                path=path,
                status_code=403,
                body=None,
            )

        headers = {
            "x-api-key": self._api_key,
            "Accept": "application/json",
        }
        if json_body is not None:
            headers["Content-Type"] = "application/json"
        url = f"{self._base_url}{path}"
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, headers=headers, transport=self._transport
            ) as client:
                response = await client.request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    data=data,
                    files=files,
                )
        except httpx.HTTPError as exc:  # network / DNS / timeout
            raise BmoniError(f"Could not reach the BMONI API: {exc}", method=method, path=path) from exc

        if response.status_code >= 400:
            try:
                body: Any = response.json()
            except Exception:
                body = response.text
            body = self._scrub_body(body)
            raise BmoniError(
                "BMONI API request failed",
                method=method,
                path=path,
                status_code=response.status_code,
                body=body if self._echo_body_effective() else None,
            )
        return self._scrub_api_key(self._decode(response))

    # -- security helpers ---------------------------------------------------
    def _read_only_effective(self) -> bool:
        if self._read_only is not None:
            return self._read_only
        return os.getenv("BMONI_READ_ONLY", "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )

    def _echo_body_effective(self) -> bool:
        mode = self._echo_mode()
        # '1' echoes the (always-redacted) body; '0' and 'masked' suppress it.
        return mode == "1"

    def _echo_mode(self) -> str:
        if self._error_body_echo is not None:
            mode = self._error_body_echo
        else:
            mode = os.getenv("BMONI_ERROR_BODY_ECHO", "masked").strip().lower() or "masked"
        return mode if mode in ("0", "1", "masked") else "masked"

    @staticmethod
    def _allowed_readonly(method: str, path: str) -> bool:
        if method == "GET":
            return True
        return method == "POST" and any(
            allowed in path for allowed in _READONLY_ALLOWED_POST
        )

    def _scrub_body(self, body: Any) -> Any:
        """Redact sensitive values and scrub the API key from any text."""
        return self._scrub_api_key(redact(body))

    def _scrub_api_key(self, value: Any) -> Any:
        """Recursively remove the literal API key from string leaves."""
        if not self._api_key:
            return value
        if isinstance(value, str):
            return value.replace(self._api_key, "[REDACTED]")
        if isinstance(value, dict):
            return {k: self._scrub_api_key(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._scrub_api_key(v) for v in value]
        return value

    @staticmethod
    def _decode(response: httpx.Response) -> Any:
        content_type = response.headers.get("content-type", "").lower()
        if "application/json" in content_type:
            try:
                return response.json()
            except Exception:
                return response.text
        if response.content:
            return {
                "contentType": content_type or "application/octet-stream",
                "dataBase64": base64.b64encode(response.content).decode("ascii"),
                "hint": "The response is binary; dataBase64 holds its base64 encoding.",
            }
        return {"ok": True}

    # -- convenience verbs -------------------------------------------------
    async def get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        return await self.request("GET", path, params=params)

    async def post(self, path: str, *, json_body: Any = None, params: dict[str, Any] | None = None, **kw: Any) -> Any:
        return await self.request("POST", path, params=params, json_body=json_body, **kw)

    async def put(self, path: str, *, json_body: Any = None) -> Any:
        return await self.request("PUT", path, json_body=json_body)

    async def patch(self, path: str, *, json_body: Any = None) -> Any:
        return await self.request("PATCH", path, json_body=json_body)

    async def delete(self, path: str, *, json_body: Any = None) -> Any:
        return await self.request("DELETE", path, json_body=json_body)
