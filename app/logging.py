"""Correlation IDs and structured, redacted JSON logging for RouteGuard."""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

LOGGER = logging.getLogger("routeguard")
if not LOGGER.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    LOGGER.addHandler(_handler)
LOGGER.setLevel(logging.INFO)


def new_request_id() -> str:
    """Return a fresh correlation identifier."""
    return uuid.uuid4().hex


def emit(event: str, **fields: Any) -> None:
    """Emit one structured JSON log line. Payloads are never logged."""
    record: dict[str, Any] = {"event": event}
    record.update(fields)
    LOGGER.info(json.dumps(record, default=str, sort_keys=True))


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Attach a request ID and log one completion line per HTTP request."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        request_id = request.headers.get("x-request-id") or new_request_id()
        request.state.request_id = request_id
        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            latency_ms = int((time.perf_counter() - started) * 1000)
            emit(
                "http_request",
                request_id=request_id,
                method=request.method,
                route=request.url.path,
                status=status_code,
                latency_ms=latency_ms,
            )


def log_assessment(
    *,
    request_id: str,
    route: dict[str, str],
    date: str,
    classification: str,
    confidence: str,
    degraded: bool,
    evidence_counts: dict[str, int],
) -> None:
    """Log a completed assessment in the documented structured format."""
    emit(
        "assessment_complete",
        request_id=request_id,
        route=f"{route.get('origin_iata', '?')}-{route.get('destination_iata', '?')}",
        date=date,
        classification=classification,
        confidence=confidence,
        degraded=degraded,
        evidence_counts=evidence_counts,
    )


def log_provider_call(
    *,
    request_id: str,
    provider: str,
    url: str,
    status: str,
    http_status: int | None,
    latency_ms: int,
) -> None:
    """Log one outbound provider call without request or response bodies."""
    emit(
        "provider_call",
        request_id=request_id,
        provider=provider,
        url=url,
        outcome=status,
        http_status=http_status,
        latency_ms=latency_ms,
    )
