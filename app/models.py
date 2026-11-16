"""Pydantic v2 models shared by the API, service, risk engine and UI.

There is deliberately no numeric score field anywhere in this module: risk
(classification) and confidence are independent categorical axes.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_serializer,
    field_validator,
    model_validator,
)

from app.cities import CityLookupError, CityRegistry

ProviderName = Literal["NWS", "AWC", "OPEN_METEO"]
Severity = Literal["EXTREME", "SEVERE", "MODERATE", "MINOR", "UNKNOWN"]
Reliability = Literal["HIGH", "MEDIUM", "LOW"]
Geography = Literal["EXACT", "NEAR", "UNKNOWN"]
TemporalOverlap = Literal["FULL", "PARTIAL", "NONE", "UNKNOWN"]
Freshness = Literal["FRESH", "STALE", "UNKNOWN"]
Classification = Literal["CLEAR", "LOW", "ELEVATED", "HIGH", "CRITICAL", "INDETERMINATE"]
Confidence = Literal["HIGH", "MEDIUM", "LOW"]
SignalType = Literal[
    "NWS_ALERT",
    "NWS_FORECAST_PERIOD",
    "AWC_METAR",
    "AWC_TAF",
    "OPEN_METEO_CURRENT",
    "OPEN_METEO_HOURLY",
]

# Only the two terminal no-coverage outcomes (R01/R08) may carry an empty
# evidence_ids list. C03 always links to the surviving provider's evidence and
# HORIZON_NOTE links to emitted evidence; neither is an evidence-free rule.
# R00 is request validation and never produces a Recommendation.
NO_EVIDENCE_RULE_IDS = frozenset(
    {
        "R01_NO_COVERAGE",
        "R08_INDETERMINATE",
    }
)

_ORIGIN_REGISTRY = CityRegistry()


def _origin_local_today(origin: str | None) -> date:
    """Return the departure airport's local calendar date at validation time.

    The origin is resolved here (before ``AssessmentService.assess``) so the
    date bound uses the airport's IANA timezone. If the origin is unmapped or
    its zone is unavailable, a conservative UTC "today" is used; the service
    still reports ``UNMAPPED_CITY`` for unmapped queries.
    """
    instant = datetime.now(timezone.utc)
    if not origin:
        return instant.date()
    try:
        airport = _ORIGIN_REGISTRY.resolve(origin)
    except CityLookupError:
        return instant.date()
    try:
        return instant.astimezone(ZoneInfo(airport.timezone)).date()
    except ZoneInfoNotFoundError:
        return instant.date()


def _utc_iso(value: datetime | None) -> str | None:
    """Serialize a UTC datetime as ISO 8601 with a trailing Z."""
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")


class AssessRequest(BaseModel):
    """Incoming assessment request.

    ``date`` is the origin airport's local calendar date in ISO YYYY-MM-DD form.
    It must not precede that airport's local today (R00 validation). There is
    deliberately no hard maximum horizon: the disclosed forecast limits are
    advisory and the engine returns INDETERMINATE with a coverage note instead
    of rejecting a far-future date.
    """

    model_config = ConfigDict(extra="forbid")

    origin: str = Field(min_length=2, max_length=64)
    destination: str = Field(min_length=2, max_length=64)
    date: date
    departure_time: str | None = None

    @field_validator("date")
    @classmethod
    def _reject_past_date(cls, value: date, info: ValidationInfo) -> date:
        """Reject dates before the departure airport's local calendar today."""
        origin_value = info.data.get("origin")
        origin = origin_value if isinstance(origin_value, str) else None
        today = _origin_local_today(origin)
        if value < today:
            raise ValueError(
                f"Travel date {value.isoformat()} is before the departure airport's "
                f"local today ({today.isoformat()})."
            )
        return value


