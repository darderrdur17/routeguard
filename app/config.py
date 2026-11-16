"""Runtime settings for RouteGuard.

All outbound endpoints, identification, retry/freshness thresholds and the
authoritative external fallback links are defined here in one place. Values
follow the verified design in docs/01_architecture.md (sections 2, 7 and 11).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os


@dataclass(frozen=True)
class Settings:
    """Immutable bundle of prototype settings.

    Attributes:
        user_agent: Identifying User-Agent sent on 100% of outbound calls.
        timeout_s: Per-request httpx timeout in seconds.
        max_retries: Maximum retries on 429/5xx only (never on 4xx besides 429).
        backoff_base_s: Base jittered-backoff delay; tests may set this to 0.
        nws_points_url: Template with a single ``{point}`` placeholder.
        nws_alerts_url: Point-based active alerts endpoint.
        awc_metar_url: Aviation Weather Center METAR endpoint.
        awc_taf_url: Aviation Weather Center TAF endpoint.
        faa_nas_status_url: Authoritative human-facing NAS status dashboard.
        faa_airport_status_url: Authoritative human-facing airport status map.
        nws_docs_url: Official NWS API documentation (fallback link).
        awc_docs_url: Official AWC API documentation (fallback link).
        freshness_hours: Issue-age thresholds by signal type.
        forecast_horizon_days: NWS gridpoint forecast horizon disclosed to users.
        taf_horizon_hours: TAF validity horizon disclosed to users.
        site_url: Canonical public origin for SEO metadata; empty means derive from
            the incoming request (useful for local runs and preview deployments).
    """

    user_agent: str = (
        "RouteGuardPrototype/0.1 (contact: "
        + os.getenv("ROUTEGUARD_CONTACT_EMAIL", "derren@example.com")
        + ")"
    )
    timeout_s: float = 10.0
    max_retries: int = 2
    backoff_base_s: float = 0.25
    nws_points_url: str = "https://api.weather.gov/points/{point}"
    nws_alerts_url: str = "https://api.weather.gov/alerts/active"
    awc_metar_url: str = "https://aviationweather.gov/api/data/metar"
    awc_taf_url: str = "https://aviationweather.gov/api/data/taf"
    open_meteo_url: str = "https://api.open-meteo.com/v1/forecast"
    faa_nas_status_url: str = "https://nasstatus.faa.gov/"
    faa_airport_status_url: str = "https://www.fly.faa.gov/flyfaa/usmap.jsp"
    nws_docs_url: str = "https://www.weather.gov/documentation/services-web-api"
    awc_docs_url: str = "https://aviationweather.gov/data/api/"
    open_meteo_docs_url: str = "https://open-meteo.com/en/docs"
    freshness_hours: dict[str, int] = field(
        default_factory=lambda: {
            "NWS_ALERT": 24,
            "NWS_FORECAST_PERIOD": 12,
            "AWC_METAR": 3,
            "AWC_TAF": 6,
            "OPEN_METEO_CURRENT": 3,
            "OPEN_METEO_HOURLY": 6,
        }
    )
    forecast_horizon_days: int = 7
    taf_horizon_hours: int = 30
    site_url: str = os.getenv("ROUTEGUARD_SITE_URL", "").strip().rstrip("/")


settings = Settings()

AIR_TRAVEL_ASSUMPTION = (
    "Commercial air travel; airport-level assessment, not a verified flight itinerary."
)


def air_travel_scope(country: str) -> str:
    """State the current route's national focus explicitly."""
    return (
        f"{country} commercial air travel; airport-level assessment, "
        "not a verified flight itinerary."
    )
WHOLE_DAY_ASSUMPTION = (
    "Travel date is the departure airport's local calendar date; no departure time is "
    "used, so the assessment has whole-day precision."
)
DESTINATION_WINDOW_ASSUMPTION = (
    "Destination evidence is evaluated against the same UTC travel window; "
    "arrival-local calendar date is not modelled."
)
WEATHER_NOT_OPERATIONS_ASSUMPTION = (
    "All integrated providers supply weather or aviation-weather signals; RouteGuard "
    "does not claim an airport is delayed or closed. Operational status must be "
    "checked with the relevant national authority."
)


def coverage_note_for(weather_provider: str) -> str:
    """Disclose the real forward horizons of the providers used in one run."""
    if weather_provider == "NWS":
        horizons = (
            "NWS gridpoint forecasts cover approximately 7 days and NWS active alerts "
            "describe alerts active now; TAF forecasts cover approximately 30 hours."
        )
    else:
        horizons = (
            "Open-Meteo current conditions describe now and hourly forecasts cover "
            "approximately 2 days; TAF forecasts cover approximately 30 hours. "
            "No official national alert feed is available for this route."
        )
    return (
        horizons
        + " Beyond these horizons RouteGuard returns INDETERMINATE rather than a "
        "reassuring LOW. All evidence is evaluated at whole-day precision "
        "(00:00-24:00 departure-local)."
    )
