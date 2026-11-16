"""Shared fixtures and builders for deterministic, offline unit tests."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Coroutine

import pytest

from app.models import Evidence, ProviderStatus

FIXTURES_DIR = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 11, 16, 7, 0, tzinfo=timezone.utc)


def load_fixture(name: str) -> Any:
    """Load one recorded provider payload fixture."""
    with (FIXTURES_DIR / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def run(coroutine: Coroutine[Any, Any, Any]) -> Any:
    """Run a coroutine in a synchronous pytest test without extra plugins."""
    return asyncio.run(coroutine)


def make_window(
    start: datetime | None = None, end: datetime | None = None
) -> dict[str, datetime]:
    """Build a UTC travel window (defaults to the day after NOW)."""
    window_start = start or NOW + timedelta(hours=1)
    window_end = end or window_start + timedelta(days=1)
    return {"start": window_start, "end": window_end}


def make_evidence(
    index: int,
    provider: str,
    severity: str,
    reliability: str = "HIGH",
    geography: str = "EXACT",
    overlap: str = "FULL",
    freshness: str = "FRESH",
) -> Evidence:
    """Build one Evidence with explicit decision-table attributes."""
    signal_type = (
        "NWS_ALERT"
        if provider == "NWS"
        else "AWC_METAR" if provider == "AWC" else "AWC_TAF"
    )
    return Evidence(
        id=f"evidence-{index:02d}-abcdef0123456789"[:16],
        provider=provider,  # type: ignore[arg-type]
        signal_type=signal_type,  # type: ignore[arg-type]
        signal=f"signal-{index:02d}",
        severity=severity,  # type: ignore[arg-type]
        reliability=reliability,  # type: ignore[arg-type]
        geography=geography,  # type: ignore[arg-type]
        temporal_overlap=overlap,  # type: ignore[arg-type]
        freshness=freshness,  # type: ignore[arg-type]
        observed_at=NOW,
        valid_from=NOW,
        valid_to=NOW + timedelta(hours=12),
        relevance_reason="Synthetic decision-table test evidence.",
        source_url="https://example.invalid/test",
        raw_excerpt="synthetic",
    )


def make_status(
    provider: str, status: str = "OK", *, error: str | None = None, note: str = ""
) -> ProviderStatus:
    """Build one ProviderStatus for risk-engine tests."""
    return ProviderStatus(
        provider=provider,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        http_status=200 if status == "OK" else 500,
        latency_ms=42,
        fetched_at=NOW,
        evidence_count=0,
        error=error,
        note=note,
        authoritative_url=(
            "https://www.weather.gov/documentation/services-web-api"
            if provider == "NWS"
            else "https://aviationweather.gov/data/api/"
        ),
    )


@pytest.fixture
def nws_points() -> Any:
    """Recorded NWS points response for SFO."""
    return load_fixture("nws_points.json")


@pytest.fixture
def nws_alerts() -> Any:
    """Recorded NWS active-alerts response with one California alert."""
    return load_fixture("nws_alerts.json")


@pytest.fixture
def nws_forecast() -> Any:
    """Recorded NWS gridpoint forecast response."""
    return load_fixture("nws_forecast.json")


@pytest.fixture
def awc_metar() -> Any:
    """Recorded AWC METAR array."""
    return load_fixture("awc_metar.json")


@pytest.fixture
def awc_taf() -> Any:
    """Recorded AWC TAF array."""
    return load_fixture("awc_taf.json")
