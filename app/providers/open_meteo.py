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

    def __init__(self, http: HTTPClient, retrospective: bool = False) -> None:
        self._http = http
        self._retrospective = retrospective

    async def fetch(
        self,
        origin: Airport,
        destination: Airport,
        window: dict[str, datetime],
    ) -> ProviderResult:
        """Fetch one compact weather document per airport.

        Forward runs read current conditions plus hourly precipitation
        probability. Retrospective runs read recent-past model hours
        (``past_days``) and summarise the assessed day per airport; this is
        reanalysis data, not a station observation.
        """
        if self._retrospective:
            urls = {
                role: (
                    f"{settings.open_meteo_url}?latitude={airport.lat}&longitude={airport.lon}"
                    "&hourly=weather_code,temperature_2m,wind_speed_10m,precipitation"
                    "&past_days=7&forecast_days=1&timezone=UTC"
                )
                for role, airport in (("origin", origin), ("destination", destination))
            }
        else:
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
            if self._retrospective:
                payloads.extend(
                    self._retrospective_records(outcome, role, url, window, notes)
                )
            else:
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
    def _retrospective_records(
        result: HTTPResult,
        role: str,
        url: str,
        window: dict[str, datetime],
        notes: list[str],
    ) -> list[dict[str, Any]]:
        """Summarise the assessed day from recent-past hourly model data.

        One envelope per airport: the most severe hour inside the UTC travel
        window (by the shared WMO/wind severity rule), with the day's peak wind
        and precipitation attached. All hours outside the window are ignored.
        """
        data = result.data
        if not isinstance(data, dict):
            notes.append("Malformed Open-Meteo payload: object expected.")
            return []
        hourly = data.get("hourly")
        if not isinstance(hourly, dict):
            notes.append("Malformed Open-Meteo payload: hourly missing.")
            return []
        times = hourly.get("time") or []
        weather_codes = hourly.get("weather_code") or []
        temperatures = hourly.get("temperature_2m") or []
        winds = hourly.get("wind_speed_10m") or []
        precipitation = hourly.get("precipitation") or []
        if not isinstance(times, list) or not times:
            notes.append("Malformed Open-Meteo payload: hourly times missing.")
            return []

        from app.normalize import SEVERITY_RANK, open_meteo_current_severity

        worst_rank = -1
        worst_index: int | None = None
        peak_wind: float | None = None
        peak_precip: float | None = None
        in_window = 0
        for index, stamp in enumerate(times):
            try:
                instant = datetime.fromisoformat(str(stamp) + "+00:00")
            except ValueError:
                continue
            if not (window["start"] <= instant <= window["end"]):
                continue
            in_window += 1
            wind_value = winds[index] if index < len(winds) else None
            precip_value = precipitation[index] if index < len(precipitation) else None
            wind_number = float(wind_value) if isinstance(wind_value, (int, float)) else None
            precip_number = (
                float(precip_value) if isinstance(precip_value, (int, float)) else None
            )
            if wind_number is not None and (peak_wind is None or wind_number > peak_wind):
                peak_wind = wind_number
            if precip_number is not None and (
                peak_precip is None or precip_number > peak_precip
            ):
                peak_precip = precip_number
            rank = SEVERITY_RANK[
                open_meteo_current_severity(
                    {
                        "weather_code": weather_codes[index]
                        if index < len(weather_codes)
                        else None,
                        "wind_speed_10m": wind_value,
                    }
                )
            ]
            if rank > worst_rank:
                worst_rank = rank
                worst_index = index
        if in_window == 0 or worst_index is None:
            notes.append(
                "No Open-Meteo retrospective hours fall inside the assessed window."
            )
            return []
        worst_time = str(times[worst_index]) + "Z"
        record = {
            "time": worst_time,
            "weather_code": weather_codes[worst_index]
            if worst_index < len(weather_codes)
            else None,
            "wind_speed_10m": peak_wind,
            "precipitation": peak_precip,
            "temperature_2m": temperatures[worst_index]
            if worst_index < len(temperatures)
            else None,
            "provider": "Open-Meteo",
        }
        return [
            {
                "_provider": "OPEN_METEO",
                "_signal": "OPEN_METEO_RETROSPECTIVE",
                "_source_url": url,
                "_role": role,
                "record": record,
            }
        ]

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
