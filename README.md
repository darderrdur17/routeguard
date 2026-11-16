# RouteGuard — prototype

RouteGuard is a local, evidence-driven prototype that gives one explainable view of
weather signals for a city-pair on a chosen travel date. It fetches genuine public
data from two independent providers through the backend, normalizes it into typed
evidence, applies a deterministic decision table, and shows the classification,
confidence, triggered rules, recommendations and provider status. There is no
numerical 0–100 score and no AI/LLM at runtime.

**Product assumption:** commercial air travel, airport-level, not a flight
itinerary. A city lookup resolves to one curated airport; no flight number, gate,
schedule, connection or aircraft route is invented. The date is the departure
airport's local calendar date. Because no departure time is used, the assessment
has whole-day precision, and destination evidence is evaluated against the same
UTC window (arrival-local date is not modelled).

**Current focus and global extension:** the original brief focused on the United
States. That remains the default: 48 curated US airports assessed with NWS + AWC.
The prototype now also covers 27 curated airports in 25 other countries/regions
(including Hong Kong, China), assessed with Open-Meteo + AWC. The route's cities,
countries and active providers are shown in the journey panel and a coverage
badge. See `docs/05_CONFIGURATION.md` for the exact key/environment requirements —
**no API key is required**.

## Run locally

From this directory:

```bash
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

Then open <http://127.0.0.1:8765/>. No build step, no frontend dependencies, no
API keys. `GET /api/health` returns `{"status":"ok"}`; `GET /api/airports` returns
the curated registry that backs the UI autocomplete; `POST /api/assess` accepts
`{"origin":"New York","destination":"San Francisco","date":"YYYY-MM-DD"}`.

### Interface

The frontend is a dependency-free single-page command centre. It renders a bento
dashboard with a journey summary, overall classification, schematic route map,
recommended actions, origin/destination intelligence, timestamped signal timeline,
evidence distribution, filterable evidence ledger and source coverage panel.

- The map is a schematic longitude/latitude projection with bounds recomputed per
  route, so both regional and intercontinental journeys render honestly. Signals
  inherit their airport's coordinates from the curated backend registry. The dashed
  connector links endpoints only — it is **not** an aircraft route or flight path.
- A failed submission now clears the previous result and shows the empty state; a
  stale assessment is never displayed beside a fresh error.
- Selecting a marker, timeline item or evidence card opens a contextual drawer with
  source, original excerpt, observation/validity/retrieval times, verification class,
  RouteGuard interpretation and journey relevance. Selections are cross-linked:
  map → evidence, airport card → map/filter, timeline → evidence.
- Evidence filters operate on retrieved signal types and freshness only. Airport
  operations and aviation advisories are labelled as not integrated; there are no
  decorative or non-functional controls.
- `⌘ K` / `Ctrl K` opens a working command palette (navigation, refresh, clear filters,
  and setting either airport from the curated registry). Palette hints show each
  airport's country. Refresh re-queries the sources and reports whether the
  classification changed.
- Loading is honest: the backend returns one aggregate response, so the UI shows a
  single "Contacting sources…" state with no simulated stages or percentages.
- Reduced-motion preferences, keyboard navigation, visible focus states and responsive
  desktop/tablet/mobile layouts are implemented.

## Test

```bash
python3 -m pytest -q
```

All tests are offline: provider behaviour is exercised with `httpx.MockTransport`.
No test makes a live network call. `tests/fixtures/` contains sanitised copies of
the recorded provider payload shapes documented in `docs/02_api_verification_notes.md`.
`tests/test_risk.py` implements every scenario (S01–S12) in `docs/01_architecture.md`
section 10 plus determinism, no-score and evidence-linkage assertions.

## Dependencies

`requirements.txt` declares compatible ranges that include both the architecture's
reference pins and the versions actually tested in this environment:

| Package | Tested version | Range |
|---|---|---|
| fastapi | 0.162.0 | `>=0.115.6,<1` |
| uvicorn | 0.54.0 | `>=0.34.0,<1` |
| httpx | 0.28.1 | `>=0.28.1,<1` |
| pydantic | 2.14.2 | `>=2.10.4,<3` |
| pytest | 9.2.0 | `>=8.3.4,<10` |

Python 3.11+ is required for `zoneinfo`. Tested with Python 3.13.12.

## Providers and real endpoints

All calls are backend-only, with an identifying
`User-Agent: RouteGuardPrototype/0.1 (contact: derren@example.com)`, a 10 s timeout
and at most two retries on 429/5xx. 204 is success-with-no-data.

| Provider | Endpoints | Evidence |
|---|---|---|
| National Weather Service (NWS) | `https://api.weather.gov/points/{lat},{lon}` → `https://api.weather.gov/alerts/active?point={lat},{lon}` and the `properties.forecast` URL read from the points response (template `https://api.weather.gov/gridpoints/{wfo}/{x},{y}/forecast`) | Active alerts and gridpoint forecast periods |
| NOAA Aviation Weather Center (AWC) | `https://aviationweather.gov/api/data/metar?ids={icao,...}&format=json&hours=2` and `https://aviationweather.gov/api/data/taf?ids={icao,...}&format=json` | Decoded METAR observations and TAF forecast groups; international station network |
| Open-Meteo (non-US routes only) | `https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,weather_code,wind_speed_10m&hourly=precipitation_probability&forecast_days=3&timezone=UTC` | Current WMO condition and peak in-window precipitation probability; no API key |

