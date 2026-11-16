"""Open-Meteo adapter for routes outside the United States.

Open-Meteo is a free, no-key public weather API. It is used only where NWS has no
coverage. Aviation signal still comes from the NOAA Aviation Weather Center,
whose METAR/TAF network is international. No operational-status claim is made.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from app.cities import Airport
from app.config import settings
from app.http_client import HTTPClient, HTTPResult, UpstreamError
from app.providers.base import ProviderResult, build_status


class OpenMeteoAdapter:
    """Fetch current conditions and hourly precipitation for both airports."""

    name = "OPEN_METEO"

    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    async def fetch(
        self,
        origin: Airport,
        destination: Airport,
        window: dict[str, datetime],
    ) -> ProviderResult:
        """Fetch one compact forecast document per airport."""
        urls = {
            role: (
                f"{settings.open_meteo_url}?latitude={airport.lat}&longitude={airport.lon}"
                "&current=temperature_2m,weather_code,wind_speed_10m"
                "&hourly=precipitation_probability&forecast_days=3&timezone=UTC"
            )
            for role, airport in (("origin", origin), ("destination", destination))
        }
        outcomes = await asyncio.gather(
            *(
                self._http.get_json(url, accept="application/json", provider=self.name)
                for url in urls.values()
            ),
            return_exceptions=True,
        )
        payloads: list[dict[str, Any]] = []
        notes: list[str] = []
        errors: list[UpstreamError] = []
        latency_ms = 0
        codes: list[int] = []

        for (role, url), outcome in zip(urls.items(), outcomes, strict=True):
            if isinstance(outcome, UpstreamError):
                errors.append(outcome)
                continue
            if isinstance(outcome, BaseException):
                errors.append(UpstreamError(f"TransportError({type(outcome).__name__})"))
                continue
            codes.append(outcome.status_code)
            latency_ms += outcome.latency_ms
            payloads.extend(self._records(outcome, role, url, window, notes))

        malformed = any(note.startswith("Malformed") for note in notes)
        if errors and not payloads:
            state = "FAILED"
        elif errors or malformed:
            state = "DEGRADED"
        else:
            state = "OK"
        http_status = errors[0].http_status if errors and errors[0].http_status else None
        if http_status is None:
            http_status = 200 if 200 in codes else (codes[0] if codes else 200)

        return ProviderResult(
            payloads,
            build_status(
                self.name,
                state,
                http_status=http_status,
                latency_ms=latency_ms,
                error=str(errors[0]) if errors else None,
                note=" ".join(notes),
            ),
        )

    @staticmethod
    def _records(
        result: HTTPResult,
        role: str,
        url: str,
        window: dict[str, datetime],
        notes: list[str],
    ) -> list[dict[str, Any]]:
        """Turn one Open-Meteo document into two provenance-tagged envelopes."""
        data = result.data
        if not isinstance(data, dict):
            notes.append("Malformed Open-Meteo payload: object expected.")
            return []
        current = data.get("current")
        hourly = data.get("hourly")
        if not isinstance(current, dict) or not isinstance(hourly, dict):
            notes.append("Malformed Open-Meteo payload: current/hourly missing.")
            return []
        time_value = str(current.get("time", ""))
        if not time_value:
            notes.append("Malformed Open-Meteo current record skipped.")
            return []
        observed = time_value + ("Z" if not time_value.endswith("Z") else "")

        current_record = {
            "time": observed,
            "weather_code": current.get("weather_code"),
            "wind_speed_10m": current.get("wind_speed_10m"),
            "temperature_2m": current.get("temperature_2m"),
            "provider": "Open-Meteo",
        }
        # Pick the highest precipitation probability inside the travel window.
        times = hourly.get("time") or []
        probabilities = hourly.get("precipitation_probability") or []
        peak_probability = 0
        peak_time = ""
        if isinstance(times, list) and isinstance(probabilities, list):
            for stamp, value in zip(times, probabilities):
                if not isinstance(value, (int, float)):
                    continue
                try:
                    instant = datetime.fromisoformat(str(stamp) + "+00:00")
                except ValueError:
                    continue
                if window["start"] <= instant <= window["end"] and value > peak_probability:
                    peak_probability = float(value)
                    peak_time = str(stamp) + "Z"
        hourly_record = {
            "time": peak_time or observed,
            "precipitation_probability": peak_probability,
            "provider": "Open-Meteo",
        }
        return [
            {
                "_provider": "OPEN_METEO",
                "_signal": "OPEN_METEO_CURRENT",
                "_source_url": url,
                "_role": role,
                "record": current_record,
            },
            {
                "_provider": "OPEN_METEO",
                "_signal": "OPEN_METEO_HOURLY",
                "_source_url": url,
                "_role": role,
                "record": hourly_record,
            },
        ]
