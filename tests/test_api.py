"""HTTP-layer R00 validation tests: date bounds and error envelope shape.

The service is stubbed so these tests stay offline: they exercise request
validation and FastAPI's existing error handler, never live providers.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

import app.main as main_module

JFK_ZONE = ZoneInfo("America/New_York")


class _StubAssessment:
    """Minimal stand-in returned by the stubbed assessment service."""

    def model_dump(self, mode: str = "json") -> dict[str, Any]:
        """Return a small JSON-ready payload for the endpoint."""
        _ = mode
        return {
            "classification": "INDETERMINATE",
            "confidence": "LOW",
            "provider_status": [{"provider": "NWS"}, {"provider": "AWC"}],
        }


def _client(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, list[Any]]:
    """Return a TestClient whose assessment service never calls providers."""
    calls: list[Any] = []

    async def fake_assess(payload: Any, request_id: str) -> _StubAssessment:
        calls.append((payload, request_id))
        return _StubAssessment()

    monkeypatch.setattr(main_module._service, "assess", fake_assess)
    return TestClient(main_module.app), calls


def _local_today() -> date:
    """Return JFK's local calendar date at test time."""
    return datetime.now(JFK_ZONE).date()


def _assert_error_envelope(body: Any, code: str, field: str) -> None:
    """Assert the four-field error envelope emitted by main.py."""
    assert isinstance(body, dict)
    assert set(body) == {"code", "message", "request_id", "details"}
    assert body["code"] == code
    assert isinstance(body["message"], str) and body["message"]
    assert isinstance(body["request_id"], str) and body["request_id"]
    assert isinstance(body["details"], dict)
    errors = body["details"]["errors"]
    assert errors[0]["field"] == field
    assert isinstance(errors[0]["message"], str) and errors[0]["message"]


def test_health_is_live(monkeypatch: pytest.MonkeyPatch) -> None:
    """The liveness endpoint stays independent of validation changes."""
    client, _calls = _client(monkeypatch)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_past_date_is_rejected_with_invalid_date_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A date before JFK's local today never reaches the provider layer."""
    client, calls = _client(monkeypatch)
    yesterday = (_local_today() - timedelta(days=1)).isoformat()
    response = client.post(
        "/api/assess",
        json={"origin": "JFK", "destination": "SFO", "date": yesterday},
    )
    assert response.status_code == 422
    body = response.json()
    _assert_error_envelope(body, "INVALID_DATE", "body.date")
    assert "local today" in body["details"]["errors"][0]["message"]
    # The top-level message is human-readable and explains why past dates
    # cannot be assessed instead of a generic validation banner.
    assert "local today" in body["message"]
    assert "past dates cannot be evaluated" in body["message"]
    assert calls == []


@pytest.mark.parametrize("offset_days", [0, 1, 30])
def test_today_tomorrow_and_far_future_are_accepted(
    monkeypatch: pytest.MonkeyPatch, offset_days: int
) -> None:
    """Today, tomorrow and far-future dates pass R00; no hard horizon is imposed."""
    client, calls = _client(monkeypatch)
    travel_date = (_local_today() + timedelta(days=offset_days)).isoformat()
    response = client.post(
        "/api/assess",
        json={"origin": "JFK", "destination": "SFO", "date": travel_date},
    )
    assert response.status_code == 200
    assert response.json()["classification"] == "INDETERMINATE"
    assert len(calls) == 1
    assert calls[0][0].date.isoformat() == travel_date


def test_malformed_date_is_rejected_with_invalid_date_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-ISO date keeps the existing Pydantic-to-422 mapping."""
    client, calls = _client(monkeypatch)
    response = client.post(
        "/api/assess",
        json={"origin": "JFK", "destination": "SFO", "date": "not-a-date"},
    )
    assert response.status_code == 422
    _assert_error_envelope(response.json(), "INVALID_DATE", "body.date")
    assert calls == []


def _assert_structured_error(body: Any, code: str) -> None:
    """Assert the base error envelope for non-validation HTTP errors."""
    assert isinstance(body, dict)
    assert set(body) == {"code", "message", "request_id", "details"}
    assert body["code"] == code
    assert isinstance(body["message"], str) and body["message"]
    assert isinstance(body["request_id"], str) and body["request_id"]


def test_unknown_routes_and_methods_use_the_uniform_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """404 and 405 remain structured errors, not bare FastAPI detail bodies."""
    client, _calls = _client(monkeypatch)
    response = client.get("/definitely-not-a-route")
    assert response.status_code == 404
    _assert_structured_error(response.json(), "NOT_FOUND")
    response = client.get("/api/assess")
    assert response.status_code == 405
    _assert_structured_error(response.json(), "METHOD_NOT_ALLOWED")


def test_invalid_route_takes_precedence_over_invalid_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If both fields are bad, the error points at the airport input first."""
    client, _calls = _client(monkeypatch)
    response = client.post(
        "/api/assess",
        json={"origin": "", "destination": "San Francisco", "date": "2000-01-01"},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "INVALID_ROUTE"
    assert {item["field"] for item in body["details"]["errors"]} == {"body.origin", "body.date"}


def test_same_origin_and_destination_is_rejected() -> None:
    """An airport pair must contain two distinct curated airports."""
    from app.service import AssessmentService, RouteInputError

    service = AssessmentService()
    from app.models import AssessRequest

    request = AssessRequest(
        origin="New York", destination="New York", date=_local_today()
    )
    with pytest.raises(RouteInputError) as raised:
        import asyncio

        asyncio.run(service.assess(request, "same-airport-test"))
    assert raised.value.code == "INVALID_ROUTE"


def test_maximum_supported_date_does_not_overflow() -> None:
    """The travel window builder handles Python's maximum calendar date."""
    from datetime import date as date_type

    from app.cities import CityRegistry
    from app.service import AssessmentService

    airport = CityRegistry().resolve("JFK")
    window = AssessmentService._travel_window(airport, date_type.max)
    assert window["start"].year == date_type.max.year
    assert window["end"].year == date_type.max.year
    assert window["end"] > window["start"]


def test_date_validation_uses_origin_timezone() -> None:
    """The validator resolves the origin airport's zone before checking today."""
    from app.models import AssessRequest, _origin_local_today

    assert _origin_local_today("JFK") == datetime.now(JFK_ZONE).date()
    request = AssessRequest(origin="JFK", destination="SFO", date=_local_today())
    assert request.date == _local_today()