**Configuration:** no API keys are required. The only optional environment variable is
`ROUTEGUARD_CONTACT_EMAIL`, which sets the identifying `User-Agent` contact. Full
details are in `docs/05_CONFIGURATION.md`.

NWS G-AIRMET, CWA and SIGMET were verified during design but are not integrated in
the MVP. HTML is never parsed; no paid service is used.

### FAA operational status — deliberately excluded

FAA published pages offer human-facing dashboards but no documented, stable, no-key
programmatic feed suitable for this prototype. A legacy XML endpoint exists but is
undocumented and mixes airport closures with delay programs; presenting it as a
supported integration would breach the guardrails. RouteGuard therefore offers
authoritative external checks instead, always labelled as out-of-app verification
and never as evidence:

- <https://nasstatus.faa.gov/> — National Airspace System status
- <https://www.fly.faa.gov/flyfaa/usmap.jsp> — Airport Status & Delays

Weather signals are never represented as airport operational status, delays or closures.

## Decision logic

The full decision table (R00–R08, confidence C01–C05, normalization rules and
recommendation templates) is in `docs/01_architecture.md` sections 7–8. In brief:
a geography/overlap/time-eligible evidence core is split into trustworthy and
downgraded evidence; corroboration counts distinct providers with trustworthy
MODERATE-or-higher signals. R01 prevents "no alerts ⇒ LOW"; R02 marks unverified
extremes so they cannot become CRITICAL; R03–R08 are ordered terminal rules. Risk
and confidence are independent; confidence is capped for partial failures, stale
and low-reliability evidence. Two **architect-approved reconciliations** are recorded
in `docs/01_architecture.md` and applied consistently with the expected results:

- **R-1:** R01 tests the eligible **core** (so a downgraded-only case can reach R02/R05),
  and C01 requires at least one HIGH-reliability trustworthy item (so two MEDIUM
  corroborators cap at MEDIUM).
- **R-2:** C04 is keyed to the eligible core plus the LOW-reliability downgrade, not to
  "no trustworthy evidence". This includes the change formerly described as a third
  reconciliation: a stale-only eligible core stays at MEDIUM (C05 cap) rather than LOW.

No application code was changed by these reconciliations; the architecture table and
the shipped decision table now agree.

## Limitations

1. Airport-level, not itinerary-level: no flight number, gate, schedule, connection or aircraft route is emitted; no invented airports.
2. Whole travel day: no departure time; destination evidence uses the same UTC window and arrival-local date is not modelled.
3. Forward horizon: NWS gridpoint forecasts are ~7 days, TAF ~30 h, and NWS active alerts only describe alerts active now. Beyond these horizons the engine returns INDETERMINATE, never a reassuring LOW.
4. Weather is not operations: NWS/AWC are weather signals; the app never claims an airport is delayed or closed.
5. FAA status is not integrated; authoritative links are offered instead.
6. AWC advisories are not integrated: G-AIRMET `bbox` filtering was unreliable in live verification and polygon filtering is out of MVP scope.
7. No numerical score and no AI/LLM at runtime; classification is deterministic.
8. Rate limits: NWS publishes no numeric limit; AWC documents 100 requests/min and ≤400 entries. A route issues at most 3 NWS calls and 2 AWC calls per assessment; a repeated-demo throttle is not implemented.
9. Caching is limited to provider `Cache-Control`; no production cache, auth or monitoring.
10. DST edge cases use Python's default `zoneinfo` fold behaviour at ambiguous/nonexistent local midnight; precision is reduced and disclosed.
11. City coverage is 75 curated airports (48 US + 27 international); unmapped input returns `UNMAPPED_CITY` rather than a guess. UI labels such as `Salt Lake City (SLC)` and ICAO codes are accepted by the API.
12. Travel dates must be the departure airport's local today or later; an earlier date is rejected as `INVALID_DATE` with HTTP 422. There is no hard maximum horizon: beyond the disclosed forecast windows the engine returns `INDETERMINATE` with a coverage note instead of rejecting the request.
13. Outside the United States there is no integrated official national alert feed. Open-Meteo current/hourly weather and AWC aviation weather are global proxies, not operational-status data; the coverage note states this explicitly.
14. The schematic map uses real coordinates but no country polygons; it is a coordinate projection, not a geographic basemap.

### Benign in-horizon coverage is intentionally not reassuring

For an ordinary future-date run (e.g. JFK→SFO, 1–2 days out) it is **expected, not a
defect**, that the engine returns `INDETERMINATE` / `LOW` even though both provider
calls succeeded (`provider_status = [NWS OK 200, AWC OK 200]`, `degraded=false`):

- NWS gridpoint periods that meet none of the severity thresholds are deliberately not
  emitted. The absence of a flagged hazard is not positive evidence of safe conditions.
- An AWC METAR is a ~1 h point observation. For a travel day 1–2 days out its window has
  `temporal_overlap == NONE`, so it stays visible in `evidence[]` but is outside the
  eligibility core. TAF validity (~30 h) fails the same test beyond that horizon.
- The core is therefore empty: R01 fires → `INDETERMINATE`, and C04 → `LOW` confidence.
  R07 `CLEAR` requires ≥1 trustworthy evidence item from **each** provider; it cannot be
  satisfied by reachability alone.

**"Both providers reached" is not the same as "both contributed eligible evidence."**
`ProviderStatus.status == OK` asserts only that the HTTP request succeeded and the
payload was readable. Two `OK` statuses with zero eligible evidence is the normal shape
of an inconclusive assessment: the response says so honestly rather than converting
silence into reassurance. The UI shows the two `provider_status` entries under the
"Source coverage" panel as data-gathering status only, keeps `coverage_note` visible,
and shows the R01 recommendation verbatim. Phrase a healthy in-horizon run as *"both weather providers were contacted
successfully; no eligible hazard evidence was found for the selected travel day, so no
risk level can be concluded — re-check closer to departure"* — never as "all clear",
"low risk" or "two providers confirm safe conditions". No normalization or R07 change
is warranted in the MVP.

## How AI was used in development

AI assisted with coding, adapter scaffolding, decision-table/test drafting and
documentation, guided by the architect's verified endpoint research. At runtime
RouteGuard is fully deterministic: there is no model call, no generated prose and
no AI-derived classification.

## What I'd change before production

- Add authentication, abuse protection and per-provider 60 s throttling.
- Add caching with explicit TTLs keyed by airport/date, and request-level monitoring/alerting.
- Establish a real, documented FAA data agreement before presenting operational status.
- Broaden city coverage and validate the registry against an authoritative airport dataset.
- Move to itinerary-level data (flight numbers, times and connections) with user consent, and keep human escalation for high-impact decisions.

## Delivery manifest

Application: `app/{__init__,main,config,models,airports.json,cities,http_client,logging,normalize,risk,service}.py`, `app/providers/{__init__,base,nws,awc}.py`.
Frontend: `static/{index.html,styles.css,app.js}`.
Tests: `tests/{__init__,conftest,test_cities,test_normalize,test_adapters,test_risk,test_api,test_open_meteo}.py` and `tests/fixtures/*.json`.
Dependencies/docs: `requirements.txt`, this README, and `docs/00_PRD.md` … `docs/05_CONFIGURATION.md` (including QA reports).
