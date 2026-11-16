"""Backend-only HTTP client with identification, timeouts and bounded retries.

All provider calls go through this module. Response bodies are parsed as JSON
only; HTML is never parsed. Errors are redacted to exception class + HTTP code
before they can reach a ProviderStatus, logs or the client.
"""

from __future__ import annotations

import asyncio
import json
import random
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import settings
from app.logging import log_provider_call


@dataclass(frozen=True)
class HTTPResult:
    """A successful (including 204) JSON fetch."""

    status_code: int
    data: Any
    url: str
    latency_ms: int


class UpstreamError(Exception):
    """A redacted provider failure safe to expose in an API response."""

    def __init__(self, message: str, http_status: int | None = None) -> None:
        self.http_status: int | None = http_status
        super().__init__(message)


class HTTPClient:
    """Async JSON client with a fixed identifying User-Agent.

    Args:
        request_id: Correlation ID used in structured logs.
        provider: Logical provider name used in structured logs.
        transport: Optional httpx transport (``MockTransport`` in unit tests).
        timeout_s: Per-request timeout.
        max_retries: Retries on 429/5xx only; 0 disables retrying.
        backoff_base_s: Base jittered backoff; tests may set to 0.0.
    """

    def __init__(
        self,
        *,
        request_id: str = "",
        provider: str = "",
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_s: float | None = None,
        max_retries: int | None = None,
        backoff_base_s: float | None = None,
    ) -> None:
        self.request_id = request_id
        self.provider = provider
        self.max_retries = settings.max_retries if max_retries is None else max_retries
        self.backoff_base_s = (
            settings.backoff_base_s if backoff_base_s is None else backoff_base_s
        )
        self._client = httpx.AsyncClient(
            transport=transport,
            timeout=timeout_s if timeout_s is not None else settings.timeout_s,
            headers={
                "User-Agent": settings.user_agent,
                "Accept": "application/geo+json, application/json;q=0.9",
            },
            follow_redirects=False,
        )

    async def __aenter__(self) -> "HTTPClient":
        """Enter the async client context."""
        return self

    async def __aexit__(self, *_exc: object) -> None:
        """Close the underlying async client."""
        await self._client.aclose()

    async def get_json(
        self,
        url: str,
        *,
        params: dict[str, str] | None = None,
        accept: str | None = None,
        provider: str | None = None,
    ) -> HTTPResult:
        """Fetch a URL and parse its JSON body.

        204 No Content is a success with ``data=None``. Only 429 and 5xx are
        retried, at most ``max_retries`` times, with jittered backoff. The
        optional ``provider`` label overrides the client-wide log label.
        """
        headers = {"Accept": accept} if accept else None
        log_provider = provider or self.provider
        attempt = 0
        while True:
            started = time.perf_counter()
            try:
                response = await self._client.get(url, params=params, headers=headers)
            except httpx.HTTPError as exc:
                latency_ms = int((time.perf_counter() - started) * 1000)
                error = f"TransportError({type(exc).__name__})"
                log_provider_call(
                    request_id=self.request_id,
                    provider=log_provider,
                    url=url,
                    status="error",
                    http_status=None,
                    latency_ms=latency_ms,
                )
                raise UpstreamError(error) from exc

            latency_ms = int((time.perf_counter() - started) * 1000)
            status_code = response.status_code

            if status_code == 204:
                log_provider_call(
                    request_id=self.request_id,
                    provider=log_provider,
                    url=url,
                    status="no_content",
                    http_status=status_code,
                    latency_ms=latency_ms,
                )
                return HTTPResult(204, None, str(response.request.url), latency_ms)

            if status_code == 429 or 500 <= status_code < 600:
                if attempt < self.max_retries:
                    delay = self.backoff_base_s * (2**attempt) * (1.0 + random.random())
                    attempt += 1
                    if delay > 0:
                        await asyncio.sleep(delay)
                    continue
                log_provider_call(
                    request_id=self.request_id,
                    provider=log_provider,
                    url=url,
                    status="error",
                    http_status=status_code,
                    latency_ms=latency_ms,
                )
                raise UpstreamError(f"HTTPError(status={status_code})", status_code)

            if status_code >= 400:
                log_provider_call(
                    request_id=self.request_id,
                    provider=log_provider,
                    url=url,
                    status="error",
                    http_status=status_code,
                    latency_ms=latency_ms,
                )
                raise UpstreamError(f"HTTPError(status={status_code})", status_code)

            try:
                data: Any = response.json()
            except (ValueError, json.JSONDecodeError) as exc:
                log_provider_call(
                    request_id=self.request_id,
                    provider=log_provider,
                    url=url,
                    status="malformed_json",
                    http_status=status_code,
                    latency_ms=latency_ms,
                )
                raise UpstreamError(
                    f"MalformedJSON(status={status_code})", status_code
                ) from exc

            log_provider_call(
                request_id=self.request_id,
                provider=log_provider,
                url=url,
                status="ok",
                http_status=status_code,
                latency_ms=latency_ms,
            )
            return HTTPResult(status_code, data, str(response.request.url), latency_ms)
