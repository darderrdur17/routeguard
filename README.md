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

**Retrospective mode:** travel dates up to 7 days before the departure airport's
local today are supported. A past date switches the run to AWC historical METAR
observations (window anchored at the travel day) plus Open-Meteo recent-past
model hours, and the same deterministic decision table classifies the day —
`assessment_mode: "retrospective"`, basis `airport-level retrospective`, a
`RETROSPECTIVE` badge in the UI and a coverage note stating that NWS alert
history, TAF history and station-grade precision are unavailable. Open-Meteo
retrospective data is model reanalysis, not a station observation, and carries
MEDIUM reliability. Freshness for a retrospective run is judged relative to the
assessed day, so evidence generated during that day is not penalised as stale.

**Current focus and global extension:** the original brief focused on the United
States. That remains the default: 48 curated US airports assessed with NWS + AWC.
The prototype now also covers 27 curated airports in 25 other countries/regions
(including Hong Kong, China), assessed with Open-Meteo + AWC. The route's cities,
countries and active providers are shown in the journey panel and a coverage
badge. See `docs/05_CONFIGURATION.md` for the exact key/environment requirements —
**no API key is required**.

**Public links:** live app <https://routeguard-six.vercel.app> · source
<https://github.com/darderrdur17/routeguard>. The live canonical origin, Open Graph
URLs, `robots.txt` and `sitemap.xml` all resolve to the Vercel production alias
above.

## Run locally

From this directory:

```bash
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

Then open <http://127.0.0.1:8765/>. No build step, no frontend dependencies, no
API keys. `GET /api/health` returns `{"status":"ok"}`; `GET /api/airports` returns
the curated registry that backs the UI autocomplete; `POST /api/assess` accepts
`{"origin":"New York","destination":"San Francisco","date":"YYYY-MM-DD"}`.

### Vercel deployment

The same source is deployed through `api/index.py` and `vercel.json`; Vercel uses
Python 3.12 and installs `requirements.txt`. No paid plan or paid API is involved.
The deployment sets `ROUTEGUARD_SITE_URL` so canonical/OG URLs stay pinned to the
production alias even when a preview deployment is visited. `robots.txt` and
`sitemap.xml` are generated from that origin and publish only the product page.

### Interface

The frontend follows the supplied Dashboard V29 direction: a narrow dark navigation
rail, a light workspace canvas, rounded coral/pastel/charcoal cards, compact pill
filters and a dedicated right contextual panel. The interactive geographic map is
the visual centrepiece, not a decorative thumbnail.

- **Map:** MapLibre GL JS loads progressively from CDN with the keyless OpenFreeMap
  Positron style. Real airport coordinates and normalized evidence coordinates come
  from the backend; the map supports zoom, pan, marker selection, reset, fullscreen,
  layer toggles, a legend and visible OpenFreeMap/OpenMapTiles/OpenStreetMap
  attribution. If MapLibre cannot load, the original SVG schematic remains fully
  interactive with zoom, pan and the same layer controls.
- **Route honesty:** the dashed connector is explicitly labelled an illustrative
  airport-pair reference. It is never presented as a flight path, trajectory or
  verified itinerary.
- **Layer integrity:** Airports, Route reference, Weather and Aviation/METAR–TAF are
  toggleable because they have real data. Airport Operations is visibly disabled
  because no verified operational feed is integrated. Aviation Advisories is a
  genuine empty view for the same reason.
- **Synchronization:** selecting a map marker, evidence card, timeline item or
  priority finding updates one shared selection state. The contextual panel, map
  marker emphasis, evidence card and timeline item all stay in sync.
- **Progressive disclosure:** Overview mode uses plain language; Analyst mode reveals
  raw excerpts, reliability and technical detail. Glossary tooltips explain METAR,
  TAF, confidence and coverage without hiding evidence.
- **View pills:** All, Routes, Weather, Airport Operations, Aviation Advisories and
  High Priority filter real evidence and map visibility. Empty views explain what is
  unavailable rather than inventing data.
- **Motion:** staggered entrance, card hover/selection, map focus transitions,
  marker emphasis, filter/timeline transitions, drawer/panel motion and honest
  skeleton states are implemented. Refresh preserves the previous assessment and
  shows an indeterminate line — never a fabricated progress percentage. Marker
  emphasis transforms are applied to the marker's inner element only; MapLibre
  retains sole ownership of the marker element's geographic `transform`, so
  hover/selection styling can never displace an airport marker.
- **Keyboard and accessibility:** `⌘ K` / `Ctrl K` opens the command palette, all
  controls are keyboard reachable, focus is visible, loading is announced, dialogs
  trap and restore focus, and `prefers-reduced-motion` disables non-essential
  motion. Layouts were checked at 1440px, 820px and 390px with no overflow.
- A failed submission keeps the last good assessment visible, never mixes stale
  results with a fresh error, and first-run loading feedback is shown before any
  results exist.

## Test

```bash
python3 -m pytest -q
```

All tests are offline: provider behaviour is exercised with `httpx.MockTransport`.
No test makes a live network call. `tests/fixtures/` contains sanitised copies of
the recorded provider payload shapes documented in `docs/02_api_verification_notes.md`.
`tests/test_risk.py` implements every scenario (S01–S12) in `docs/01_architecture.md`
section 10 plus determinism, no-score and evidence-linkage assertions.
`tests/test_seo.py` verifies the exact browser title, meta description, canonical/OG
URL resolution, favicon/touch-icon references, robots policy, single-URL sitemap and
1200×630 Open Graph image. `tests/test_frontend.py` checks the V29 shell contract,
real layer controls, progressive disclosure, honest skeletons, keyless MapLibre
enhancement with SVG fallback, the no-`innerHTML` rule and accessibility tokens.
Current result: **120 passed**.

### Robustness hardening (post-audit)

A full audit pass fixed and regression-tested: uniform `NOT_FOUND` /
`METHOD_NOT_ALLOWED` error envelopes; route-before-date validation precedence
(both invalid → `INVALID_ROUTE`); same-origin/destination rejection; a
`9999-12-31` max-date overflow 500; partial-provider failures no longer 500 (C03
links to surviving-provider evidence or is skipped); Open-Meteo hourly
precipitation evidence now carries freshness and participates in classification;
`/static/index.html` redirects to `/` so no crawlable duplicate page with
unresolved template placeholders exists.

### UX pass (17 November 2026)

A browser-reported pass fixed: a workspace state that could show neither the
results nor the empty state (one `syncWorkspace()` function now owns that
invariant and a render exception surfaces a message instead of a blank canvas);
stray horizontal panning (`overflow-x: clip`; the navigation rail is narrower at
64px and the context panel min width 280px); past-date handling — the date
picker is bounded to today onwards with an inline hint, the client explains
"*travel dates in the past cannot be assessed*" before the API is called, and
the API returns a human-readable `INVALID_DATE` message naming the airport-local
bound instead of a generic validation banner. The Overview/Analyst switch
documents itself via tooltips (Overview = plain language; Analyst = raw
excerpts, reliability and technical detail).

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

The browser also loads MapLibre GL JS from `unpkg.com` and the keyless OpenFreeMap
Positron basemap from `tiles.openfreemap.org`. Neither requires an API key or an npm
build step; if either is unavailable, the bundled SVG map fallback remains usable.
No backend dependency or paid service is introduced by the map.

## Providers and real endpoints

All calls are backend-only, with an identifying
`User-Agent: RouteGuardPrototype/0.1 (contact: derren@example.com)`, a 10 s timeout
and at most two retries on 429/5xx. 204 is success-with-no-data.

| Provider | Endpoints | Evidence |
|---|---|---|
| National Weather Service (NWS) | `https://api.weather.gov/points/{lat},{lon}` → `https://api.weather.gov/alerts/active?point={lat},{lon}` and the `properties.forecast` URL read from the points response (template `https://api.weather.gov/gridpoints/{wfo}/{x},{y}/forecast`) | Active alerts and gridpoint forecast periods |
| NOAA Aviation Weather Center (AWC) | `https://aviationweather.gov/api/data/metar?ids={icao,...}&format=json&hours=2` and `https://aviationweather.gov/api/data/taf?ids={icao,...}&format=json` | Decoded METAR observations and TAF forecast groups; international station network |
| Open-Meteo (non-US routes only) | `https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,weather_code,wind_speed_10m&hourly=precipitation_probability&forecast_days=3&timezone=UTC` | Current WMO condition and peak in-window precipitation probability; no API key |

