"""NOAA Aviation Weather Center adapter: batched METAR + TAF JSON.

Origin and destination ICAO ids are sent as one comma-separated ``ids`` value
per endpoint. METAR uses ``hours=2``; TAF has no ``hours`` parameter.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from app.cities import Airport
from app.config import settings
from app.http_client import HTTPClient, HTTPResult, UpstreamError
from app.providers.base import ProviderResult, build_status


class AWCAdapter:
    """Fetch and lightly validate AWC METAR and TAF JSON arrays."""

    name = "AWC"

    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    async def fetch(
        self,
        origin: Airport,
        destination: Airport,
        window: dict[str, datetime],
    ) -> ProviderResult:
        """Fetch both station products for the route in two outbound calls."""
        _ = window
        ids = f"{origin.icao},{destination.icao}"
        metar_url = f"{settings.awc_metar_url}?ids={ids}&format=json&hours=2"
        taf_url = f"{settings.awc_taf_url}?ids={ids}&format=json"

        outcomes = await asyncio.gather(
            self._http.get_json(metar_url, accept="application/json", provider=self.name),
            self._http.get_json(taf_url, accept="application/json", provider=self.name),
            return_exceptions=True,
        )
        payloads: list[dict[str, Any]] = []
        notes: list[str] = []
        errors: list[UpstreamError] = []
        latency_ms = 0

        metar_result, taf_result = outcomes
        if isinstance(metar_result, UpstreamError):
            errors.append(metar_result)
        elif isinstance(metar_result, BaseException):
            errors.append(UpstreamError(f"TransportError({type(metar_result).__name__})"))
        else:
            payloads.extend(self._records(metar_result, "AWC_METAR", origin, destination, notes))
            latency_ms += metar_result.latency_ms
            if metar_result.status_code == 204:
                notes.append("204 No Content - no current METAR.")

        if isinstance(taf_result, UpstreamError):
            errors.append(taf_result)
        elif isinstance(taf_result, BaseException):
            errors.append(UpstreamError(f"TransportError({type(taf_result).__name__})"))
        else:
            payloads.extend(self._records(taf_result, "AWC_TAF", origin, destination, notes))
            latency_ms += taf_result.latency_ms
            if taf_result.status_code == 204:
                notes.append("204 No Content - no current TAF.")

        malformed = any(note.startswith("Malformed") for note in notes)
        if errors and not payloads:
            state = "FAILED"
        elif errors or malformed:
            state = "DEGRADED"
        else:
            state = "OK"
        http_status = errors[0].http_status if errors and errors[0].http_status else None
        if http_status is None:
            success_codes = [
                result.status_code
                for result in (metar_result, taf_result)
                if isinstance(result, HTTPResult)
            ]
            http_status = (
                200 if 200 in success_codes else (success_codes[0] if success_codes else 200)
            )

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
        signal: str,
        origin: Airport,
        destination: Airport,
        notes: list[str],
    ) -> list[dict[str, Any]]:
        """Wrap each AWC record with provenance and station role metadata."""
        if result.data is None:
            return []
        if not isinstance(result.data, list):
            notes.append(f"Malformed AWC {signal} payload: array expected.")
            return []
        payloads: list[dict[str, Any]] = []
        for record in result.data:
            if not isinstance(record, dict):
                notes.append(f"Malformed AWC {signal} record skipped.")
                continue
            icao = str(record.get("icaoId", "")).upper()
            role = "origin" if icao == origin.icao else "destination"
            if icao not in {origin.icao, destination.icao}:
                role = "unknown"
            payloads.append(
                {
                    "_provider": "AWC",
                    "_signal": signal,
                    "_source_url": result.url,
                    "_role": role,
                    "record": record,
                }
            )
        return payloads
