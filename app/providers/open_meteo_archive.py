"""Open-Meteo Archive adapter: ERA5 daily reanalysis for one airport per call.

The archive endpoint is free and keyless. It serves model reanalysis, never
station observations; callers must keep that distinction visible. Missing or
mismatched daily series are padded with explicit nulls rather than dropped or
interpolated.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.cities import Airport
from app.config import settings
from app.http_client import HTTPClient, UpstreamError

# The exact daily series requested from the archive endpoint, in request order.
DAILY_SERIES: tuple[str, ...] = (
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "wind_speed_10m_max",
    "weather_code",
)


class OpenMeteoArchiveAdapter:
    """Fetch one ERA5 archive document per airport; never raises to the caller.

    Every outcome — success or failure — is returned as a plain dict shaped
    like one ``airports.<role>`` block of the history response contract, so the
    service can assemble a 200 response around a partial failure.
    """

    name = "OPEN_METEO_ARCHIVE"

    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    async def fetch(
        self, airport: Airport, start_date: date, end_date: date
    ) -> dict[str, Any]:
        """Fetch daily ERA5 reanalysis for one airport.

        The archive endpoint serves one coordinate per call, so the service
        issues two concurrent fetches for an airport pair.
        """
        url = (
            f"{settings.open_meteo_archive_url}?latitude={airport.lat}&longitude={airport.lon}"
            f"&start_date={start_date.isoformat()}&end_date={end_date.isoformat()}"
            f"&daily={','.join(DAILY_SERIES)}&timezone=UTC"
        )
        try:
            result = await self._http.get_json(
                url, accept="application/json", provider=self.name
            )
        except UpstreamError as exc:
            # UpstreamError messages are already redacted (class + HTTP code).
            return self.unavailable_block(airport, str(exc))
        return self._parse(result.data, airport)

    @staticmethod
    def unavailable_block(airport: Airport, detail: str) -> dict[str, Any]:
        """Build the redacted per-airport failure block of the contract."""
        return {
            "iata": airport.iata,
            "icao": airport.icao,
            "city": airport.city,
            "country": airport.country,
            "latitude": airport.lat,
            "longitude": airport.lon,
            "daily": None,
            "daily_units": None,
            "unavailable": True,
            "detail": detail,
        }

    def _parse(self, data: Any, airport: Airport) -> dict[str, Any]:
        """Turn one archive document into a contract block with explicit nulls."""
        if not isinstance(data, dict):
            return self.unavailable_block(
                airport, "Malformed Open-Meteo Archive payload: object expected."
            )
        daily = data.get("daily")
        if not isinstance(daily, dict):
            return self.unavailable_block(
                airport, "Malformed Open-Meteo Archive payload: daily missing."
            )
        times = daily.get("time")
        if not isinstance(times, list) or not times:
            return self.unavailable_block(
                airport, "Malformed Open-Meteo Archive payload: daily.time missing."
            )
        length = len(times)
        units = data.get("daily_units")
        series = {
            key: self._series(daily.get(key), length) for key in DAILY_SERIES
        }
        return {
            "iata": airport.iata,
            "icao": airport.icao,
            "city": airport.city,
            "country": airport.country,
            "latitude": airport.lat,
            "longitude": airport.lon,
            "daily": {"time": [str(stamp) for stamp in times], **series},
            "daily_units": units if isinstance(units, dict) else {},
            "unavailable": False,
            "detail": None,
        }

    @staticmethod
    def _series(raw: Any, length: int) -> list[int | float | None]:
        """Normalize one daily series to ``length`` numeric-or-null entries.

        Mismatched-length upstream arrays are padded with explicit nulls or
        truncated to the length of ``time``; non-numeric entries become null.
        Values are never interpolated.
        """
        values = raw if isinstance(raw, list) else []
        output: list[int | float | None] = []
        for index in range(length):
            value = values[index] if index < len(values) else None
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                output.append(None)
            else:
                output.append(value)
        return output
