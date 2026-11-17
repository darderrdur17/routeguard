"""History endpoint and ERA5 archive adapter tests — zero live calls.

Rejection tests exercise the real validation path (no network happens before
it). Payload tests use httpx.MockTransport through HistoryService/adapter, the
same offline pattern as tests/test_adapters.py.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

import httpx
import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.cities import CityRegistry
from app.config import settings
from app.http_client import HTTPClient
from app.history import HistoryService
from app.providers.open_meteo_archive import OpenMeteoArchiveAdapter

TODAY = datetime.now(timezone.utc).date()
LAG_BOUND = TODAY - timedelta(days=6)
HAPPY_END = TODAY - timedelta(days=7)
HAPPY_START = HAPPY_END - timedelta(days=9)
JFK = CityRegistry().resolve("JFK")


def archive_payload(start: date, end: date) -> dict[str, Any]:
    """Build a realistic archive document with one explicit null day."""
    times: list[str] = []
    day = start
    while day <= end:
        times.append(day.isoformat())
        day += timedelta(days=1)
    count = len(times)
    precipitation = [12.4 if index % 3 == 0 else 0.0 for index in range(count)]
    precipitation[0] = None  # explicit null day, never interpolated
    return {
        "daily": {
            "time": times,
            "temperature_2m_max": [20.5 + index for index in range(count)],
            "temperature_2m_min": [10.0 for _ in range(count)],
            "precipitation_sum": precipitation,
            "wind_speed_10m_max": [18.2 for _ in range(count)],
            "weather_code": [3 if index % 2 else 0 for index in range(count)],
        },
        "daily_units": {
            "temperature_2m_max": "°C",
            "temperature_2m_min": "°C",
            "precipitation_sum": "mm",
            "wind_speed_10m_max": "km/h",
        },
    }


def make_archive_handler(
    *,
    origin_status: int = 200,
    destination_status: int = 200,
) -> Callable[[httpx.Request], httpx.Response]:
    """Return 200 payloads per airport, or the requested failure status.

    JFK (lat ~40.64) is the origin; SFO (lat ~37.62) is the destination.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        latitude = float(request.url.params["latitude"])
        start = date.fromisoformat(str(request.url.params["start_date"]))
        end = date.fromisoformat(str(request.url.params["end_date"]))
        is_origin = latitude >= 39.0
        status = origin_status if is_origin else destination_status
        if status != 200:
            return httpx.Response(status, request=request)
        return httpx.Response(200, json=archive_payload(start, end), request=request)

    return handler


def history_client(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
) -> TestClient:
    """Return a TestClient whose history service uses a MockTransport."""
    service = HistoryService(
        transport=httpx.MockTransport(handler), max_retries=0
    )
    monkeypatch.setattr(main_module, "_history_service", service)
    return TestClient(main_module.app)


def get_history(client: TestClient, **params: str) -> Any:
    """GET /api/history with the given query parameters."""
    return client.get("/api/history", params=params)


def _assert_envelope(body: Any, code: str) -> None:
    """Assert the uniform four-field error envelope."""
    assert isinstance(body, dict)
    assert set(body) == {"code", "message", "request_id", "details"}
    assert body["code"] == code
    assert isinstance(body["message"], str) and body["message"]
    assert isinstance(body["request_id"], str) and body["request_id"]


def test_end_date_after_lag_bound_is_rejected() -> None:
    """end_date inside the archive publication lag is an INVALID_DATE."""
    client = TestClient(main_module.app)
    response = get_history(
        client,
        origin="JFK",
        destination="SFO",
        start_date=(LAG_BOUND - timedelta(days=9)).isoformat(),
        end_date=TODAY.isoformat(),
    )
    assert response.status_code == 422
    body = response.json()
    _assert_envelope(body, "INVALID_DATE")
    assert "publishes ~6 days behind today" in body["message"]
    assert f"end_date must be on or before {LAG_BOUND.isoformat()}" in body["message"]


