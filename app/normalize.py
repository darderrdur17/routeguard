"""Deterministic normalization of raw provider payloads into Evidence.

Every rule in this module follows docs/01_architecture.md section 7. Invalid or
unparsable records are flagged (never crash, never silently dropped) and are
reported back to the service as per-provider notes that downgrade status.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from app.config import settings
from app.models import (
    Evidence,
    Freshness,
    Geography,
    Reliability,
    Severity,
    SignalType,
    TemporalOverlap,
)

SEVERITY_RANK: dict[str, int] = {
    "UNKNOWN": 0,
    "MINOR": 1,
    "MODERATE": 2,
    "SEVERE": 3,
    "EXTREME": 4,
}

SIGNAL_LABELS: dict[str, str] = {
    "NWS_ALERT": "active weather alert",
    "NWS_FORECAST_PERIOD": "gridpoint forecast period",
    "AWC_METAR": "METAR observation",
    "AWC_TAF": "TAF forecast group",
    "OPEN_METEO_CURRENT": "Open-Meteo current condition",
    "OPEN_METEO_HOURLY": "Open-Meteo hourly forecast",
}


@dataclass
class NormalizationResult:
    """Normalized evidence plus per-provider data-quality notes."""

    evidence: list[Evidence] = field(default_factory=list)
    notes: dict[str, list[str]] = field(default_factory=dict)
    degraded: set[str] = field(default_factory=set)

    def add_note(self, provider: str, message: str, *, degraded: bool = True) -> None:
        """Record a data-quality note for a provider."""
        if provider not in self.notes:
            self.notes[provider] = []
        if message not in self.notes[provider]:
            self.notes[provider].append(message)
        if degraded:
            self.degraded.add(provider)


def utc_now() -> datetime:
    """Return the current timezone-aware UTC instant."""
    return datetime.now(timezone.utc)


def parse_instant(value: Any) -> datetime | None:
    """Parse an ISO 8601 string or epoch seconds into aware UTC, else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def as_float(value: Any) -> float | None:
    """Coerce a JSON scalar to float, returning None when not numeric."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def parse_visibility(value: Any) -> float | None:
    """Parse METAR (numeric) or TAF (string) visibility into statute miles."""
    if value is None:
        return None
    numeric = as_float(value)
    if numeric is not None:
        return numeric
    if not isinstance(value, str):
        return None
    text = value.strip().upper()
    if not text:
        return None
    fraction_match = re.fullmatch(r"M?(\d+)/(\d+)SM?", text)
    if fraction_match:
        numerator = float(fraction_match.group(1))
        denominator = float(fraction_match.group(2))
        return numerator / denominator if denominator else None
    match = re.match(r"P?(\d+(?:\.\d+)?)", text)
    return float(match.group(1)) if match else None


def max_wind_mph(wind_speed: Any) -> float | None:
    """Return the largest mph number in strings such as '5 to 16 mph'."""
    if not isinstance(wind_speed, str):
        return None
    numbers = [float(value) for value in re.findall(r"\d+(?:\.\d+)?", wind_speed)]
    return max(numbers) if numbers else None


def has_precip_keyword(text: Any) -> bool:
    """Return True when a forecast mentions rain, snow or thunder."""
    if not isinstance(text, str):
        return False
    lowered = text.lower()
    return any(word in lowered for word in ("rain", "snow", "thunder"))


def nws_alert_severity(properties: dict[str, Any]) -> Severity:
    """Map an NWS alert severity enum to the internal severity enum."""
    mapping: dict[str, Severity] = {
        "extreme": "EXTREME",
        "severe": "SEVERE",
        "moderate": "MODERATE",
        "minor": "MINOR",
        "unknown": "UNKNOWN",
    }
    return mapping.get(str(properties.get("severity", "")).strip().lower(), "UNKNOWN")


def forecast_severity(period: dict[str, Any]) -> Severity:
    """Derive severity from NWS forecast wind and precipitation fields."""
    wind = max_wind_mph(period.get("windSpeed"))
    pop_value = None
    pop = period.get("probabilityOfPrecipitation")
    if isinstance(pop, dict):
        pop_value = as_float(pop.get("value"))
    precipitating = has_precip_keyword(period.get("shortForecast"))
    if (wind is not None and wind >= 35) or (
        pop_value is not None and pop_value >= 80 and precipitating
    ):
        return "MODERATE"
    if (wind is not None and wind >= 20) or (
        pop_value is not None and pop_value >= 50 and precipitating
    ):
        return "MINOR"
    return "UNKNOWN"


def metar_severity(record: dict[str, Any]) -> Severity:
    """Derive severity from a decoded AWC METAR record."""
    flight_category = str(record.get("fltCat", "")).strip().upper()
    visibility = parse_visibility(record.get("visib"))
    wind_speed = as_float(record.get("wspd"))
    gust = as_float(record.get("wgst"))
    wx = str(record.get("wxString") or "").strip().upper()
    if flight_category == "LIFR" or (visibility is not None and visibility < 1):
        return "SEVERE"
    if (
        flight_category == "IFR"
        or (visibility is not None and visibility < 3)
        or (gust is not None and gust >= 50)
        or (wind_speed is not None and wind_speed >= 35)
        or "TS" in wx
    ):
        return "MODERATE"
    if flight_category == "MVFR" or wx:
        return "MINOR"
    return "UNKNOWN"


def taf_severity(forecast: dict[str, Any]) -> Severity:
    """Derive severity from one TAF forecast group."""
    visibility = parse_visibility(forecast.get("visib"))
    wx = str(forecast.get("wxString") or "").strip().upper()
    wind_speed = as_float(forecast.get("wspd"))
    gust = as_float(forecast.get("wgst"))
    if visibility is not None and visibility < 1:
        return "SEVERE"
    if (
        (visibility is not None and visibility < 3)
        or "TS" in wx
        or (gust is not None and gust >= 50)
        or (wind_speed is not None and wind_speed >= 35)
    ):
        return "MODERATE"
    if visibility is not None and visibility < 5:
        return "MINOR"
    return "UNKNOWN"


def open_meteo_current_severity(record: dict[str, Any]) -> Severity:
    """Derive severity from WMO weather codes and wind speed (km/h)."""
    code = as_float(record.get("weather_code"))
    wind = as_float(record.get("wind_speed_10m"))
    if code is not None and code >= 95:  # thunderstorm
        return "SEVERE"
    if (
        (code is not None and 71 <= code <= 77)  # snow
        or (code is not None and 80 <= code <= 82)  # rain showers
        or (wind is not None and wind >= 60)
    ):
        return "MODERATE"
    if (
        (code is not None and 51 <= code <= 67)  # drizzle / rain
        or (code is not None and 1 <= code <= 3)  # cloudy
        or (wind is not None and wind >= 30)
    ):
        return "MINOR"
    return "UNKNOWN"


def open_meteo_hourly_severity(record: dict[str, Any]) -> Severity:
    """Derive severity from peak precipitation probability in the travel window."""
    probability = as_float(record.get("precipitation_probability"))
    if probability is None:
        return "UNKNOWN"
    if probability >= 80:
        return "MODERATE"
    if probability >= 40:
        return "MINOR"
    return "UNKNOWN"


def temporal_overlap(
    valid_from: datetime | None,
    valid_to: datetime | None,
    window: dict[str, datetime],
) -> TemporalOverlap:
    """Compare an evidence validity interval with the UTC travel window."""
    if valid_from is None or valid_to is None:
        return "UNKNOWN"
    start = window["start"]
    end = window["end"]
    if valid_to <= start or valid_from >= end:
        return "NONE"
    if valid_from <= start and valid_to >= end:
        return "FULL"
    return "PARTIAL"


def freshness(
    issued_at: datetime | None, signal_type: str, now: datetime
) -> Freshness:
    """Classify evidence issue age against the documented per-signal threshold."""
    if issued_at is None:
        return "UNKNOWN"
    threshold = settings.freshness_hours.get(signal_type)
    if threshold is None:
        return "UNKNOWN"
    age_seconds = (now - issued_at).total_seconds()
    return "FRESH" if age_seconds <= threshold * 3600 else "STALE"


def evidence_id(
    provider: str,
    signal_type: str,
    source_url: str,
    signal: str,
    valid_from: datetime | None,
) -> str:
    """Return a deterministic 16-hex identifier for one evidence item."""
    material = "|".join(
        [
            provider,
            signal_type,
            source_url,
            signal,
            valid_from.isoformat() if valid_from else "",
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def _relevance_reason(provider: str, signal_type: str, role: str, overlap: str) -> str:
    """Build a plain deterministic relevance sentence."""
    if role in {"origin", "destination"}:
        location = f"the {role} airport"
    else:
        location = "an unmatched station"
    return (
        f"{provider} {SIGNAL_LABELS.get(signal_type, 'signal')} at {location} has "
        f"{overlap.lower()} overlap with the selected travel day."
    )


def _excerpt(record: dict[str, Any]) -> str:
    """Return a compact, bounded, deterministic excerpt of the raw record."""
    try:
        text = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)
    except (TypeError, ValueError):
        text = str(record)
    return text[:240]


class Normalizer:
    """Convert verified provider envelopes into typed Evidence objects."""

    def __init__(
        self,
        now: datetime | None = None,
        locations: dict[str, tuple[str, float, float]] | None = None,
    ) -> None:
        self._now = now or utc_now()
        # role -> (label, latitude, longitude), built from the curated registry.
        self._locations = locations or {}

    def normalize(
        self, payloads: list[dict[str, Any]], window: dict[str, datetime]
    ) -> NormalizationResult:
        """Normalize all payload envelopes in stable input order."""
        result = NormalizationResult()
        for envelope in payloads:
            try:
                self._normalize_one(envelope, window, result)
            except Exception as exc:  # defensive: one bad record must not crash a run
                provider = str(envelope.get("_provider", "UNKNOWN"))
                result.add_note(
                    provider,
                    f"Malformed {provider} record skipped ({type(exc).__name__}).",
                )
        return result

    def _normalize_one(
        self,
        envelope: dict[str, Any],
        window: dict[str, datetime],
        result: NormalizationResult,
    ) -> None:
        """Dispatch one envelope to its signal-specific normalizer."""
        provider = str(envelope.get("_provider", "UNKNOWN"))
        signal_type = str(envelope.get("_signal", ""))
        record = envelope.get("record")
        if not isinstance(record, dict):
            result.add_note(provider, f"Malformed {signal_type} record skipped.")
            return
        if signal_type == "NWS_ALERT":
            self._nws_alert(envelope, record, window, result)
        elif signal_type == "NWS_FORECAST_PERIOD":
            self._nws_forecast(envelope, record, window, result)
        elif signal_type == "AWC_METAR":
            self._awc_metar(envelope, record, window, result)
        elif signal_type == "AWC_TAF":
            self._awc_taf(envelope, record, window, result)
        elif signal_type in {"OPEN_METEO_CURRENT", "OPEN_METEO_HOURLY"}:
            self._open_meteo(envelope, record, window, result, signal_type)
        else:
            result.add_note(provider, f"Malformed record with unknown signal {signal_type}.")

    def _append(
        self,
        *,
        result: NormalizationResult,
        envelope: dict[str, Any],
        window: dict[str, datetime],
        signal: str,
        severity: Severity,
        observed_at: datetime | None,
        valid_from: datetime | None,
        valid_to: datetime | None,
        note: str | None = None,
        freshness_ref: datetime | None = None,
    ) -> None:
        """Build and append one Evidence, applying all shared attributes.

        ``freshness_ref`` lets a provider declare which timestamp represents its
        data generation/issue time without misrepresenting a forecast validity
        timestamp as an observation.
        """
        provider = str(envelope["_provider"])
        signal_type = str(envelope["_signal"])
        source_url = str(envelope.get("_source_url", ""))
        reliability: Reliability = (
            "HIGH"
            if signal_type in {"NWS_ALERT", "AWC_METAR", "OPEN_METEO_CURRENT"}
            else "MEDIUM"
        )
        geography: Geography = (
            "EXACT" if envelope.get("_role") in {"origin", "destination"} else "UNKNOWN"
        )
        overlap = temporal_overlap(valid_from, valid_to, window)
        location = self._locations.get(str(envelope.get("_role", "")))
        item = Evidence(
            id=evidence_id(provider, signal_type, source_url, signal, valid_from),
            provider=provider,  # type: ignore[arg-type]
            signal_type=signal_type,  # type: ignore[arg-type]
            signal=signal[:240],
            severity=severity,
            reliability=reliability,
            geography=geography,
            temporal_overlap=overlap,
            freshness=freshness(
                freshness_ref if freshness_ref is not None else observed_at,
                signal_type,
                self._now,
            ),
            observed_at=observed_at,
            valid_from=valid_from,
            valid_to=valid_to,
            relevance_reason=_relevance_reason(
                provider, signal_type, str(envelope.get("_role", "unknown")), overlap
            ),
            source_url=source_url,
            raw_excerpt=_excerpt(envelope["record"]),
            location_label=location[0] if location else None,
            latitude=location[1] if location else None,
            longitude=location[2] if location else None,
        )
        result.evidence.append(item)
        if note:
            result.add_note(provider, note)

    def _nws_alert(
        self,
        envelope: dict[str, Any],
        record: dict[str, Any],
        window: dict[str, datetime],
        result: NormalizationResult,
    ) -> None:
        """Normalize one NWS active-alert feature."""
        properties = record.get("properties")
        if not isinstance(properties, dict):
            result.add_note("NWS", "Malformed NWS alert properties skipped.")
            return
        observed = parse_instant(properties.get("sent")) or parse_instant(
            properties.get("effective")
        )
        valid_from = parse_instant(properties.get("onset")) or observed
        valid_to = parse_instant(properties.get("expires")) or parse_instant(
            properties.get("ends")
        )
        signal = str(properties.get("event") or "").strip()
        severity = nws_alert_severity(properties)
        note: str | None = None
        if not signal or severity == "UNKNOWN":
            note = "Malformed NWS alert (missing event/severity) flagged UNKNOWN."
            signal = signal or "unnamed-alert"
        self._append(
            result=result,
            envelope=envelope,
            window=window,
            signal=signal,
            severity=severity,
            observed_at=observed,
            valid_from=valid_from,
            valid_to=valid_to,
            note=note,
        )

    def _nws_forecast(
        self,
        envelope: dict[str, Any],
        record: dict[str, Any],
        window: dict[str, datetime],
        result: NormalizationResult,
    ) -> None:
        """Normalize one NWS gridpoint forecast period with a severity rule."""
        severity = forecast_severity(record)
        if severity == "UNKNOWN":
            return
        valid_from = parse_instant(record.get("startTime"))
        valid_to = parse_instant(record.get("endTime"))
        if valid_from is None or valid_to is None:
            result.add_note("NWS", "Malformed NWS forecast period times skipped.")
            return
        signal = str(record.get("shortForecast") or "").strip() or "unnamed-forecast"
        self._append(
            result=result,
            envelope=envelope,
            window=window,
            signal=signal,
            severity=severity,
            observed_at=parse_instant(envelope.get("_generated_at")),
            valid_from=valid_from,
            valid_to=valid_to,
        )

    def _awc_metar(
        self,
        envelope: dict[str, Any],
        record: dict[str, Any],
        window: dict[str, datetime],
        result: NormalizationResult,
    ) -> None:
        """Normalize one decoded AWC METAR observation."""
        severity = metar_severity(record)
        if severity == "UNKNOWN":
            return
        observed = parse_instant(record.get("reportTime")) or parse_instant(
            record.get("obsTime")
        )
        valid_to = observed + timedelta(hours=1) if observed else None
        flight_category = str(record.get("fltCat") or "UNKNOWN").strip().upper()
        wx = str(record.get("wxString") or "none").strip() or "none"
        signal = f"{flight_category}:{wx}"
        self._append(
            result=result,
            envelope=envelope,
            window=window,
            signal=signal,
            severity=severity,
            observed_at=observed,
            valid_from=observed,
            valid_to=valid_to,
        )

    def _awc_taf(
        self,
        envelope: dict[str, Any],
        record: dict[str, Any],
        window: dict[str, datetime],
        result: NormalizationResult,
    ) -> None:
        """Normalize every TAF forecast group with a severity rule."""
        issued = parse_instant(record.get("issueTime")) or parse_instant(
            record.get("bulletinTime")
        )
        forecasts = record.get("fcsts")
        if not isinstance(forecasts, list):
            result.add_note("AWC", "Malformed AWC TAF forecast array skipped.")
            return
        for forecast in forecasts:
            if not isinstance(forecast, dict):
                result.add_note("AWC", "Malformed AWC TAF forecast group skipped.")
                continue
            severity = taf_severity(forecast)
            if severity == "UNKNOWN":
                continue
            valid_from = parse_instant(forecast.get("timeFrom"))
            valid_to = parse_instant(forecast.get("timeTo"))
            if valid_from is None or valid_to is None:
                result.add_note("AWC", "Malformed AWC TAF group times skipped.")
                continue
            wx_values = {
                str(value).strip().upper()
                for value in [forecast.get("wxString")]
                if isinstance(value, str) and value.strip()
            }
            signal = ", ".join(sorted(wx_values)) if wx_values else "no-significant-wx"
            self._append(
                result=result,
                envelope=envelope,
                window=window,
                signal=signal,
                severity=severity,
                observed_at=issued,
                valid_from=valid_from,
                valid_to=valid_to,
            )

    def _open_meteo(
        self,
        envelope: dict[str, Any],
        record: dict[str, Any],
        window: dict[str, datetime],
        result: NormalizationResult,
        signal_type: str,
    ) -> None:
        """Normalize one Open-Meteo current or hourly record."""
        is_current = signal_type == "OPEN_METEO_CURRENT"
        if is_current:
            severity = open_meteo_current_severity(record)
            observed = parse_instant(record.get("time"))
            if observed is None:
                result.add_note("OPEN_METEO", "Malformed Open-Meteo current time skipped.")
                return
            signal = (
                f"WMO {record.get('weather_code', '?')} · "
                f"wind {record.get('wind_speed_10m', '?')} km/h"
            )
        else:
            severity = open_meteo_hourly_severity(record)
            observed = None
            signal = f"peak precipitation {record.get('precipitation_probability', '?')}%"
        if severity == "UNKNOWN":
            return
        valid_from = observed if is_current else parse_instant(record.get("time"))
        if valid_from is None:
            result.add_note("OPEN_METEO", "Malformed Open-Meteo forecast time skipped.")
            return
        self._append(
            result=result,
            envelope=envelope,
            window=window,
            signal=signal,
            severity=severity,
            observed_at=observed,
            valid_from=valid_from,
            valid_to=valid_from + timedelta(hours=1),
            # Open-Meteo does not expose an issue time for its hourly forecast.
            # Use the forecast hour as the freshness reference, while leaving
            # observed_at absent so it is never reported as an observation.
            freshness_ref=valid_from if not is_current else None,
        )
