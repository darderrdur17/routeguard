"""All 12 architecture scenarios plus determinism and integrity assertions."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from app.models import Assessment, Evidence
from app.risk import classify
from tests.conftest import NOW, make_evidence, make_status, make_window

WINDOW = make_window(NOW + timedelta(hours=1), NOW + timedelta(hours=25))
TRAVEL_DATE = date(2026, 11, 17)
BOTH_OK = lambda: [make_status("NWS"), make_status("AWC")]  # noqa: E731


def ev(
    index: int,
    provider: str,
    severity: str,
    reliability: str = "HIGH",
    geography: str = "EXACT",
    overlap: str = "FULL",
    freshness: str = "FRESH",
) -> Evidence:
    """Short-hand builder for decision-table evidence."""
    return make_evidence(
        index, provider, severity, reliability, geography, overlap, freshness
    )


SCENARIOS: list[tuple[str, list[Evidence], list[Any], str, list[str], str, bool]] = [
    (
        "S01",
        [ev(0, "NWS", "EXTREME"), ev(1, "AWC", "MODERATE", "MEDIUM", overlap="PARTIAL")],
        BOTH_OK(),
        "CRITICAL",
        ["R03_CRITICAL"],
        "HIGH",
        False,
    ),
    (
        "S02",
        [ev(0, "NWS", "EXTREME")],
        [make_status("NWS"), make_status("AWC", "FAILED", error="HTTPError(status=500)")],
        "HIGH",
        ["R04_HIGH"],
        "MEDIUM",
        True,
    ),
    (
        "S03",
        [ev(0, "NWS", "SEVERE"), ev(1, "AWC", "SEVERE", overlap="PARTIAL")],
        BOTH_OK(),
        "HIGH",
        ["R04_HIGH"],
        "HIGH",
        False,
    ),
    (
        "S04",
        [ev(0, "NWS", "SEVERE")],
        BOTH_OK(),
        "HIGH",
        ["R04_HIGH"],
        "MEDIUM",
        False,
    ),
    (
        "S05",
        [ev(0, "NWS", "MODERATE")],
        BOTH_OK(),
        "ELEVATED",
        ["R05_ELEVATED"],
        "MEDIUM",
        False,
    ),
    (
        "S06",
        [
            ev(0, "NWS", "MODERATE", "MEDIUM", overlap="PARTIAL"),
            ev(1, "AWC", "MODERATE", "MEDIUM", overlap="PARTIAL"),
        ],
        BOTH_OK(),
        "ELEVATED",
        ["R05_ELEVATED"],
        "MEDIUM",
        False,
    ),
    (
        "S07",
        [ev(0, "AWC", "MODERATE", "MEDIUM", overlap="PARTIAL")],
        BOTH_OK(),
        "LOW",
        ["R06_LOW"],
        "MEDIUM",
        False,
    ),
    (
        "S08",
        [ev(0, "NWS", "MINOR"), ev(1, "AWC", "MINOR", overlap="PARTIAL")],
        BOTH_OK(),
        "CLEAR",
        ["R07_CLEAR"],
        "HIGH",
        False,
    ),
    (
        "S09",
        [],
        BOTH_OK(),
        "INDETERMINATE",
        ["R01_NO_COVERAGE"],
        "LOW",
        False,
    ),
    (
        "S10",
        [ev(0, "NWS", "MINOR")],
        [make_status("NWS"), make_status("AWC", "FAILED", error="HTTPError(status=500)")],
        "INDETERMINATE",
        ["R08_INDETERMINATE"],
        "MEDIUM",
        True,
    ),
    (
        "S11",
        [ev(0, "NWS", "EXTREME", freshness="STALE")],
        BOTH_OK(),
        "ELEVATED",
        ["R02_UNVERIFIED_GUARD", "R05_ELEVATED"],
        "MEDIUM",
        False,
    ),
    (
        "S12",
        [
            ev(0, "NWS", "EXTREME", "LOW"),
            ev(1, "AWC", "MODERATE", "MEDIUM", overlap="PARTIAL"),
        ],
        BOTH_OK(),
        "ELEVATED",
        ["R02_UNVERIFIED_GUARD", "R05_ELEVATED"],
        "LOW",
        False,
    ),
]


@pytest.mark.parametrize(
    "evidence,statuses,expected_class,expected_rules,expected_confidence,expected_degraded",
    [scenario[1:] for scenario in SCENARIOS],
    ids=[scenario[0] for scenario in SCENARIOS],
)
def test_all_twelve_scenarios(
    evidence: list[Evidence],
    statuses: list[Any],
    expected_class: str,
    expected_rules: list[str],
    expected_confidence: str,
    expected_degraded: bool,
) -> None:
    """Each recorded scenario yields the documented class, rules and confidence."""
    result = classify(evidence, statuses, TRAVEL_DATE, NOW, WINDOW)
    assert result.classification == expected_class
    assert result.rule_ids == expected_rules
    assert result.confidence == expected_confidence
    assert any(status.status != "OK" for status in statuses) == expected_degraded
    assert len(result.recommendations) >= 1


def test_determinism_byte_identical_summary() -> None:
    """The same evidence produces identical class/confidence/rule IDs."""
    scenario = SCENARIOS[0]
    first = classify(scenario[1], scenario[2], TRAVEL_DATE, NOW, WINDOW)
    second = classify(scenario[1], scenario[2], TRAVEL_DATE, NOW, WINDOW)
    assert (first.classification, first.confidence, first.rule_ids) == (
        second.classification,
        second.confidence,
        second.rule_ids,
    )
    assert asdict(first) == asdict(second)


def test_no_score_fields_anywhere_in_response() -> None:
    """No numeric score, risk_score or probability field is emitted."""
    scenario = SCENARIOS[0]
    result = classify(scenario[1], scenario[2], TRAVEL_DATE, NOW, WINDOW)
    assessment = Assessment(
        request_id="test",
        generated_at=NOW,
        route={"origin_iata": "JFK", "destination_iata": "SFO"},
        travel_date=TRAVEL_DATE,
        travel_window_utc=WINDOW,
        classification=result.classification,
        confidence=result.confidence,
        degraded=False,
        assumptions=[],
        triggered_rules=result.triggered_rules,
        evidence=scenario[1],
        recommendations=result.recommendations,
        provider_status=scenario[2],
        coverage_note="test",
    )
    payload = assessment.model_dump(mode="json")

    def keys(value: Any) -> set[str]:
        found: set[str] = set()
        if isinstance(value, dict):
            for key, nested in value.items():
                found.add(str(key))
                found |= keys(nested)
        elif isinstance(value, list):
            for nested in value:
                found |= keys(nested)
        return found

    all_keys = keys(payload)
    assert "score" not in all_keys
    assert "risk_score" not in all_keys
    assert "probability" not in all_keys


@pytest.mark.parametrize(
    "evidence,statuses,_expected_class,rule_ids,_confidence,_degraded",
    [scenario[1:] for scenario in SCENARIOS if scenario[0] != "S09"],
    ids=[scenario[0] for scenario in SCENARIOS if scenario[0] != "S09"],
)
def test_recommendations_are_evidence_linked(
    evidence: list[Evidence],
    statuses: list[Any],
    _expected_class: str,
    rule_ids: list[str],
    _confidence: str,
    _degraded: bool,
) -> None:
    """Non-CLEAR results have ≥1 recommendation with valid evidence IDs,
    except the terminal coverage rules R01/R08 which carry none."""
    result = classify(evidence, statuses, TRAVEL_DATE, NOW, WINDOW)
    emitted = {item.id for item in evidence}
    if rule_ids[0] in {"R01_NO_COVERAGE", "R08_INDETERMINATE"}:
        return
    linked = [
        recommendation
        for recommendation in result.recommendations
        if recommendation.evidence_ids
        and set(recommendation.evidence_ids).issubset(emitted)
    ]
    assert linked


def test_r01_does_not_imply_low_risk() -> None:
    """No-coverage outcomes never reassure the user with LOW risk language."""
    result = classify([], BOTH_OK(), TRAVEL_DATE, NOW, WINDOW)
    assert result.classification == "INDETERMINATE"
    for recommendation in result.recommendations:
        text = (recommendation.action + " " + recommendation.rationale).lower()
        assert "low" not in text


def test_unverified_extreme_never_becomes_critical() -> None:
    """R02 marks unverified extremes and caps them at ELEVATED."""
    result = classify([ev(0, "NWS", "EXTREME", freshness="STALE")], BOTH_OK(), TRAVEL_DATE, NOW, WINDOW)
    assert "R02_UNVERIFIED_GUARD" in result.rule_ids
    assert result.classification != "CRITICAL"
    assert result.classification == "ELEVATED"


def _assessment_with_recommendation(
    rule_id: str, evidence_ids: list[str], classification: str = "HIGH"
) -> Assessment:
    """Build an Assessment carrying exactly one recommendation."""
    return Assessment(
        request_id="test",
        generated_at=NOW,
        route={},
        travel_date=TRAVEL_DATE,
        travel_window_utc=WINDOW,
        classification=classification,  # type: ignore[arg-type]
        confidence="MEDIUM",
        degraded=False,
        assumptions=[],
        triggered_rules=[],
        evidence=[],
        recommendations=[
            {
                "priority": "HIGH",
                "action": "act",
                "rationale": "why",
                "rule_id": rule_id,
                "evidence_ids": evidence_ids,
            }
        ],
        provider_status=BOTH_OK(),
        coverage_note="test",
    )


@pytest.mark.parametrize(
    "rule_id", ["R04_HIGH", "C03_MEDIUM_PARTIAL", "HORIZON_NOTE"]
)
def test_assessment_rejects_unlinked_recommendation(rule_id: str) -> None:
    """Unknown evidence IDs are rejected for every non-exempt rule."""
    with pytest.raises(ValidationError):
        _assessment_with_recommendation(rule_id, ["not-present"])


@pytest.mark.parametrize(
    "rule_id", ["R04_HIGH", "C03_MEDIUM_PARTIAL", "HORIZON_NOTE"]
)
def test_assessment_rejects_empty_evidence_ids_outside_no_coverage(
    rule_id: str,
) -> None:
    """Only R01/R08 no-coverage outcomes may omit evidence IDs."""
    with pytest.raises(ValidationError, match="no evidence IDs"):
        _assessment_with_recommendation(rule_id, [])


@pytest.mark.parametrize("rule_id", ["R01_NO_COVERAGE", "R08_INDETERMINATE"])
def test_no_coverage_recommendations_may_omit_evidence_ids(rule_id: str) -> None:
    """Runtime no-coverage recommendations remain valid with empty IDs."""
    assessment = _assessment_with_recommendation(
        rule_id, [], classification="INDETERMINATE"
    )
    assert assessment.recommendations[0].evidence_ids == []


def test_partial_failure_does_not_suppress_supported_class() -> None:
    """A failed provider caps confidence but does not erase HIGH evidence."""
    statuses = [
        make_status("NWS"),
        make_status("AWC", "FAILED", error="HTTPError(status=500)"),
    ]
    result = classify([ev(0, "NWS", "SEVERE")], statuses, TRAVEL_DATE, NOW, WINDOW)
    assert result.classification == "HIGH"
    assert result.confidence == "MEDIUM"
    assert "C03_MEDIUM_PARTIAL" in result.confidence_ids
    assert any(rec.rule_id == "C03_MEDIUM_PARTIAL" for rec in result.recommendations)
