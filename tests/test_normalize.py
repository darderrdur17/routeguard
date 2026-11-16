"""Normalization tests built from recorded provider payload shapes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from app.normalize import Normalizer, parse_instant, temporal_overlap

ALERTS_URL = "https://api.weather.gov/alerts/active?point=37.6213,-122.3790"
FORECAST_URL = "https://api.weather.gov/gridpoints/MTR/85,98/forecast"
METAR_URL = (
    "https://aviationweather.gov/api/data/metar?ids=KSFO,KJFK&format=json&hours=2"
)
TAF_URL = "https://aviationweather.gov/api/data/taf?ids=KSFO,KJFK&format=json"

WINDOW = {
    "start": datetime(2026, 11, 16, 0, 0, tzinfo=timezone.utc),
    "end": datetime(2026, 11, 17, 0, 0, tzinfo=timezone.utc),
}
NOW = datetime(2026, 11, 16, 7, 0, tzinfo=timezone.utc)


def alert_envelopes(nws_alerts: dict[str, Any]) -> list[dict[str, Any]]:
    """Wrap recorded alert features in normalizer envelopes."""
    return [
        {
            "_provider": "NWS",
            "_signal": "NWS_ALERT",
            "_source_url": ALERTS_URL,
            "_role": "origin",
            "record": feature,
        }
        for feature in nws_alerts["features"]
    ]


def forecast_envelopes(nws_forecast: dict[str, Any]) -> list[dict[str, Any]]:
    """Wrap recorded forecast periods in normalizer envelopes."""
    properties = nws_forecast["properties"]
    return [
        {
            "_provider": "NWS",
            "_signal": "NWS_FORECAST_PERIOD",
            "_source_url": FORECAST_URL,
            "_role": "origin",
            "_generated_at": properties["generatedAt"],
            "record": period,
        }
        for period in properties["periods"]
    ]


def metar_envelopes(awc_metar: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Wrap recorded METAR records in normalizer envelopes."""
    return [
        {
            "_provider": "AWC",
            "_signal": "AWC_METAR",
            "_source_url": METAR_URL,
            "_role": "origin" if record["icaoId"] == "KSFO" else "destination",
            "record": record,
        }
        for record in awc_metar
    ]


