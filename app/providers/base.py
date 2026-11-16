"""Shared adapter protocol and status construction helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from app.cities import Airport
from app.config import settings
from app.models import ProviderStatus


def utc_now() -> datetime:
    """Return the current timezone-aware UTC instant."""
    return datetime.now(timezone.utc)


@dataclass
class ProviderResult:
    """Raw payload envelopes plus the adapter's own status.

    Envelopes are plain dicts with ``_provider``, ``_signal``, ``_source_url``,
    ``_role`` and ``record`` keys so that normalization can explain provenance.
    """

    payloads: list[dict[str, Any]]
    status: ProviderStatus


@runtime_checkable
class ProviderAdapter(Protocol):
    """Contract implemented by NWS and AWC adapters."""

    name: str

    async def fetch(
        self,
        origin: Airport,
        destination: Airport,
        window: dict[str, datetime],
    ) -> ProviderResult:
        """Fetch raw provider payloads without raising to the caller.

        Implementors provide the concrete fetch logic; this protocol only
        declares the contract shared by both adapters.
        """
        raise NotImplementedError("ProviderAdapter implementations must define fetch")


def authoritative_url(provider: str) -> str:
    """Return the human-checkable fallback link for a provider."""
    if provider == "NWS":
        return settings.nws_docs_url
    if provider == "AWC":
        return settings.awc_docs_url
    if provider == "OPEN_METEO":
        return settings.open_meteo_docs_url
    return settings.faa_nas_status_url


def build_status(
    provider: str,
    status: str,
    *,
    http_status: int | None = None,
    latency_ms: int | None = None,
    error: str | None = None,
    note: str = "",
    fetched_at: datetime | None = None,
) -> ProviderStatus:
    """Build a validated ProviderStatus with consistent defaults."""
    return ProviderStatus(
        provider=provider,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        http_status=http_status,
        latency_ms=latency_ms,
        fetched_at=fetched_at or utc_now(),
        evidence_count=0,
        error=error,
        note=note,
        authoritative_url=authoritative_url(provider),
    )