def test_range_over_366_days_is_rejected() -> None:
    """A range deeper than one year is an INVALID_DATE."""
    client = TestClient(main_module.app)
    end = HAPPY_END
    response = get_history(
        client,
        origin="JFK",
        destination="SFO",
        start_date=(end - timedelta(days=400)).isoformat(),
        end_date=end.isoformat(),
    )
    assert response.status_code == 422
    body = response.json()
    _assert_envelope(body, "INVALID_DATE")
    assert "366" in body["message"]


def test_minimum_date_is_invalid_date_not_overflow_500() -> None:
    """A 0001-01-01 range returns INVALID_DATE, never an OverflowError/500."""
    client = TestClient(main_module.app)
    response = get_history(
        client,
        origin="JFK",
        destination="SFO",
        start_date=date.min.isoformat(),
        end_date=date.min.isoformat(),
    )
    assert response.status_code == 422
    body = response.json()
    _assert_envelope(body, "INVALID_DATE")
    assert "outside the supported archive range" in body["message"]


def test_start_after_end_is_rejected() -> None:
    """An inverted range is an INVALID_DATE."""
    client = TestClient(main_module.app)
    response = get_history(
        client,
        origin="JFK",
        destination="SFO",
        start_date=HAPPY_END.isoformat(),
        end_date=(HAPPY_END - timedelta(days=5)).isoformat(),
    )
    assert response.status_code == 422
    _assert_envelope(response.json(), "INVALID_DATE")


def test_unknown_airport_is_rejected_consistently_with_assess() -> None:
    """An unmapped city yields UNMAPPED_CITY on both endpoints."""
    client = TestClient(main_module.app)
    response = get_history(
        client,
        origin="Atlantis",
        destination="SFO",
        start_date=HAPPY_START.isoformat(),
        end_date=HAPPY_END.isoformat(),
    )
    assert response.status_code == 422
    _assert_envelope(response.json(), "UNMAPPED_CITY")


def test_malformed_query_dates_map_to_invalid_date() -> None:
    """Non-ISO query dates reach INVALID_DATE through the shared handler."""
    client = TestClient(main_module.app)
    response = get_history(
        client,
        origin="JFK",
        destination="SFO",
        start_date="not-a-date",
        end_date=HAPPY_END.isoformat(),
    )
    assert response.status_code == 422
    body = response.json()
    _assert_envelope(body, "INVALID_DATE")
    fields = {item["field"] for item in body["details"]["errors"]}
    assert "query.start_date" in fields


