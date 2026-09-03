"""Thin async HTTP client for the BMONI Embedded API.

Every request authenticates with the ``x-api-key`` header, as required by
the API reference. Responses are returned as parsed JSON (dict/list). The
two PDF endpoints are returned as base64 text so the result stays a valid
JSON-serializable MCP tool return value.
"""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx


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
    """Stateless wrapper around the BMONI REST API."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._transport = transport

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
            raise BmoniError(
                "BMONI API request failed",
                method=method,
                path=path,
                status_code=response.status_code,
                body=body,
            )
        return self._decode(response)

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