class Evidence(BaseModel):
    """One normalized, explainable provider signal."""

    model_config = ConfigDict(extra="forbid")

    id: str
    provider: ProviderName
    signal_type: SignalType
    signal: str
    severity: Severity
    reliability: Reliability
    geography: Geography
    temporal_overlap: TemporalOverlap
    freshness: Freshness
    observed_at: datetime | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    relevance_reason: str
    source_url: str
    raw_excerpt: str = Field(max_length=240)
    # Optional geographic anchor derived from the curated airport registry.
    # It exists so the UI can place a signal on the route map without inventing
    # coordinates. Absent means no location could be attributed.
    location_label: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    @field_serializer("observed_at", "valid_from", "valid_to", when_used="json")
    def _serialize_instant(self, value: datetime | None, _info: Any) -> str | None:
        return _utc_iso(value)


class ProviderStatus(BaseModel):
    """Outcome of one provider adapter call, including partial failures."""

    model_config = ConfigDict(extra="forbid")

    provider: ProviderName
    status: Literal["OK", "DEGRADED", "FAILED"]
    http_status: int | None = None
    latency_ms: int | None = None
    fetched_at: datetime | None = None
    evidence_count: int = 0
    error: str | None = None
    note: str = ""
    authoritative_url: str

    @field_serializer("fetched_at", when_used="json")
    def _serialize_fetched_at(self, value: datetime | None, _info: Any) -> str | None:
        return _utc_iso(value)


class RuleHit(BaseModel):
    """A decision-table rule that fired, with the evidence that triggered it."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str
    description: str
    evidence_ids: list[str] = Field(default_factory=list)


class Recommendation(BaseModel):
    """A rule-derived action linked back to evidence where applicable."""

    model_config = ConfigDict(extra="forbid")

    priority: Literal["IMMEDIATE", "HIGH", "ROUTINE"]
    action: str
    rationale: str
    rule_id: str
    evidence_ids: list[str] = Field(default_factory=list)


class Assessment(BaseModel):
    """Complete API response for one route/date assessment."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    generated_at: datetime
    route: dict[str, str]
    travel_date: date
    travel_window_utc: dict[str, datetime]
    classification: Classification
    confidence: Confidence
    degraded: bool
    assumptions: list[str]
    triggered_rules: list[RuleHit]
    evidence: list[Evidence]
    recommendations: list[Recommendation]
    provider_status: list[ProviderStatus]
    coverage_note: str

    @field_serializer("generated_at", when_used="json")
    def _serialize_generated_at(self, value: datetime, _info: Any) -> str:
        return _utc_iso(value) or ""

    @field_serializer("travel_window_utc", when_used="json")
    def _serialize_window(self, value: dict[str, datetime], _info: Any) -> dict[str, str]:
        return {key: _utc_iso(instant) or "" for key, instant in value.items()}

    @model_validator(mode="after")
    def check_invariants(self) -> "Assessment":
        """Enforce explainability and provider-status invariants."""
        evidence_ids = {item.id for item in self.evidence}
        if self.classification != "CLEAR" and not self.recommendations:
            raise ValueError("Non-CLEAR classifications require a recommendation")
        for recommendation in self.recommendations:
            if recommendation.rule_id in NO_EVIDENCE_RULE_IDS:
                continue
            if not recommendation.evidence_ids:
                raise ValueError("Evidence-linked recommendation has no evidence IDs")
            if not set(recommendation.evidence_ids).issubset(evidence_ids):
                raise ValueError("Recommendation references unknown evidence ID")
        expected_degraded = any(p.status != "OK" for p in self.provider_status)
        if self.degraded != expected_degraded:
            raise ValueError("degraded must match provider status")
        if len(self.provider_status) != 2:
            raise ValueError("Exactly two provider statuses are required")
        return self


class ErrorEnvelope(BaseModel):
    """Uniform shape for all non-2xx responses."""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    request_id: str
    details: dict[str, Any] | None = None

    @field_serializer("details", when_used="json")
    def _serialize_details(self, value: dict[str, Any] | None, _info: Any) -> dict[str, Any] | None:
        return value