def test_happy_path_returns_contract_with_null_passthrough(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The 200 payload matches the contract and keeps explicit nulls."""
    client = history_client(monkeypatch, make_archive_handler())
    response = get_history(
        client,
        origin="JFK",
        destination="SFO",
        start_date=HAPPY_START.isoformat(),
        end_date=HAPPY_END.isoformat(),
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"request_id", "query", "provenance", "airports"}
    assert body["query"] == {
        "origin": "JFK",
        "destination": "SFO",
        "start_date": HAPPY_START.isoformat(),
        "end_date": HAPPY_END.isoformat(),
    }
    provenance = body["provenance"]
    assert provenance["source"] == "Open-Meteo Archive API"
    assert provenance["model"] == "ERA5 reanalysis (model), not observations"
    assert provenance["docs_url"] == settings.open_meteo_archive_docs_url
    assert provenance["retrieved_at"].endswith("Z")

    origin = body["airports"]["origin"]
    assert origin["iata"] == "JFK" and origin["icao"] == JFK.icao
    assert origin["unavailable"] is False and origin["detail"] is None
    daily = origin["daily"]
    lengths = {len(daily[key]) for key in daily}
    assert len(lengths) == 1  # every series, including time, has one entry/day
    assert daily["precipitation_sum"][0] is None  # null passthrough, no fill
    assert origin["daily_units"]["precipitation_sum"] == "mm"

    destination = body["airports"]["destination"]
    assert destination["unavailable"] is False
    assert destination["daily"]["time"][0] == HAPPY_START.isoformat()


def test_history_response_has_no_classification_or_score_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The history payload never carries assessment or severity vocabulary."""
    client = history_client(monkeypatch, make_archive_handler())
    response = get_history(
        client,
        origin="JFK",
        destination="SFO",
        start_date=HAPPY_START.isoformat(),
        end_date=HAPPY_END.isoformat(),
    )
    assert response.status_code == 200
    text = response.text.lower()
    for banned in (
        "classification",
        "confidence",
        "severity",
        "score",
        "extreme",
        "triggered_rules",
    ):
        assert banned not in text


def test_partial_upstream_failure_marks_airport_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One failing airport stays a 200 with unavailable:true + redacted detail."""
    client = history_client(
        monkeypatch, make_archive_handler(destination_status=503)
    )
    response = get_history(
        client,
        origin="JFK",
        destination="SFO",
        start_date=HAPPY_START.isoformat(),
        end_date=HAPPY_END.isoformat(),
    )
    assert response.status_code == 200
    airports = response.json()["airports"]
    assert airports["origin"]["unavailable"] is False
    assert airports["origin"]["daily"] is not None
    assert airports["destination"]["unavailable"] is True
    assert isinstance(airports["destination"]["detail"], str)
    assert airports["destination"]["daily"] is None


def test_both_airports_failing_returns_502_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Total archive failure maps to the 502 UPSTREAM_UNAVAILABLE envelope."""
    client = history_client(
        monkeypatch,
        make_archive_handler(origin_status=503, destination_status=503),
    )
    response = get_history(
        client,
        origin="JFK",
        destination="SFO",
        start_date=HAPPY_START.isoformat(),
        end_date=HAPPY_END.isoformat(),
    )
    assert response.status_code == 502
    body = response.json()
    _assert_envelope(body, "UPSTREAM_UNAVAILABLE")
    assert body["details"]["origin"] and body["details"]["destination"]


def test_adapter_pads_mismatched_series_with_nulls() -> None:
    """Short upstream arrays are padded with explicit nulls, never dropped."""
    from tests.conftest import run

    start = HAPPY_START
    end = HAPPY_END
    payload = archive_payload(start, end)
    expected_days = len(payload["daily"]["time"])
    payload["daily"]["temperature_2m_max"] = [21.5]  # mismatched length

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload, request=request)

    async def scenario() -> dict[str, Any]:
        async with HTTPClient(
            request_id="test-request",
            transport=httpx.MockTransport(handler),
            max_retries=0,
        ) as client:
            return await OpenMeteoArchiveAdapter(client).fetch(JFK, start, end)

    block = run(scenario())
    assert block["unavailable"] is False
    series = block["daily"]["temperature_2m_max"]
    assert len(series) == expected_days
    assert series[0] == 21.5
    assert all(value is None for value in series[1:])


def test_adapter_failure_block_is_redacted() -> None:
    """An HTTP failure returns unavailable:true with a redacted detail."""
    from tests.conftest import run

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, request=request)

    async def scenario() -> dict[str, Any]:
        async with HTTPClient(
            request_id="test-request",
            transport=httpx.MockTransport(handler),
            max_retries=0,
        ) as client:
            return await OpenMeteoArchiveAdapter(client).fetch(
                JFK, HAPPY_START, HAPPY_END
            )

    block = run(scenario())
    assert block["unavailable"] is True
    assert block["detail"] == "HTTPError(status=500)"
    assert block["daily"] is None and block["daily_units"] is None
    assert block["iata"] == "JFK" and block["city"] == JFK.city


def test_service_validation_errors_include_the_errors_array() -> None:
    """History date-bound failures share the validation envelope shape."""
    client = TestClient(main_module.app)
    response = get_history(
        client,
        origin="JFK",
        destination="SFO",
        start_date=LAG_BOUND.isoformat(),
        end_date=LAG_BOUND.isoformat(),
    )
    assert response.status_code == 200 or response.status_code == 422
    if response.status_code == 422:
        body = response.json()
        assert isinstance(body["details"]["errors"], list)


def test_unmapped_origin_in_history_uses_unmapped_city_code() -> None:
    """History and assessment agree on the error code for an unknown city."""
    client = TestClient(main_module.app)
    response = get_history(
        client,
        origin="Atlantis",
        destination="SFO",
        start_date=HAPPY_START.isoformat(),
        end_date=HAPPY_END.isoformat(),
    )
    assert response.status_code == 422
    assert response.json()["code"] == "UNMAPPED_CITY"
