"""NWS adapter: point metadata, then active alerts and gridpoint forecast.

The forecast URL is always read from the ``points`` response; it is never
synthesised from a hardcoded grid. Failure of ``points`` disables both NWS
signals and yields a single FAILED ProviderStatus entry.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from app.cities import Airport
from app.config import settings
from app.http_client import HTTPClient, HTTPResult, UpstreamError
from app.providers.base import ProviderResult, build_status


class NWSAdapter:
    """Fetch and lightly validate NWS JSON payloads for the origin airport."""

    name = "NWS"

    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    async def fetch(
        self,
        origin: Airport,
        destination: Airport,
        window: dict[str, datetime],
    ) -> ProviderResult:
        """Fetch alerts and forecast for the origin airport point.

        ``destination`` and ``window`` are accepted for the adapter protocol;
        NWS point signals are origin-only and are later evaluated against the
        shared UTC travel window by the normalizer.
        """
        _ = (destination, window)
        point = origin.nws_point
        points_url = settings.nws_points_url.format(point=point)
        alerts_url = f"{settings.nws_alerts_url}?point={point}"

        try:
            points = await self._http.get_json(points_url, accept="application/geo+json", provider=self.name)
        except UpstreamError as exc:
            return ProviderResult(
                [],
                build_status(
                    self.name,
                    "FAILED",
                    http_status=exc.http_status,
                    error=str(exc),
                    note="NWS point metadata unavailable; alerts and forecast skipped.",
                ),
            )

        properties = self._properties(points)
        forecast_url = properties.get("forecast") if properties else None
        if not isinstance(forecast_url, str) or not forecast_url.startswith(
            "https://api.weather.gov/gridpoints/"
        ):
            return ProviderResult(
                [],
                build_status(
                    self.name,
                    "FAILED",
                    http_status=points.status_code,
                    error="InvalidPointsPayload",
                    note="NWS points response did not contain a valid forecast URL.",
                    latency_ms=points.latency_ms,
                ),
            )

        outcomes = await asyncio.gather(
            self._http.get_json(alerts_url, accept="application/geo+json", provider=self.name),
            self._http.get_json(forecast_url, accept="application/geo+json", provider=self.name),
            return_exceptions=True,
        )
        payloads: list[dict[str, Any]] = []
        notes: list[str] = []
        errors: list[UpstreamError] = []
        malformed = False
        latency_ms = points.latency_ms

        alert_result, forecast_result = outcomes
        if isinstance(alert_result, UpstreamError):
            errors.append(alert_result)
        elif isinstance(alert_result, BaseException):
            errors.append(UpstreamError(f"TransportError({type(alert_result).__name__})"))
        else:
            payloads.extend(self._alert_payloads(alert_result, notes))
            latency_ms += alert_result.latency_ms
            if alert_result.status_code == 204:
                notes.append("204 No Content - no active alerts at origin point.")

        if isinstance(forecast_result, UpstreamError):
            errors.append(forecast_result)
        elif isinstance(forecast_result, BaseException):
            errors.append(UpstreamError(f"TransportError({type(forecast_result).__name__})"))
        else:
            payloads.extend(self._forecast_payloads(forecast_result, notes))
            latency_ms += forecast_result.latency_ms
            if forecast_result.status_code == 204:
                notes.append("204 No Content - no gridpoint forecast.")

        malformed = any(note.startswith("Malformed") for note in notes)
        if errors and not payloads:
            state = "FAILED"
        elif errors or malformed:
            state = "DEGRADED"
        else:
            state = "OK"

        http_status = (
            errors[0].http_status
            if errors and errors[0].http_status is not None
            else points.status_code
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
    def _properties(result: HTTPResult) -> dict[str, Any] | None:
        """Return the points feature properties when well-formed."""
        data = result.data
        if not isinstance(data, dict):
            return None
        properties = data.get("properties")
        return properties if isinstance(properties, dict) else None

    @staticmethod
    def _alert_payloads(result: HTTPResult, notes: list[str]) -> list[dict[str, Any]]:
        """Wrap each active alert feature with provenance metadata."""
        if result.data is None:
            return []
        if not isinstance(result.data, dict) or not isinstance(
            result.data.get("features"), list
        ):
            notes.append("Malformed NWS alerts payload: features array missing.")
            return []
        payloads: list[dict[str, Any]] = []
        for feature in result.data["features"]:
            if not isinstance(feature, dict) or not isinstance(
                feature.get("properties"), dict
            ):
                notes.append("Malformed NWS alert feature skipped.")
                continue
            payloads.append(
                {
                    "_provider": "NWS",
                    "_signal": "NWS_ALERT",
                    "_source_url": result.url,
                    "_role": "origin",
                    "record": feature,
                }
            )
        return payloads

    @staticmethod
    def _forecast_payloads(result: HTTPResult, notes: list[str]) -> list[dict[str, Any]]:
        """Wrap each forecast period with provenance metadata."""
        if result.data is None:
            return []
        if not isinstance(result.data, dict):
            notes.append("Malformed NWS forecast payload: object expected.")
            return []
        properties = result.data.get("properties")
        if not isinstance(properties, dict) or not isinstance(
            properties.get("periods"), list
        ):
            notes.append("Malformed NWS forecast payload: periods array missing.")
            return []
        generated_at = properties.get("generatedAt")
        payloads: list[dict[str, Any]] = []
        for period in properties["periods"]:
            if not isinstance(period, dict):
                notes.append("Malformed NWS forecast period skipped.")
                continue
            payloads.append(
                {
                    "_provider": "NWS",
                    "_signal": "NWS_FORECAST_PERIOD",
                    "_source_url": result.url,
                    "_role": "origin",
                    "_generated_at": generated_at,
                    "record": period,
                }
            )
        return payloads
