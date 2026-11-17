"""Service orchestration tests: forward vs retrospective provider routing.

Providers and the HTTP client are replaced with in-memory fakes so no network
call is made. The deterministic decision table itself is covered in
test_risk.py; this module only asserts routing, mode marking and honesty fields.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import pytest

import app.service as service_module
from app.cities import CityRegistry
from app.http_client import HTTPClient
from app.models import AssessRequest
from app.providers.base import ProviderResult, build_status
from app.service import AssessmentService

ORIGIN = CityRegistry().resolve("JFK")
DESTINATION = CityRegistry().resolve("SFO")


class _Seen:
    """Shared recorder for fake adapter construction."""

    open_meteo_retrospective: bool | None = None
    awc_retrospective: bool | None = None
    nws_constructed = False


class _FakeOpenMeteo:
    name = "OPEN_METEO"

    def __init__(self, http: HTTPClient, retrospective: bool = False) -> None:
        _Seen.open_meteo_retrospective = retrospective

    async def fetch(
        self, origin: Any, destination: Any, window: dict[str, Any]
    ) -> ProviderResult:
        return ProviderResult([], build_status(self.name, "OK"))


class _FakeAWC:
    name = "AWC"

    def __init__(self, http: HTTPClient, retrospective: bool = False) -> None:
        _Seen.awc_retrospective = retrospective

    async def fetch(
        self, origin: Any, destination: Any, window: dict[str, Any]
    ) -> ProviderResult:
        return ProviderResult([], build_status(self.name, "OK"))


class _FakeNWS:
    name = "NWS"

    def __init__(self, http: HTTPClient) -> None:
        _Seen.nws_constructed = True

    async def fetch(
        self, origin: Any, destination: Any, window: dict[str, Any]
    ) -> ProviderResult:
        return ProviderResult([], build_status(self.name, "OK"))


class _FakeHTTPClient:
    """Stand-in for HTTPClient; supports async context management only."""

    def __init__(self, request_id: str | None = None, **kwargs: Any) -> None:
        pass

    async def __aenter__(self) -> "_FakeHTTPClient":
        return self

    async def __aexit__(self, *args: Any) -> bool:
        return False


@pytest.fixture()
def wired(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace providers and the HTTP client with in-memory fakes."""
    _Seen.open_meteo_retrospective = None
    _Seen.awc_retrospective = None
    _Seen.nws_constructed = False
    monkeypatch.setattr(service_module, "OpenMeteoAdapter", _FakeOpenMeteo)
    monkeypatch.setattr(service_module, "AWCAdapter", _FakeAWC)
    monkeypatch.setattr(service_module, "NWSAdapter", _FakeNWS)
    monkeypatch.setattr(service_module, "HTTPClient", _FakeHTTPClient)


def _jfk_today() -> Any:
    """Return JFK's local calendar date right now."""
    return datetime.now(timezone.utc).astimezone(ZoneInfo(ORIGIN.timezone)).date()


def _assess(date_iso: str) -> Any:
    request = AssessRequest(origin="JFK", destination="SFO", date=date_iso)
    service = AssessmentService()
    return asyncio.run(service.assess(request, "test-request-id"))


def test_retrospective_uses_historical_providers_and_marks_the_run(
    wired: None,
) -> None:
    """A past date routes to retrospective adapters and marks the assessment."""
    recent_past = (_jfk_today() - timedelta(days=2)).isoformat()

    assessment = _assess(recent_past)

    assert _Seen.open_meteo_retrospective is True
    assert _Seen.awc_retrospective is True
    assert _Seen.nws_constructed is False
    assert assessment.assessment_mode == "retrospective"
    assert assessment.route["basis"] == "airport-level retrospective"
    assert assessment.route["weather_provider"] == "OPEN_METEO"
    assert "Retrospective run" in assessment.coverage_note
    assert any("Retrospective assessment" in line for line in assessment.assumptions)
    assert [status.provider for status in assessment.provider_status] == [
        "OPEN_METEO",
        "AWC",
    ]


def test_forward_uses_country_provider_and_forward_mode(wired: None) -> None:
    """A future date keeps the US NWS + AWC pair and the forward marking."""
    tomorrow = (_jfk_today() + timedelta(days=1)).isoformat()

    assessment = _assess(tomorrow)

    assert _Seen.nws_constructed is True
    assert not _Seen.open_meteo_retrospective
    assert not _Seen.awc_retrospective
    assert assessment.assessment_mode == "forward"
    assert assessment.route["basis"] == "airport-level"
    assert assessment.route["weather_provider"] == "NWS"
    assert [status.provider for status in assessment.provider_status] == ["NWS", "AWC"]
