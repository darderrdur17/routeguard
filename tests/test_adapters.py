"""Provider adapter tests using only httpx.MockTransport — zero live calls."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

import httpx
import pytest

from app.cities import CityRegistry
from app.config import settings
from app.http_client import HTTPClient
from app.providers.awc import AWCAdapter
from app.providers.nws import NWSAdapter
from tests.conftest import make_window, run

ORIGIN = CityRegistry().resolve("JFK")
DESTINATION = CityRegistry().resolve("SFO")
WINDOW = make_window()
NWS_POINTS_PATH = "/points/40.6413,-73.7781"
FORECAST_PATH = "/gridpoints/MTR/85,98/forecast"


def make_client(
    handler: Callable[[httpx.Request], httpx.Response],
    provider: str = "NWS",
    *,
    max_retries: int = 0,
) -> HTTPClient:
    """Build an HTTPClient backed by an in-memory MockTransport."""
    return HTTPClient(
        request_id="test-request",
        provider=provider,
        transport=httpx.MockTransport(handler),
        max_retries=max_retries,
        backoff_base_s=0.0,
    )


def test_nws_happy_path_reads_forecast_url_from_points(
    nws_points: dict[str, Any],
    nws_alerts: dict[str, Any],
    nws_forecast: dict[str, Any],
) -> None:
    """NWS calls points, alerts and the exact forecast URL from points."""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path.startswith("/points/"):
            return httpx.Response(200, json=nws_points, request=request)
        if request.url.path == "/alerts/active":
            return httpx.Response(200, json=nws_alerts, request=request)
        if request.url.path == FORECAST_PATH:
            return httpx.Response(200, json=nws_forecast, request=request)
        return httpx.Response(404, request=request)

    async def scenario() -> Any:
        async with make_client(handler, "NWS") as client:
            return await NWSAdapter(client).fetch(ORIGIN, DESTINATION, WINDOW)

    result = run(scenario())
    assert result.status.status == "OK"
    assert result.status.http_status == 200
    assert len(result.payloads) == 4  # 1 alert + 3 forecast periods
    assert len(calls) == 3
    assert calls[0].url.path == NWS_POINTS_PATH
    assert calls[1].url.params["point"] == ORIGIN.nws_point
    assert calls[2].url.path == FORECAST_PATH
    assert calls[2].url.path == nws_points["properties"]["forecast"].split("gov")[1]
    assert all(
        request.headers["user-agent"] == settings.user_agent for request in calls
    )
    assert all(
        "application/geo+json" in request.headers["accept"] for request in calls
    )


def test_nws_points_http_failure_is_failed_status(nws_points: dict[str, Any]) -> None:
    """A points 5xx disables both NWS signals with a redacted error."""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(500, request=request)

    async def scenario() -> Any:
        async with make_client(handler, "NWS") as client:
            return await NWSAdapter(client).fetch(ORIGIN, DESTINATION, WINDOW)

    result = run(scenario())
    assert result.status.status == "FAILED"
    assert result.status.error == "HTTPError(status=500)"
    assert result.payloads == []
    assert len(calls) == 1
    assert nws_points["properties"]["forecast"].startswith("https://api.weather.gov")


def test_nws_malformed_points_json_is_failed(nws_alerts: dict[str, Any]) -> None:
    """Malformed JSON is never parsed as HTML or leaked to the caller."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/points/"):
            return httpx.Response(
                200,
                text="{not valid json",
                headers={"content-type": "application/json"},
                request=request,
            )
        return httpx.Response(200, json=nws_alerts, request=request)

    async def scenario() -> Any:
        async with make_client(handler, "NWS") as client:
            return await NWSAdapter(client).fetch(ORIGIN, DESTINATION, WINDOW)

    result = run(scenario())
    assert result.status.status == "FAILED"
    assert result.status.error == "MalformedJSON(status=200)"
    assert result.payloads == []


def test_nws_204_alerts_is_success_with_no_data(
    nws_points: dict[str, Any], nws_forecast: dict[str, Any]
) -> None:
    """204 means no active alerts, not an adapter failure."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/points/"):
            return httpx.Response(200, json=nws_points, request=request)
        if request.url.path == "/alerts/active":
            return httpx.Response(204, request=request)
        return httpx.Response(200, json=nws_forecast, request=request)

    async def scenario() -> Any:
        async with make_client(handler, "NWS") as client:
            return await NWSAdapter(client).fetch(ORIGIN, DESTINATION, WINDOW)

    result = run(scenario())
    assert result.status.status == "OK"
    assert "204 No Content" in result.status.note
    assert len(result.payloads) == 3


def test_awc_batches_ids_and_treats_204_as_no_data(awc_taf: list[dict[str, Any]]) -> None:
    """AWC sends one METAR and one TAF call for both ICAO ids."""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/api/data/metar":
            return httpx.Response(204, request=request)
        return httpx.Response(200, json=awc_taf, request=request)

    async def scenario() -> Any:
        async with make_client(handler, "AWC") as client:
            return await AWCAdapter(client).fetch(ORIGIN, DESTINATION, WINDOW)

    result = run(scenario())
    assert result.status.status == "OK"
    assert result.status.http_status == 200
    assert "204 No Content - no current METAR." in result.status.note
    assert len(result.payloads) == 2
    assert len(calls) == 2
    assert calls[0].url.params["ids"] == "KJFK,KSFO"
    assert calls[0].url.params["hours"] == "2"
    assert calls[0].url.params["format"] == "json"
    assert "hours" not in calls[1].url.params
    assert calls[1].url.params["ids"] == "KJFK,KSFO"
    assert all(request.headers["user-agent"] == settings.user_agent for request in calls)


def test_awc_both_204_reports_real_status_and_no_evidence() -> None:
    """Two 204 responses are healthy no-data outcomes, not silent failures."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(204, request=request)

    async def scenario() -> Any:
        async with make_client(handler, "AWC") as client:
            return await AWCAdapter(client).fetch(ORIGIN, DESTINATION, WINDOW)

    result = run(scenario())
    assert result.status.status == "OK"
    assert result.status.http_status == 204
    assert result.payloads == []
    assert "no current METAR" in result.status.note
    assert "no current TAF" in result.status.note


