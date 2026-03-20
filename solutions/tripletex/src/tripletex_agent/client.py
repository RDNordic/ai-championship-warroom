"""Thin async Tripletex API client for the challenge proxy."""

from __future__ import annotations

import base64
from typing import Any

import httpx

from .models import TripletexCredentials


class TripletexAPIError(RuntimeError):
    """Raised when the Tripletex proxy returns an unexpected response."""

    def __init__(self, message: str, *, status_code: int | None = None, detail: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


class TripletexClient:
    """Authenticated client used by workflows to call the Tripletex proxy."""

    def __init__(
        self,
        *,
        base_url: str,
        session_token: str,
        timeout: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.session_token = session_token
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._default_headers(session_token),
            timeout=timeout,
            transport=transport,
        )

    @classmethod
    def from_credentials(
        cls,
        credentials: TripletexCredentials,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> "TripletexClient":
        return cls(
            base_url=credentials.base_url,
            session_token=credentials.basic_auth_password(),
            transport=transport,
        )

    async def __aenter__(self) -> "TripletexClient":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    @staticmethod
    def select_fields(*fields: str) -> str:
        return ",".join(field for field in fields if field)

    @staticmethod
    def unwrap_value(payload: Any) -> Any:
        if isinstance(payload, dict) and "value" in payload:
            return payload["value"]
        return payload

    @staticmethod
    def unwrap_values(payload: Any) -> list[Any]:
        if isinstance(payload, dict):
            values = payload.get("values")
            if isinstance(values, list):
                return values
        return []

    @staticmethod
    def _default_headers(session_token: str) -> dict[str, str]:
        raw = f"0:{session_token}".encode("utf-8")
        encoded = base64.b64encode(raw).decode("ascii")
        return {
            "Authorization": f"Basic {encoded}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        expected_status: tuple[int, ...] = (200,),
    ) -> Any:
        return await self.request("GET", path, params=params, expected_status=expected_status)

    async def post(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
        expected_status: tuple[int, ...] = (200, 201),
    ) -> Any:
        return await self.request(
            "POST",
            path,
            params=params,
            json_body=json_body,
            expected_status=expected_status,
        )

    async def put(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
        expected_status: tuple[int, ...] = (200, 201),
    ) -> Any:
        return await self.request(
            "PUT",
            path,
            params=params,
            json_body=json_body,
            expected_status=expected_status,
        )

    async def delete(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        expected_status: tuple[int, ...] = (200, 202, 204),
    ) -> Any:
        return await self.request("DELETE", path, params=params, expected_status=expected_status)

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
        expected_status: tuple[int, ...] = (200,),
    ) -> Any:
        response = await self._client.request(method, path, params=params, json=json_body)
        payload = self._decode_response(response)

        if response.status_code not in expected_status:
            raise TripletexAPIError(
                f"Tripletex {method} {path} failed",
                status_code=response.status_code,
                detail=payload,
            )

        return payload

    @staticmethod
    def _decode_response(response: httpx.Response) -> Any:
        if response.status_code == 204 or not response.content:
            return None

        content_type = response.headers.get("content-type", "")
        if "json" in content_type:
            return response.json()

        return response.text
