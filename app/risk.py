"""Deterministic, explainable risk engine.

Risk (``classification``) and confidence are separate axes. There is no
numerical score. Rules are evaluated in the exact order of
docs/01_architecture.md section 8: R00 is request validation (main.py), R01 is
the first terminal engine rule, R02 is a non-terminal marker, and R03..R08 are
terminal in that order. C01..C05 are confidence rules applied afterwards.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from app.models import (
    Classification,
    Confidence,
    Evidence,
    ProviderStatus,
    Recommendation,
    RuleHit,
)

SEVERITY_RANK: dict[str, int] = {
    "UNKNOWN": 0,
    "MINOR": 1,
    "MODERATE": 2,
    "SEVERE": 3,
    "EXTREME": 4,
}
CONFIDENCE_RANK: dict[str, int] = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}

RULE_DESCRIPTIONS: dict[str, str] = {
    "R01_NO_COVERAGE": "No eligible trustworthy evidence, or all providers failed.",
    "R02_UNVERIFIED_GUARD": "Unverified extreme evidence present; CRITICAL is forbidden.",
    "R03_CRITICAL": "Trustworthy extreme evidence corroborated by both providers.",
    "R04_HIGH": "Trustworthy extreme or high-reliability severe evidence present.",
    "R05_ELEVATED": "Trustworthy moderate or downgraded moderate-or-higher evidence present.",
    "R06_LOW": "Limited moderate evidence or corroborated minor evidence present.",
    "R07_CLEAR": "Both providers healthy, minor-or-less trustworthy evidence from each.",
    "R08_INDETERMINATE": "No other rule applies; coverage is inconclusive.",
}

RECOMMENDATION_TEMPLATES: dict[str, str] = {
    "R03_CRITICAL": (
        "Do not travel if alternatives exist; rebook or defer and contact the airline. "
        "Evidence: {ids}."
    ),
    "R04_HIGH": (
        "Check rebooking options now and allow extra connection time; re-check source "
        "alerts and airline status before leaving. Evidence: {ids}."
    ),
    "R05_ELEVATED": (
        "Monitor the flagged signal, confirm airline status, and keep a backup plan. "
        "Evidence: {ids}."
    ),
    "R06_LOW": "Routine monitoring; re-check on the day of departure. Evidence: {ids}.",
    "R07_CLEAR": "No RouteGuard action beyond normal pre-flight checks. Evidence: {ids}.",
}

NO_COVERAGE_ACTION = (
    "No conclusive coverage for this date; check the relevant national aviation "
    "authority (external link) and the airline, then retry closer to departure."
)


@dataclass
class RiskResult:
    """Output of one deterministic classification run."""

    classification: Classification
    confidence: Confidence
    triggered_rules: list[RuleHit] = field(default_factory=list)
    recommendations: list[Recommendation] = field(default_factory=list)
    confidence_ids: list[str] = field(default_factory=list)

    @property
    def rule_ids(self) -> list[str]:
        """Return triggered rule IDs in evaluation order."""
        return [item.rule_id for item in self.triggered_rules]


def _ids(items: list[Evidence]) -> list[str]:
    """Return evidence IDs in stable order."""
    return [item.id for item in items]


def _status_map(provider_status: list[ProviderStatus]) -> dict[str, str]:
    """Build a provider-name to status map."""
    return {item.provider: item.status for item in provider_status}


def classify(
    evidence: list[Evidence],
    provider_status: list[ProviderStatus],
    travel_date: date,
    generated_at: datetime,
    window: dict[str, datetime],
) -> RiskResult:
    """Apply the decision table and confidence rules to normalized evidence.

    Args:
        evidence: All evidence, including items excluded by eligibility rules.
        provider_status: Exactly one status per provider (NWS, AWC).
        travel_date: Departure-airport local travel date.
        generated_at: UTC generation instant used for the 48 h confidence test.
        window: UTC travel window with ``start`` and ``end`` keys.

    Returns:
        RiskResult with classification, independent confidence, rule hits and
        evidence-linked recommendations.
    """
    _ = travel_date
    statuses = _status_map(provider_status)
    # Provider-agnostic: US routes use NWS + AWC, international routes use
    # OPEN_METEO + AWC. The decision table must not depend on fixed names.
    provider_names = set(statuses)
    all_ok = bool(provider_names) and all(value == "OK" for value in statuses.values())
    all_failed = bool(provider_names) and all(
        value == "FAILED" for value in statuses.values()
    )

    core = [
        item
        for item in evidence
        if item.severity != "UNKNOWN"
        and item.geography in {"EXACT", "NEAR"}
        and item.temporal_overlap in {"FULL", "PARTIAL"}
    ]
    trustworthy = [
        item
        for item in core
        if item.reliability in {"HIGH", "MEDIUM"} and item.freshness == "FRESH"
    ]
    downgraded = [
        item for item in core if item.freshness == "STALE" or item.reliability == "LOW"
    ]
    corroboration = len(
        {
            item.provider
            for item in trustworthy
            if SEVERITY_RANK[item.severity] >= SEVERITY_RANK["MODERATE"]
        }
    )

    triggered: list[RuleHit] = []

    def add_hit(rule_id: str, matched: list[Evidence]) -> None:
        """Record a rule hit with the evidence that justified it."""
        triggered.append(
            RuleHit(
                rule_id=rule_id,
                description=RULE_DESCRIPTIONS[rule_id],
                evidence_ids=_ids(matched),
            )
        )

    # "Eligible set" for R01 is the geography/overlap/time eligible core: a
    # downgraded-but-relevant signal must be able to reach R02/R05 (S11).
    if not core or all_failed:
        add_hit("R01_NO_COVERAGE", [])
        classification: Classification = "INDETERMINATE"
        terminal_rule = "R01_NO_COVERAGE"
        terminal_evidence: list[Evidence] = []
    else:
        extreme = [item for item in trustworthy if item.severity == "EXTREME"]
        severe = [item for item in trustworthy if item.severity == "SEVERE"]
        moderate = [item for item in trustworthy if item.severity == "MODERATE"]
        downgraded_extreme = [item for item in downgraded if item.severity == "EXTREME"]
        downgraded_moderate_plus = [
            item for item in downgraded if SEVERITY_RANK[item.severity] >= 2
        ]

        if downgraded_extreme:
            add_hit("R02_UNVERIFIED_GUARD", downgraded_extreme)

        if extreme and corroboration >= 2:
            add_hit("R03_CRITICAL", extreme)
            classification = "CRITICAL"
            terminal_rule = "R03_CRITICAL"
            terminal_evidence = extreme
        elif extreme or (
            severe and (corroboration >= 2 or any(i.reliability == "HIGH" for i in severe))
        ):
            matched = extreme or severe
            add_hit("R04_HIGH", matched)
            classification = "HIGH"
            terminal_rule = "R04_HIGH"
            terminal_evidence = matched
        else:
            elevated_moderate = [
                item
                for item in moderate
                if corroboration >= 2 or item.reliability == "HIGH"
            ]
            if elevated_moderate or downgraded_moderate_plus:
                add_hit("R05_ELEVATED", elevated_moderate + downgraded_moderate_plus)
                classification = "ELEVATED"
                terminal_rule = "R05_ELEVATED"
                terminal_evidence = elevated_moderate + downgraded_moderate_plus
            else:
                low_moderate = [
                    item
                    for item in moderate
                    if item.reliability == "MEDIUM" and corroboration < 2
                ]
                downgraded_moderate = [
                    item for item in downgraded if item.severity == "MODERATE"
                ]
                minor = [item for item in trustworthy if item.severity == "MINOR"]
                if low_moderate or downgraded_moderate or (minor and corroboration >= 2):
                    matched = low_moderate + downgraded_moderate
                    if minor and corroboration >= 2:
                        matched = matched + minor
                    add_hit("R06_LOW", matched)
                    classification = "LOW"
                    terminal_rule = "R06_LOW"
                    terminal_evidence = matched
                elif (
                    all_ok
                    and {item.provider for item in trustworthy} == provider_names
                    and all(SEVERITY_RANK[item.severity] <= 1 for item in trustworthy)
                ):
                    add_hit("R07_CLEAR", trustworthy)
                    classification = "CLEAR"
                    terminal_rule = "R07_CLEAR"
                    terminal_evidence = trustworthy
                else:
                    add_hit("R08_INDETERMINATE", [])
                    classification = "INDETERMINATE"
                    terminal_rule = "R08_INDETERMINATE"
                    terminal_evidence = []

    # ---- Confidence (independent axis, computed after classification) -------
    hours_to_travel = (window["start"] - generated_at).total_seconds() / 3600.0
    trustworthy_providers = {item.provider for item in trustworthy}
    non_ok_providers = [p for p in provider_status if p.status != "OK"]
    candidate_confidences: list[tuple[str, str]] = []

    # C01 additionally requires at least one HIGH-reliability trustworthy item,
    # which is the reading consistent with scenario S06 (two MEDIUM-reliability
    # corroborators classify ELEVATED but cap confidence at MEDIUM).
    high_reliability_trustworthy = any(
        item.reliability == "HIGH" for item in trustworthy
    )
    if (
        all_ok
        and len(trustworthy) >= 2
        and trustworthy_providers == provider_names
        and hours_to_travel <= 48
        and high_reliability_trustworthy
    ):
        candidate_confidences.append(("C01_HIGH", "HIGH"))
    if all_ok and (
        trustworthy_providers != provider_names
        or hours_to_travel > 48
        or not high_reliability_trustworthy
    ):
        candidate_confidences.append(("C02_MEDIUM_SINGLE", "MEDIUM"))
    if len(non_ok_providers) == 1 and trustworthy_providers:
        candidate_confidences.append(("C03_MEDIUM_PARTIAL", "MEDIUM"))
    if (
        all_failed
        or not core
        or any(item.reliability == "LOW" for item in downgraded)
    ):
        candidate_confidences.append(("C04_LOW", "LOW"))
    stale_core = [item for item in core if item.freshness == "STALE"]
    if stale_core:
        candidate_confidences.append(("C05_CAP_STALE", "MEDIUM"))

    confidence_ids = [rule_id for rule_id, _value in candidate_confidences]
    if candidate_confidences:
        confidence: Confidence = min(  # type: ignore[assignment]
            (value for _rule_id, value in candidate_confidences),
            key=lambda value: CONFIDENCE_RANK[value],
        )
    else:
        confidence = "LOW"

    # ---- Rule-derived, evidence-linked recommendations ---------------------
    recommendations: list[Recommendation] = []
    if terminal_rule in RECOMMENDATION_TEMPLATES:
        linked_ids = _ids(terminal_evidence)
        action = RECOMMENDATION_TEMPLATES[terminal_rule].format(
            ids=", ".join(linked_ids) if linked_ids else "none"
        )
        priority: str = (
            "IMMEDIATE"
            if terminal_rule in {"R03_CRITICAL", "R04_HIGH"}
            else "HIGH"
            if terminal_rule == "R05_ELEVATED"
            else "ROUTINE"
        )
        recommendations.append(
            Recommendation(
                priority=priority,  # type: ignore[arg-type]
                action=action,
                rationale=(
                    f"Decision rule {terminal_rule} matched: "
                    f"{RULE_DESCRIPTIONS[terminal_rule]}"
                ),
                rule_id=terminal_rule,
                evidence_ids=linked_ids,
            )
        )
    else:
        no_coverage_rationale = (
            "No eligible trustworthy evidence or both providers failed; coverage is "
            "inconclusive and absence of findings is not reassurance."
        )
        recommendations.append(
            Recommendation(
                priority="HIGH",
                action=NO_COVERAGE_ACTION,
                rationale=no_coverage_rationale,
                rule_id=terminal_rule,
                evidence_ids=[],
            )
        )

    if any(rule_id == "C03_MEDIUM_PARTIAL" for rule_id in confidence_ids):
        for provider in non_ok_providers:
            surviving_ids = [
                item.id for item in trustworthy if item.provider != provider.provider
            ]
            recommendations.append(
                Recommendation(
                    priority="HIGH",
                    action=(
                        f"{provider.provider} unavailable; verify directly at "
                        f"{provider.authoritative_url}."
                    ),
                    rationale=(
                        f"Provider status {provider.status}: "
                        f"{provider.error or provider.note or 'no detail'}"
                    ),
                    rule_id="C03_MEDIUM_PARTIAL",
                    evidence_ids=surviving_ids,
                )
            )

    if stale_core:
        recommendations.append(
            Recommendation(
                priority="HIGH",
                action="Evidence is stale; treat this assessment as indicative and refresh.",
                rationale="At least one classified evidence item exceeds its freshness threshold.",
                rule_id="C05_CAP_STALE",
                evidence_ids=_ids(stale_core),
            )
        )

    if hours_to_travel > 7 * 24:
        # The horizon note is informational, not an evidence-free rule: it must
        # cite an emitted evidence item. When nothing was emitted at all, the
        # standing coverage_note already discloses the same horizon, so no
        # unlinkable recommendation is added.
        note_ids = _ids(terminal_evidence) or _ids(evidence)
        if note_ids:
            recommendations.append(
                Recommendation(
                    priority="ROUTINE",
                    action=(
                        "Weather forecast horizons are limited (gridpoint ~7 days, "
                        "Open-Meteo ~2 days, TAF ~30 h); this date is beyond a "
                        "reliable outlook — recheck later."
                    ),
                    rationale="Travel date exceeds the disclosed forward forecast horizon.",
                    rule_id="HORIZON_NOTE",
                    evidence_ids=note_ids,
                )
            )

    return RiskResult(
        classification=classification,
        confidence=confidence,
        triggered_rules=triggered,
        recommendations=recommendations,
        confidence_ids=confidence_ids,
    )
