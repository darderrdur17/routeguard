"""History service: up to one year of ERA5 archive reanalysis for a route.

The history view is a browsing feature, not an assessment: it returns raw
daily model summaries with explicit nulls for missing days and never labels
reanalysis values as observations. Both airport fetches run concurrently; a
partial failure is represented per airport, a total failure raises
UPSTREAM_UNAVAILABLE so main.py can map it to a 502 envelope.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

from app.cities import Airport, CityLookupError, CityRegistry
from app.config import settings
from app.http_client import HTTPClient
from app.providers.open_meteo_archive import OpenMeteoArchiveAdapter
from app.service import RouteInputError

# ERA5 archive publishes roughly 6 days behind today; older ranges are allowed.
ARCHIVE_LAG_DAYS = 6
# One year deep, inclusive: 2024-01-01 → 2024-12-31 is 366 days of coverage.
ARCHIVE_MAX_SPAN_DAYS = 366


class HistoryService:
    """Validate, fetch and assemble daily archive weather for one airport pair."""

    def __init__(
        self,
        registry: CityRegistry | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        max_retries: int | None = None,
    ) -> None:
        """Build the service.

        ``transport`` and ``max_retries`` exist for offline unit tests; in
        production both stay ``None`` and the real HTTP client is used.
        """
        self._registry = registry or CityRegistry()
        self._transport = transport
        self._max_retries = max_retries

    async def fetch_history(
        self,
        origin: str,
        destination: str,
        start_date: date,
        end_date: date,
        request_id: str,
    ) -> dict[str, Any]:
        """Return the full /api/history response payload for one request."""
        try:
            origin_airport = self._registry.resolve(origin)
            destination_airport = self._registry.resolve(destination)
        except CityLookupError as exc:
            raise RouteInputError(
                CityLookupError.code,
                str(exc),
                {"query": exc.query, "hint": "Use a curated city name or IATA code."},
            ) from exc

        self._validate_dates(start_date, end_date)

        async with HTTPClient(
            request_id=request_id,
            transport=self._transport,
            max_retries=self._max_retries,
        ) as client:
            adapter = OpenMeteoArchiveAdapter(client)
            outcomes = await asyncio.gather(
                adapter.fetch(origin_airport, start_date, end_date),
                adapter.fetch(destination_airport, start_date, end_date),
                return_exceptions=True,
            )

        origin_block = self._block(outcomes[0], origin_airport)
        destination_block = self._block(outcomes[1], destination_airport)
        if origin_block["unavailable"] and destination_block["unavailable"]:
            raise RouteInputError(
                "UPSTREAM_UNAVAILABLE",
                "The ERA5 archive was unreachable for both airports.",
                {
                    "origin": origin_block.get("detail"),
                    "destination": destination_block.get("detail"),
                },
            )

        return {
            "request_id": request_id,
            "query": {
                "origin": origin,
                "destination": destination,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            },
            "provenance": {
                "source": "Open-Meteo Archive API",
                "model": "ERA5 reanalysis (model), not observations",
                "docs_url": settings.open_meteo_archive_docs_url,
                "retrieved_at": self._retrieved_at(),
            },
            "airports": {
                "origin": origin_block,
                "destination": destination_block,
            },
        }

    @staticmethod
    def _validate_dates(start_date: date, end_date: date) -> None:
        """Enforce the archive bounds; every rejection is an INVALID_DATE."""
        if start_date > end_date:
            raise RouteInputError(
                "INVALID_DATE",
                f"start_date {start_date.isoformat()} must be on or before "
                f"end_date {end_date.isoformat()}.",
            )
        today = datetime.now(timezone.utc).date()
        bound = today - timedelta(days=ARCHIVE_LAG_DAYS)
        if end_date > bound:
            raise RouteInputError(
                "INVALID_DATE",
                f"end_date must be on or before {bound.isoformat()} "
                f"(ERA5 archive publishes ~{ARCHIVE_LAG_DAYS} days behind today).",
            )
        # The old one-year lookback (``end_date - timedelta(days=365)``)
        # overflowed for dates near ``date.min`` and escaped as a 500. Both
        # comparisons below are overflow-free: ``end_date - date.min`` is a
        # bounded timedelta, and ``span_days`` is an integer. Dates too early to
        # form a supported archive window are rejected as INVALID_DATE, and the
        # span check preserves the strict "at most ARCHIVE_MAX_SPAN_DAYS
        # inclusive days" rule that fully subsumed the old lookback clause.
        if end_date - date.min < timedelta(days=ARCHIVE_MAX_SPAN_DAYS - 1):
            raise RouteInputError(
                "INVALID_DATE",
                f"end_date {end_date.isoformat()} is outside the supported archive range.",
            )
        span_days = (end_date - start_date).days
        if span_days + 1 > ARCHIVE_MAX_SPAN_DAYS:
            raise RouteInputError(
                "INVALID_DATE",
                f"History ranges span at most {ARCHIVE_MAX_SPAN_DAYS} days; "
                f"the requested range covers {span_days + 1} days.",
            )

    @staticmethod
    def _block(outcome: Any, airport: Airport) -> dict[str, Any]:
        """Convert one gather outcome into a contract block."""
        if isinstance(outcome, BaseException):
            return OpenMeteoArchiveAdapter.unavailable_block(
                airport, f"{type(outcome).__name__}"
            )
        return outcome

    @staticmethod
    def _retrieved_at() -> str:
        """Return the retrieval instant as an ISO-8601 UTC string."""
        return (
            datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )
