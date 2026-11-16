"""Case-insensitive city/IATA lookup over the curated airport registry.

Only airports present in ``airports.json`` can be resolved. No geocoding, no
schedule lookup and no guessing of airports is performed.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

AIRPORTS_PATH = Path(__file__).with_name("airports.json")

# Convenience aliases. Every alias maps to an existing curated airport only.
ALIASES: dict[str, str] = {
    "nyc": "JFK",
    "ny": "JFK",
    "new york city": "JFK",
    "jfk airport": "JFK",
    "sf": "SFO",
    "sf bay": "SFO",
    "bay area": "SFO",
    "san francisco bay": "SFO",
    "dc": "IAD",
    "washington dc": "IAD",
    "dulles": "IAD",
    "reagan": "DCA",
    "nola": "MSY",
    "vegas": "LAS",
    "big apple": "JFK",
}


class CityLookupError(Exception):
    """Raised when a caller supplies a city/IATA outside the curated registry."""

    code = "UNMAPPED_CITY"

    def __init__(self, query: str) -> None:
        self.query = query
        super().__init__(
            f"'{query}' is not a mapped US airport/city. "
            "Use a curated city name or IATA code from the form."
        )


@dataclass(frozen=True)
class Airport:
    """One curated airport with verified IATA/ICAO pair and coordinates."""

    city: str
    state: str
    country: str
    region: str
    iata: str
    icao: str
    lat: float
    lon: float
    nws_point: str
    timezone: str

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "Airport":
        """Construct an Airport from one JSON registry record."""
        return cls(
            city=str(record["city"]),
            state=str(record["state"]),
            country=str(record.get("country", "United States")),
            region=str(record.get("region", "North America")),
            iata=str(record["iata"]).upper(),
            icao=str(record["icao"]).upper(),
            lat=float(record["lat"]),
            lon=float(record["lon"]),
            nws_point=str(record["nws_point"]),
            timezone=str(record["timezone"]),
        )

    def display_name(self) -> str:
        """Return a short human-readable label."""
        return f"{self.city} ({self.iata})"


class CityRegistry:
    """Deterministic registry backed by the static JSON file."""

    def __init__(self, path: Path | None = None) -> None:
        source = path or AIRPORTS_PATH
        with source.open("r", encoding="utf-8") as handle:
            records: list[dict[str, Any]] = json.load(handle)
        self._airports: list[Airport] = [Airport.from_record(record) for record in records]
        self._by_iata: dict[str, Airport] = {
            airport.iata: airport for airport in self._airports
        }
        self._by_icao: dict[str, Airport] = {
            airport.icao: airport for airport in self._airports
        }

    def all(self) -> list[Airport]:
        """Return all curated airports in stable file order."""
        return list(self._airports)

    def resolve(self, query: str) -> Airport:
        """Resolve a city name or IATA code, case-insensitively.

        Args:
            query: User-supplied city name, IATA code or documented alias.

        Raises:
            CityLookupError: If the query is blank or not in the registry.
        """
        if not isinstance(query, str):
            raise CityLookupError(str(query))
        key = re.sub(r"\s+", " ", query.strip()).lower()
        # The autocomplete offers labels such as "Salt Lake City (SLC)".
        # Accept that exact label as well as the bare city and code forms so a
        # selection from the UI can never be rejected by the API.
        key = re.sub(r"\s*\([^()]*\)\s*$", "", key).strip()
        if not key:
            raise CityLookupError(query)
        key = ALIASES.get(key, key)
        airport = self._by_iata.get(key.upper()) or self._by_icao.get(key.upper())
        if airport is not None:
            return airport
        for candidate in self._airports:
            if candidate.city.lower() == key:
                return candidate
        raise CityLookupError(query)