**Configuration:** no API keys are required. Two optional environment variables exist:
`ROUTEGUARD_CONTACT_EMAIL` sets the identifying `User-Agent` contact, and
`ROUTEGUARD_SITE_URL` pins the canonical public origin for SEO (set to the live
Vercel alias in this deployment). Full details are in `docs/05_CONFIGURATION.md`.

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
12. Travel dates must be within the supported coverage: up to 7 days before the departure airport's local today (retrospective) or any future date. Older dates are rejected as `INVALID_DATE` with HTTP 422. There is no hard maximum horizon: beyond the disclosed forecast windows the engine returns `INDETERMINATE` with a coverage note instead of rejecting the request.
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

Application: `app/{__init__,main,config,models,airports.json,cities,http_client,logging,normalize,risk,service}.py`, `app/providers/{__init__,base,nws,awc,open_meteo}.py`.
Deployment: `api/index.py`, `vercel.json`, `.vercelignore`, `.gitignore`.
Frontend: `static/{index.html,styles.css,app.js,favicon.svg,apple-touch-icon.png,og-image.png}`.
Tests: `tests/{__init__,conftest,test_cities,test_normalize,test_adapters,test_risk,test_api,test_open_meteo,test_seo,test_frontend}.py` and `tests/fixtures/*.json`.
Dependencies/docs: `requirements.txt`, this README, and `docs/00_PRD.md` … `docs/05_CONFIGURATION.md` (including QA reports).