def test_awc_200_json_null_is_degraded_not_ok() -> None:
    """A 200 with a JSON null body is malformed evidence, not healthy no-data."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text="null",
            headers={"content-type": "application/json"},
            request=request,
        )

    async def scenario() -> Any:
        async with make_client(handler, "AWC") as client:
            return await AWCAdapter(client).fetch(ORIGIN, DESTINATION, WINDOW)

    result = run(scenario())
    assert result.status.status in {"DEGRADED", "FAILED"}
    assert result.status.status != "OK"
    assert result.status.note
    assert "Malformed" in result.status.note
    assert result.payloads == []


def test_awc_partial_failure_is_degraded(
    awc_metar: list[dict[str, Any]], awc_taf: list[dict[str, Any]]
) -> None:
    """METAR failure with a healthy TAF is DEGRADED, not a silent empty result."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/data/metar":
            return httpx.Response(500, request=request)
        return httpx.Response(200, json=awc_taf, request=request)

    async def scenario() -> Any:
        async with make_client(handler, "AWC") as client:
            return await AWCAdapter(client).fetch(ORIGIN, DESTINATION, WINDOW)

    result = run(scenario())
    assert result.status.status == "DEGRADED"
    assert result.status.error == "HTTPError(status=500)"
    assert result.status.http_status == 500
    assert len(result.payloads) == 2
    assert awc_metar[0]["icaoId"] == "KSFO"


def test_awc_malformed_json_is_degraded(awc_taf: list[dict[str, Any]]) -> None:
    """Malformed METAR JSON is captured as a partial failure."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/data/metar":
            return httpx.Response(200, text="<html>blocked</html>", request=request)
        return httpx.Response(200, json=awc_taf, request=request)

    async def scenario() -> Any:
        async with make_client(handler, "AWC") as client:
            return await AWCAdapter(client).fetch(ORIGIN, DESTINATION, WINDOW)

    result = run(scenario())
    assert result.status.status == "DEGRADED"
    assert result.status.error == "MalformedJSON(status=200)"
    assert len(result.payloads) == 2


def test_retry_on_5xx_then_success(
    awc_metar: list[dict[str, Any]], awc_taf: list[dict[str, Any]]
) -> None:
    """At most two retries on 5xx, then the call succeeds."""
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/data/taf":
            return httpx.Response(200, json=awc_taf, request=request)
        attempts["count"] += 1
        if attempts["count"] < 3:
            return httpx.Response(503, request=request)
        return httpx.Response(200, json=awc_metar, request=request)

    async def scenario() -> Any:
        async with make_client(handler, "AWC", max_retries=2) as client:
            return await AWCAdapter(client).fetch(ORIGIN, DESTINATION, WINDOW)

    result = run(scenario())
    assert result.status.status == "OK"
    assert attempts["count"] == 3


def test_retry_limit_on_429(nws_points: dict[str, Any]) -> None:
    """429 retries are bounded and exhaustedErrors are redacted."""
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(429, request=request)

    async def scenario() -> Any:
        async with make_client(handler, "NWS", max_retries=2) as client:
            return await NWSAdapter(client).fetch(ORIGIN, DESTINATION, WINDOW)

    result = run(scenario())
    assert result.status.status == "FAILED"
    assert result.status.error == "HTTPError(status=429)"
    assert attempts["count"] == 1 + 2
    assert nws_points["properties"]["gridId"] == "MTR"


def test_awc_retrospective_anchors_metar_window_and_skips_taf() -> None:
    """A retrospective run requests the assessed day only and never calls TAF."""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=[], request=request)

    window = {
        "start": datetime(2026, 11, 14, 4, 0, tzinfo=timezone.utc),
        "end": datetime(2026, 11, 15, 4, 0, tzinfo=timezone.utc),
    }

    async def scenario() -> Any:
        async with make_client(handler, "AWC") as client:
            return await AWCAdapter(client, retrospective=True).fetch(
                ORIGIN, DESTINATION, window
            )

    result = run(scenario())
    assert result.status.status == "OK"
    assert len(calls) == 1
    assert calls[0].url.path == "/api/data/metar"
    assert calls[0].url.params["date"] == "2026-11-15T04:00:00Z"
    assert calls[0].url.params["hours"] == "25"
    assert calls[0].url.params["ids"] == "KJFK,KSFO"
    assert result.payloads == []
    assert "TAF has no historical archive" in result.status.note


def test_upstream_redirect_is_a_distinct_visible_failure() -> None:
    """A drifted 3xx endpoint surfaces RedirectDisallowed, not MalformedJSON."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302,
            headers={"location": "https://api.weather.gov/elsewhere"},
            request=request,
        )

    async def scenario() -> Any:
        async with make_client(handler, "NWS", max_retries=0) as client:
            return await NWSAdapter(client).fetch(ORIGIN, DESTINATION, WINDOW)

    result = run(scenario())
    assert result.status.status == "FAILED"
    assert result.status.error == "RedirectDisallowed(302)"
    assert result.status.http_status == 302
    assert result.payloads == []
