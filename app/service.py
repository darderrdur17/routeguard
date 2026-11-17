"""Assessment orchestration: resolve, fetch concurrently, normalize, classify.

Provider errors are captured into ProviderStatus values and never raised to the
client. R00 input validation failures are raised as RouteInputError and mapped
to a 422 envelope in main.py.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.cities import Airport, CityLookupError, CityRegistry
from app.config import (
    DESTINATION_WINDOW_ASSUMPTION,
    RETROSPECTIVE_ASSUMPTION,
    RETROSPECTIVE_SOURCE_LIMITS_ASSUMPTION,
    WEATHER_NOT_OPERATIONS_ASSUMPTION,
    WHOLE_DAY_ASSUMPTION,
    air_travel_scope,
    coverage_note_for,
)
from app.http_client import HTTPClient
from app.logging import log_assessment
from app.models import (
    AssessRequest,
    Assessment,
    Evidence,
    ProviderStatus,
)
from app.normalize import Normalizer, utc_now
from app.providers.awc import AWCAdapter
from app.providers.base import ProviderAdapter, ProviderResult, build_status
from app.providers.nws import NWSAdapter
from app.providers.open_meteo import OpenMeteoAdapter
from app.risk import RiskResult, classify


class RouteInputError(Exception):
    """A validated request that cannot be resolved to curated airports."""

    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.details = details
        super().__init__(message)


def weather_provider_name(origin: Airport) -> str:
    """Return the weather provider available for the departure country."""
    return "NWS" if origin.country == "United States" else "OPEN_METEO"


def origin_local_today(airport: Airport) -> date:
    """Return the airport's local calendar date right now."""
    instant = datetime.now(timezone.utc)
    try:
        return instant.astimezone(ZoneInfo(airport.timezone)).date()
    except ZoneInfoNotFoundError:
        return instant.date()