def taf_envelopes(awc_taf: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Wrap recorded TAF records in normalizer envelopes."""
    return [
        {
            "_provider": "AWC",
            "_signal": "AWC_TAF",
            "_source_url": TAF_URL,
            "_role": "origin" if record["icaoId"] == "KSFO" else "destination",
            "record": record,
        }
        for record in awc_taf
    ]


def test_nws_alert_normalization(nws_alerts: dict[str, Any]) -> None:
    """A point alert is EXACT, HIGH reliability and fresh."""
    result = Normalizer(now=NOW).normalize(alert_envelopes(nws_alerts), WINDOW)
    assert len(result.evidence) == 1
    item = result.evidence[0]
    assert item.provider == "NWS"
    assert item.signal_type == "NWS_ALERT"
    assert item.signal == "High Surf Advisory"
    assert item.severity == "MINOR"
    assert item.reliability == "HIGH"
    assert item.geography == "EXACT"
    assert item.temporal_overlap == "PARTIAL"
    assert item.freshness == "FRESH"
    assert item.source_url == ALERTS_URL
    assert item.observed_at == parse_instant("2026-11-16T06:10:00+00:00")
    assert "origin airport" in item.relevance_reason


def test_nws_forecast_severity_rules(nws_forecast: dict[str, Any]) -> None:
    """Wind >=20 and pop>=80 with rain emit evidence; benign periods do not."""
    result = Normalizer(now=NOW).normalize(forecast_envelopes(nws_forecast), WINDOW)
    assert len(result.evidence) == 2
    assert all(item.signal_type == "NWS_FORECAST_PERIOD" for item in result.evidence)
    assert all(item.severity == "MODERATE" for item in result.evidence)
    assert all(item.reliability == "MEDIUM" for item in result.evidence)
    assert {item.signal for item in result.evidence} == {
        "Chance Light Rain",
        "Rain Likely",
    }
    assert result.evidence[0].source_url == FORECAST_URL
    assert result.evidence[0].observed_at == parse_instant(
        "2026-11-16T05:27:03+00:00"
    )


def test_metar_severity_and_one_hour_validity(awc_metar: list[dict[str, Any]]) -> None:
    """IFR/2SM is MODERATE, VFR/-RA is MINOR, observations last one hour."""
    result = Normalizer(now=NOW).normalize(metar_envelopes(awc_metar), WINDOW)
    assert len(result.evidence) == 2
    by_signal = {item.signal: item for item in result.evidence}
    ifr = by_signal["IFR:TSRA"]
    vfr = by_signal["VFR:-RA"]
    assert ifr.severity == "MODERATE"
    assert vfr.severity == "MINOR"
    assert ifr.reliability == "HIGH"
    assert ifr.freshness == "FRESH"
    assert ifr.geography == "EXACT"
    assert ifr.valid_from == parse_instant("2026-11-16T06:00:00.000Z")
    assert ifr.valid_to == ifr.valid_from + timedelta(hours=1)
    assert ifr.source_url == METAR_URL


def test_taf_severity_signal_and_visibility_string(awc_taf: list[dict[str, Any]]) -> None:
    """TAF strings are parsed; 6+ visibility emits no evidence."""
    start = parse_instant(awc_taf[0]["fcsts"][0]["timeFrom"])
    assert start is not None
    window = {"start": start, "end": start + timedelta(days=1)}
    result = Normalizer(now=NOW).normalize(taf_envelopes(awc_taf), window)
    assert len(result.evidence) == 2
    signals = {item.signal for item in result.evidence}
    assert signals == {"TSRA", "RA"}
    severe_or_moderate = [item for item in result.evidence if item.signal == "TSRA"][0]
    assert severe_or_moderate.severity == "MODERATE"
    assert severe_or_moderate.reliability == "MEDIUM"
    assert severe_or_moderate.observed_at == parse_instant(
        "2026-11-16T05:43:00.000Z"
    )
    assert "P6SM" not in signals


def test_out_of_window_evidence_is_shown_but_marked_none(
    nws_alerts: dict[str, Any],
) -> None:
    """Temporal NONE evidence remains visible but cannot classify."""
    later = {
        "start": WINDOW["start"] + timedelta(days=5),
        "end": WINDOW["end"] + timedelta(days=5),
    }
    result = Normalizer(now=NOW).normalize(alert_envelopes(nws_alerts), later)
    assert len(result.evidence) == 1
    assert result.evidence[0].temporal_overlap == "NONE"


def test_stale_evidence_is_flagged(nws_alerts: dict[str, Any]) -> None:
    """An alert older than 24 hours is STALE, not silently dropped."""
    old_now = datetime(2026, 11, 17, 8, 0, tzinfo=timezone.utc)
    result = Normalizer(now=old_now).normalize(alert_envelopes(nws_alerts), WINDOW)
    assert len(result.evidence) == 1
    assert result.evidence[0].freshness == "STALE"


def test_evidence_ids_and_excerpts_are_deterministic(
    nws_alerts: dict[str, Any],
) -> None:
    """IDs are 16 lowercase hex chars and raw excerpts are bounded."""
    first = Normalizer(now=NOW).normalize(alert_envelopes(nws_alerts), WINDOW)
    second = Normalizer(now=NOW).normalize(alert_envelopes(nws_alerts), WINDOW)
    assert first.evidence[0].id == second.evidence[0].id
    assert len(first.evidence[0].id) == 16
    assert all(char in "0123456789abcdef" for char in first.evidence[0].id)
    assert len(first.evidence[0].raw_excerpt) <= 240
    assert first.evidence[0].raw_excerpt.startswith('{"geometry"')
    assert first.evidence[0].signal == "High Surf Advisory"


def test_malformed_record_is_flagged_not_dropped_silently() -> None:
    """Invalid alert properties produce a note and a DEGRADED provider."""
    envelope = {
        "_provider": "NWS",
        "_signal": "NWS_ALERT",
        "_source_url": ALERTS_URL,
        "_role": "origin",
        "record": {"properties": None},
    }
    result = Normalizer(now=NOW).normalize([envelope], WINDOW)
    assert result.evidence == []
    assert "NWS" in result.degraded
    assert any("Malformed" in note for note in result.notes["NWS"])


def test_temporal_overlap_helpers() -> None:
    """FULL/PARTIAL/NONE/UNKNOWN overlap classification is explicit."""
    start = WINDOW["start"]
    end = WINDOW["end"]
    assert temporal_overlap(start - timedelta(hours=1), end + timedelta(hours=1), WINDOW) == "FULL"
    assert temporal_overlap(start, start + timedelta(hours=2), WINDOW) == "PARTIAL"
    assert (
        temporal_overlap(end + timedelta(hours=1), end + timedelta(hours=2), WINDOW)
        == "NONE"
    )
    assert temporal_overlap(None, end, WINDOW) == "UNKNOWN"


@pytest.mark.parametrize("value", ["2026-11-16T06:00:00Z", 1794808800, None, "bad"])
def test_parse_instant_defensive(value: Any) -> None:
    """Timestamp parsing handles ISO, epoch, missing and malformed values."""
    parsed = parse_instant(value)
    if value in (None, "bad"):
        assert parsed is None
    else:
        assert parsed is not None
        assert parsed.tzinfo == timezone.utc
