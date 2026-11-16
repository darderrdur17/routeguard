"""Global-coverage tests: no-key weather adapter and provider selection."""

from __future__ import annotations

from datetime import datetime, timezone

from app.cities import CityRegistry
from app.models import Evidence
from app.normalize import (
    Normalizer,
    open_meteo_current_severity,
    open_meteo_hourly_severity,
)
from app.service import weather_provider_name

WINDOW = {
    "start": datetime(2026, 11, 16, 0, 0, tzinfo=timezone.utc),
    "end": datetime(2026, 11, 17, 0, 0, tzinfo=timezone.utc),
}
NOW = datetime(2026, 11, 16, 8, 0, tzinfo=timezone.utc)


def envelope(signal: str, record: dict) -> dict:
    """Build one provenance-tagged envelope as the adapter emits."""
    return {
        "_provider": "OPEN_METEO",
        "_signal": signal,
        "_source_url": "https://api.open-meteo.com/v1/forecast?latitude=1.36&longitude=103.99",
        "_role": "origin",
        "record": record,
    }


def test_wmo_severity_rules_are_deterministic() -> None:
    """WMO codes map to a bounded severity ladder without probabilities."""
    assert open_meteo_current_severity({"weather_code": 95}) == "SEVERE"
    assert open_meteo_current_severity({"weather_code": 65}) == "MINOR"
    assert open_meteo_current_severity({"weather_code": 0}) == "UNKNOWN"
    assert open_meteo_current_severity({"weather_code": 0, "wind_speed_10m": 65}) == "MODERATE"
    assert open_meteo_hourly_severity({"precipitation_probability": 85}) == "MODERATE"
    assert open_meteo_hourly_severity({"precipitation_probability": 45}) == "MINOR"
    assert open_meteo_hourly_severity({"precipitation_probability": 10}) == "UNKNOWN"


def test_open_meteo_current_normalizes_to_trustworthy_evidence() -> None:
    """A severe current condition becomes an explainable, fresh, exact evidence item."""
    payload = envelope(
        "OPEN_METEO_CURRENT",
        {
            "time": "2026-11-16T07:30Z",
            "weather_code": 95,
            "wind_speed_10m": 12,
            "temperature_2m": 29.4,
        },
    )
    result = Normalizer(now=NOW, locations={"origin": ("Singapore (SIN)", 1.3644, 103.9915)}).normalize(
        [payload], WINDOW
    )
    assert len(result.evidence) == 1
    item: Evidence = result.evidence[0]
    assert item.provider == "OPEN_METEO"
    assert item.severity == "SEVERE"
    assert item.reliability == "HIGH"
    assert item.freshness == "FRESH"
    assert item.geography == "EXACT"
    assert item.temporal_overlap == "PARTIAL"
    assert item.location_label == "Singapore (SIN)"
    assert item.latitude == 1.3644
    assert "WMO 95" in item.signal


def test_open_meteo_forecast_keeps_observed_time_absent() -> None:
    """Forecast evidence is not misrepresented as an observation."""
    payload = envelope(
        "OPEN_METEO_HOURLY",
        {"time": "2026-11-16T09:00Z", "precipitation_probability": 90},
    )
    result = Normalizer(now=NOW).normalize([payload], WINDOW)
    assert len(result.evidence) == 1
    item = result.evidence[0]
    assert item.severity == "MODERATE"
    assert item.observed_at is None
    assert item.valid_from is not None
    assert item.valid_to is not None


def test_weather_provider_selected_by_country() -> None:
    """NWS stays US-only; every other country uses the no-key global provider."""
    registry = CityRegistry()
    assert weather_provider_name(registry.resolve("JFK")) == "NWS"
    assert weather_provider_name(registry.resolve("SIN")) == "OPEN_METEO"
    assert weather_provider_name(registry.resolve("LHR")) == "OPEN_METEO"
    assert weather_provider_name(registry.resolve("Toronto (YYZ)")) == "OPEN_METEO"