class AssessmentService:
    """Coordinate the end-to-end assessment of one route and date."""

    def __init__(self, registry: CityRegistry | None = None) -> None:
        self._registry = registry or CityRegistry()

    @staticmethod
    def _travel_window(airport: Airport, travel_date: Any) -> dict[str, datetime]:
        """Convert the origin local calendar date into a 24 h UTC window."""
        try:
            zone = ZoneInfo(airport.timezone)
        except ZoneInfoNotFoundError as exc:
            raise RouteInputError(
                "INVALID_ROUTE",
                f"Unknown timezone configured for {airport.iata}.",
            ) from exc
        start_local = datetime.combine(travel_date, time.min, tzinfo=zone)
        # date.max + timedelta(days=1) overflows. For the final supported Python
        # date, close the window at the last instant of that day instead.
        if travel_date == date.max:
            end_local = datetime.combine(travel_date, time.max, tzinfo=zone)
        else:
            end_local = datetime.combine(
                travel_date + timedelta(days=1), time.min, tzinfo=zone
            )
        try:
            end_utc = end_local.astimezone(timezone.utc)
        except OverflowError:
            # Python cannot represent every local timezone's final UTC instant.
            # Use the latest representable UTC instant instead of failing the run.
            end_utc = datetime.max.replace(tzinfo=timezone.utc)
        return {
            "start": start_local.astimezone(timezone.utc),
            "end": end_utc,
        }

    @staticmethod
    def _failed_status(provider: str, exc: BaseException) -> ProviderStatus:
        """Build a redacted FAILED status when an adapter itself raises."""
        return build_status(
            provider,
            "FAILED",
            error=f"{type(exc).__name__}",
            note="Adapter could not complete; no provider evidence available.",
        )

    @staticmethod
    def _apply_normalization_notes(
        statuses: list[ProviderStatus],
        notes: dict[str, list[str]],
        degraded_providers: set[str],
    ) -> None:
        """Attach data-quality notes and downgrade affected provider statuses."""
        for status in statuses:
            provider_notes = notes.get(status.provider, [])
            if provider_notes:
                combined = " ".join(filter(None, [status.note, *provider_notes]))
                status.note = combined.strip()
            if status.provider in degraded_providers and status.status == "OK":
                status.status = "DEGRADED"

    async def assess(self, request: AssessRequest, request_id: str) -> Assessment:
        """Run one complete assessment and return a validated Assessment."""
        try:
            origin = self._registry.resolve(request.origin)
            destination = self._registry.resolve(request.destination)
        except CityLookupError as exc:
            raise RouteInputError(
                exc.code,
                str(exc),
                {"query": exc.query, "hint": "Use a curated city name or IATA code."},
            ) from exc
        if {origin.iata, origin.icao} == {destination.iata, destination.icao}:
            raise RouteInputError(
                "INVALID_ROUTE",
                "Origin and destination resolve to the same airport.",
                {
                    "origin": origin.city,
                    "destination": destination.city,
                    "iata": origin.iata,
                    "hint": "Use two distinct curated airports.",
                },
            )

        generated_at = utc_now()
        window = self._travel_window(origin, request.date)
        # A travel date before the departure airport's local today is a
        # retrospective assessment: historical METAR observations and
        # recent-past model hours replace the forward-looking providers. NWS
        # has no documented historical feed, so both route kinds use the same
        # global retrospective pair.
        retrospective = request.date < origin_local_today(origin)

        async with HTTPClient(request_id=request_id) as client:
            # NWS is authoritative only for US points. Elsewhere use Open-Meteo,
            # a free no-key provider; AWC aviation weather remains international.
            if retrospective:
                weather_provider = "OPEN_METEO"
                weather_adapter: ProviderAdapter = OpenMeteoAdapter(
                    client, retrospective=True
                )
                adapters: list[ProviderAdapter] = [
                    weather_adapter,
                    AWCAdapter(client, retrospective=True),
                ]
            else:
                weather_provider = weather_provider_name(origin)
                weather_adapter = (
                    NWSAdapter(client)
                    if weather_provider == "NWS"
                    else OpenMeteoAdapter(client)
                )
                adapters = [weather_adapter, AWCAdapter(client)]
            outcomes = await asyncio.gather(
                *(
                    adapter.fetch(origin, destination, window)
                    for adapter in adapters
                ),
                return_exceptions=True,
            )

        provider_status: list[ProviderStatus] = []
        payloads: list[dict[str, Any]] = []
        for adapter, outcome in zip(adapters, outcomes, strict=True):
            if isinstance(outcome, BaseException):
                provider_status.append(self._failed_status(adapter.name, outcome))
            else:
                result: ProviderResult = outcome
                payloads.extend(result.payloads)
                provider_status.append(result.status)

        locations = {
            "origin": (
                f"{origin.city} ({origin.iata})",
                origin.lat,
                origin.lon,
            ),
            "destination": (
                f"{destination.city} ({destination.iata})",
                destination.lat,
                destination.lon,
            ),
        }
        normalization = Normalizer(
            now=generated_at, locations=locations, retrospective=retrospective
        ).normalize(payloads, window)
        evidence: list[Evidence] = normalization.evidence
        self._apply_normalization_notes(
            provider_status, normalization.notes, normalization.degraded
        )
        for status in provider_status:
            status.evidence_count = sum(
                1 for item in evidence if item.provider == status.provider
            )

        risk: RiskResult = classify(
            evidence, provider_status, request.date, generated_at, window
        )

        route = {
            "origin_city": origin.city,
            "origin_state": origin.state,
            "origin_country": origin.country,
            "origin_region": origin.region,
            "origin_iata": origin.iata,
            "origin_icao": origin.icao,
            "origin_timezone": origin.timezone,
            "origin_lat": f"{origin.lat:.4f}",
            "origin_lon": f"{origin.lon:.4f}",
            "destination_city": destination.city,
            "destination_state": destination.state,
            "destination_country": destination.country,
            "destination_region": destination.region,
            "destination_iata": destination.iata,
            "destination_icao": destination.icao,
            "destination_timezone": destination.timezone,
            "destination_lat": f"{destination.lat:.4f}",
            "destination_lon": f"{destination.lon:.4f}",
            "basis": (
                "airport-level retrospective" if retrospective else "airport-level"
            ),
            "weather_provider": weather_provider,
            "coverage_focus": origin.country,
        }
        assumptions = [
            air_travel_scope(origin.country),
            WHOLE_DAY_ASSUMPTION,
            DESTINATION_WINDOW_ASSUMPTION,
            WEATHER_NOT_OPERATIONS_ASSUMPTION,
        ]
        if retrospective:
            assumptions.append(RETROSPECTIVE_ASSUMPTION)
            assumptions.append(RETROSPECTIVE_SOURCE_LIMITS_ASSUMPTION)
        if request.departure_time:
            assumptions.append(
                "A departure time was supplied but is not used by the MVP; "
                "whole-day precision is retained."
            )

        degraded = any(status.status != "OK" for status in provider_status)
        assessment = Assessment(
            request_id=request_id,
            generated_at=generated_at,
            route=route,
            travel_date=request.date,
            travel_window_utc=window,
            classification=risk.classification,
            confidence=risk.confidence,
            degraded=degraded,
            assumptions=assumptions,
            triggered_rules=risk.triggered_rules,
            evidence=evidence,
            recommendations=risk.recommendations,
            provider_status=provider_status,
            coverage_note=coverage_note_for(weather_provider, retrospective),
            assessment_mode="retrospective" if retrospective else "forward",
        )
        log_assessment(
            request_id=request_id,
            route=route,
            date=request.date.isoformat(),
            classification=assessment.classification,
            confidence=assessment.confidence,
            degraded=assessment.degraded,
            evidence_counts={
                status.provider: status.evidence_count for status in provider_status
            },
        )
        return assessment
