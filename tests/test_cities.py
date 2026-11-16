"""City/IATA registry tests — no external geocoding or schedule lookups."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.cities import CityLookupError, CityRegistry


@pytest.fixture(scope="module")
def registry() -> CityRegistry:
    """Shared registry for lookup tests."""
    return CityRegistry()


def test_required_airports_present(registry: CityRegistry) -> None:
    """JFK/KJFK and SFO/KSFO are required by the brief."""
    jfk = registry.resolve("JFK")
    sfo = registry.resolve("SFO")
    assert (jfk.iata, jfk.icao, jfk.city) == ("JFK", "KJFK", "New York")
    assert (sfo.iata, sfo.icao, sfo.city) == ("SFO", "KSFO", "San Francisco")


def test_case_insensitive_iata_and_city(registry: CityRegistry) -> None:
    """IATA codes and city names resolve regardless of case and spacing."""
    assert registry.resolve("jfk").iata == "JFK"
    assert registry.resolve("  SAN FRANCISCO  ").iata == "SFO"
    assert registry.resolve("new york").iata == "JFK"


def test_autocomplete_labels_and_icao_codes_resolve(registry: CityRegistry) -> None:
    """The exact labels offered by the UI must be accepted by the API."""
    assert registry.resolve("Salt Lake City (SLC)").iata == "SLC"
    assert registry.resolve("New York (JFK)").iata == "JFK"
    assert registry.resolve("Salt Lake City ( SLC )").iata == "SLC"
    assert registry.resolve("KSLC").iata == "SLC"


def test_aliases_resolve_to_curated_airports(registry: CityRegistry) -> None:
    """Documented aliases map only to existing registry entries."""
    assert registry.resolve("NYC").iata == "JFK"
    assert registry.resolve("sf").iata == "SFO"
    assert registry.resolve("Dulles").iata == "IAD"


def test_city_with_multiple_airports_is_deterministic(registry: CityRegistry) -> None:
    """A city with two airports resolves to the first registry entry."""
    first = registry.resolve("New York")
    second = registry.resolve("New York")
    assert first.iata == second.iata == "JFK"
    assert registry.resolve("LGA").iata == "LGA"


def test_unmapped_input_raises_clear_error(registry: CityRegistry) -> None:
    """Unmapped or blank input never guesses an airport."""
    with pytest.raises(CityLookupError) as unknown:
        registry.resolve("Atlantis")
    assert unknown.value.code == "UNMAPPED_CITY"
    with pytest.raises(CityLookupError):
        registry.resolve("   ")


def test_registry_has_full_realistic_coverage(registry: CityRegistry) -> None:
    """The curated set is stable, unique and plausibly real."""
    airports = registry.all()
    assert len(airports) >= 75
    assert len({airport.iata for airport in airports}) == len(airports)
    assert len({airport.icao for airport in airports}) == len(airports)
    assert len({airport.country for airport in airports}) >= 20
    known_pairs = {
        "JFK": "KJFK",
        "SFO": "KSFO",
        "LAX": "KLAX",
        "ORD": "KORD",
        "ATL": "KATL",
        "SEA": "KSEA",
        "HNL": "PHNL",
        "SIN": "WSSS",
        "LHR": "EGLL",
        "HKG": "VHHH",
    }
    by_iata = {airport.iata: airport.icao for airport in airports}
    for iata, icao in known_pairs.items():
        assert by_iata[iata] == icao


def test_country_and_region_are_declared(registry: CityRegistry) -> None:
    """Current US focus and global extension are both explicit in the data."""
    assert registry.resolve("JFK").country == "United States"
    assert registry.resolve("SIN").country == "Singapore"
    assert registry.resolve("HKG").country == "Hong Kong, China"
    assert {a.country for a in registry.all() if a.iata == "SIN"} == {"Singapore"}


def test_nws_points_and_timezones_are_valid(registry: CityRegistry) -> None:
    """NWS points are <=4 decimals and every timezone is a real IANA zone."""
    for airport in registry.all():
        assert airport.nws_point == f"{airport.lat:.4f},{airport.lon:.4f}"
        assert -90.0 <= airport.lat <= 90.0
        assert -180.0 <= airport.lon <= 180.0
        assert ZoneInfo(airport.timezone)
        assert datetime.now(ZoneInfo(airport.timezone)).tzinfo is not None
