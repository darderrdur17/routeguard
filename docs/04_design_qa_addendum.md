# RouteGuard — Design QA Addendum

**Date:** 2026-11-16 · **Reviewer:** independent frontend/design QA · **Server:** `http://127.0.0.1:8771/` (live)
**Scope:** the 17 final acceptance criteria in `briefing/04_premium_design_directive.md` §11, plus the binding integrity controls in `briefing/02_route_guard_execution_guardrails.md`.
**Mode:** browser checks EXECUTED with Python Playwright + headless Chrome; screenshots captured; static review of `index.html`, `styles.css`, `app.js`, `README.md`. No check below is claimed without execution.

## Acceptance checklist

| # | Criterion | Status | Evidence from executed checks |
|---|---|---|---|
| 1 | Modern 2026 design language | Pass | Desktop/mobile screenshots; dark command-centre shell, restrained surfaces, one gradient accent. |
| 2 | Consistent typography and visual tokens | Pass | `font_geist: true` (computed body font); CSS custom-property token set for colour, radius, shadow and motion. |
| 3 | Refined bento dashboard | Pass | `bento_panels: 11` distinct card regions with asymmetric spans. |
| 4 | Immersive route intelligence experience | Pass | Journey strip, map, timeline, distribution, evidence ledger and actions on one page; no navigation away from context. |
| 5 | Interactive map where feasible | Pass | `map_markers: 4`; `signal_markers: 2`; clicking a signal marker opened the drawer with `drawer_rows: 12`. |
| 6 | Coordinated map and evidence interactions | Pass | Marker → drawer + ledger highlight; airport card click → `airport_focus_active: true` with filtered/highlighted evidence; timeline → drawer. |
| 7 | Interactive disruption timeline | Pass | `timeline_items: 2` with real provider timestamps; first item opened the drawer. |
| 8 | Contextual evidence panels | Pass | Drawer rendered 12 detail rows: source, signal, severity, verification, location, observation, validity, retrieval, relevance, interpretation, raw excerpt. |
| 9 | Smooth interface animations | Pass | CSS transitions on interactions, card entrance, verdict entrance; animation only on first load or genuine class change; no scroll-jacking. |
| 10 | Meaningful chart transitions | Pass | `dist_bars: 7` bars derived from normalized evidence counts by severity and provider; no probability or delay score. |
| 11 | Responsive desktop, tablet, mobile | Pass | Desktop 1512px, tablet 820px and mobile 390px all rendered 11 visible cards; `mobile_overflow: false`, `TABLET_OVERFLOW: False`. |
| 12 | Functional command palette if implemented | Pass | `palette_open: true`; typing "refresh" returned 1 command; Escape closed it (`palette_closed: true`). |
| 13 | Functional search, filtering and refresh | Pass | `airport_options: 48` from `GET /api/airports`; 6 filter chips changed counts (All 2, Aviation observation 2, Confirmed 2, Weather 0, Forecast 0, Severe+ 0); refresh completed with results visible. |
| 14 | Actual backend-connected interactions | Pass | `api_status: 200`, `api_providers: 2`, `api_evidence: 2`, `api_locations: 2`; no score fields (`api_score_fields: []`). |
| 15 | No fabricated information or fake controls | Pass | No progress percentages or staged retrieval; loading is a single honest "Contacting sources…" state; map legend and caption state the connector is not a flight path; FAA shown as not integrated with authoritative links. |
| 16 | Reduced-motion accessibility | Pass | `reduced_motion="reduce"` context completed an assessment with classification visible; `@media (prefers-reduced-motion: reduce)` neutralises animation/transition durations. |
| 17 | No regression in existing product functionality | Pass | `python3 -m pytest -q` → `73 passed`; live 422/200 behaviour from original QA retained; no page or console errors in final run (`errors: []`). |

## Findings and corrections

| ID | Severity | Component | Observed | Correction | Status |
|---|---|---|---|---|---|
| F-D1 | Medium | `styles.css` | Playwright click on the form was intercepted by the `hidden` evidence drawer: `.drawer { display:flex }` defeated the HTML `hidden` attribute. | Added a global `[hidden] { display:none !important }` rule. | Fixed |
| F-D2 | Medium | `app.js`, `styles.css` | Map marker clicks were intercepted by the decorative grid rect and by adjacent marker labels; overlapping signal/airport markers were ambiguous. | Added explicit 9px transparent hit circles, moved labels outside marker groups with `pointer-events:none`, disabled pointer events on decorative SVG layers, and increased signal offset to 18px. Signal-marker click then opened the drawer. | Fixed |
| F-D3 | Low | `index.html` | Browser console logged a 404 for `/favicon.ico` (`errors: ["console: Failed to load resource…404"]`). | Added an inline SVG data-URI favicon. Final run: `errors: []`. | Fixed |

No Critical or outstanding High/Medium finding remains. The original functional findings F-01–F-06 in `docs/03_qa_report.md` are separately closed; F-06 was ruled correct conservative behaviour by the architect and is documented in `README.md`.

## Executed browser assertions (final run)

- Page load: title `RouteGuard · Travel Disruption Intelligence`; 48 airport options; empty state visible; computed body font contains `Geist`.
- Assessment: `classification=INDETERMINATE`, `confidence=LOW`; 11 bento panels; 2 provider cards; 4 map markers; 2 signal markers; 6 filter chips; 2 evidence cards; 2 timeline items; 7 distribution bars; 1 action; 1 rule; 2 FAA links.
- Interactions: signal-marker click → drawer visible with 12 detail rows; destination airport click → active state; timeline click → drawer; `Ctrl+K` → palette with "refresh" command → Escape closes; refresh → results still visible.
- API via `page.request.post`: HTTP 200, exactly 2 provider statuses, 2 evidence items, 2 items with geographic anchors, zero score/probability top-level fields.
- Responsive: 1512px desktop, 820px tablet, 390px mobile — 11 visible cards each and no horizontal overflow. Reduced-motion context rendered the assessment normally.
- Console/page errors: none.
- Screenshots: `/tmp/routeguard_qa_desktop.png`, `/tmp/routeguard_qa_mobile.png`, `/tmp/routeguard_qa_drawer.png`.

## Interpretation note

The observed `INDETERMINATE / LOW` outcome is expected for a 1–2-day-out JFK→SFO date: both providers were reached successfully but no eligible in-horizon hazard evidence existed. This is the deliberate "missing information must not produce LOW risk" behaviour, not a UI or engine regression. Do not describe it as "all clear" in the demo.

## Verdict

**READY.** All 17 design acceptance criteria pass on executed checks, all three defects found during this pass were fixed and re-verified, the backend/risk engine is unchanged in behaviour, and the full test suite remains green.

---

## Addendum — global-coverage and screenshot review (same date)

A real screenshot exposed one usability defect not caught by the first browser pass: selecting `Salt Lake City (SLC)` from the autocomplete was rejected as `UNMAPPED_CITY` while stale JFK→SFO results remained on screen. Both were fixed and re-verified.

| Check | Status | Executed evidence |
|---|---|---|
| Autocomplete labels accepted by the API | Pass | `CityRegistry.resolve("Salt Lake City (SLC)") → SLC`; ICAO codes also accepted; live POST returned 200 with `NWS OK` + `AWC OK`. |
| No stale result after a failed request | Pass | Browser test with `Atlantis`: `#results` hidden, empty state visible, `422 UNMAPPED_CITY` shown. |
| Current cities and nations identified | Pass | 75 airport options, each with a country label; journey panel shows `UNITED STATES`, `SINGAPORE`, `UNITED KINGDOM`; coverage badge shows `NWS + AWC` or `Open-Meteo + AWC`. |
| Global coverage where appropriate | Pass | Live Singapore→London returned 200 with `OPEN_METEO OK` and `AWC OK`; 9 evidence items; risk rules remained provider-agnostic; no score fields. |
| World-aware map and purposeful motion | Pass | Bounds recomputed per route; animated connector present; global caption states it is schematic and not a flight path; reduced-motion mobile run rendered 11 panels with no horizontal overflow. |
| Configuration documented exactly | Pass | `docs/05_CONFIGURATION.md`: no API keys; only optional variable `ROUTEGUARD_CONTACT_EMAIL`. |

Final state after the global-coverage pass: **79 pytest tests pass**; ZIP re-extracted and re-ran all 79 tests; app imports with the 75-airport registry. Screenshots: `/tmp/routeguard_global_desktop.png`, `/tmp/routeguard_global_mobile.png`.

---

## Addendum — SEO, GitHub and Vercel publication (same date)

| Check | Status | Executed evidence |
|---|---|---|
| Exact browser identity | Pass | Served HTML contains `<title>RouteGuard | US Travel Disruption Intelligence</title>` and the approved meta description verbatim. |
| Canonical/social URL pinning | Pass | `{{SITE_URL}}` is resolved server-side; `ROUTEGUARD_SITE_URL` is set to `https://routeguard-six.vercel.app`; canonical and OG/Twitter URLs use the production alias even on a preview deployment. |
| Social assets | Pass | `static/og-image.png` verified as a real 1200×630 PNG; `favicon.svg` and 180×180 `apple-touch-icon.png` return 200 with correct content types. |
| Crawler controls | Pass | `/robots.txt` allows `/`, disallows `/api/`, `/docs`, `/redoc` and `/openapi.json`, and points to `/sitemap.xml`; the sitemap contains exactly one public URL. |
| Public GitHub repository | Pass | `https://github.com/darderrdur17/routeguard` verified `PUBLIC`; homepage set to the live Vercel URL. |
| Vercel production deployment | Pass | Project `routeguard` created; alias `https://routeguard-six.vercel.app` returns 200 for `/`, `/api/health`, `/robots.txt`, `/sitemap.xml` and the static assets. Live `Salt Lake City (SLC)` → JFK returned 200 with `NWS OK` + `AWC OK`, `LOW` / `MEDIUM`, 7 evidence items. |
| No metadata regressions | Pass | `python3 -m pytest -q` → **84 passed**, including 5 new SEO tests; no application/risk behaviour changed. |

The Vercel project name `routeguard` was accepted; the short alias `routeguard-six.vercel.app` was the actual URL assigned by Vercel and was therefore used for canonical metadata rather than an assumed `routeguard.vercel.app`.

---

## Addendum — Dashboard V29, interactive map and motion (same date)

| Check | Status | Executed evidence |
|---|---|---|
| V29 shell | Pass | Browser at 1440×900: dark 7-item rail, light canvas `rgb(243,244,246)`, heading `Travel Intelligence`, 6 view pills, coral/pastel/charcoal cards and right contextual panel all visible. |
| Map as centrepiece | Pass | `#map-stage` measured 620px on desktop; MapLibre GL JS loaded with OpenFreeMap Positron; visible attribution; reset, fullscreen, zoom, pan and layer controls present. SVG fallback retained and unit-checked. |
| Layer integrity | Pass | Airports, route reference, weather and aviation toggles are live; Airport Operations is disabled with `no feed`; Aviation Advisories is an honest empty view. Weather view with no NWS/Open-Meteo evidence showed 0 cards and only the 2 airport markers. |
| Evidence synchronization | Pass | Clicking the first evidence card set `#context-selection-title` to `AWC · awc metar`, selected exactly 1 card and emphasized the map marker/timeline item through the shared selection state. |
| Progressive disclosure | Pass | Overview/Analyst switch changed `body[data-mode]` to `analyst`; glossary tooltips and technical-only fields are present without hiding evidence. |
| Motion and honesty | Pass | Staggered cards, marker entrance, map focus, skeleton and refresh-line states implemented; loading announcement and `aria-busy` verified; no percentage or simulated stage. |
| Responsive and accessible | Pass | 820px and 390px runs had no horizontal overflow; mobile rail becomes a bottom bar; keyboard handlers, visible focus, skip link and reduced-motion rules retained. |
| Backend integrity | Pass | `/api/assess` returned 200 with the existing deterministic payload; classification `INDETERMINATE`, 2 evidence items, no score. Invalid `Atlantis` route returned `UNMAPPED_CITY`, hid results and showed the empty state. |
| No regressions | Pass | `python3 -m pytest -q` → **90 passed** (84 prior + 6 frontend contract tests); no page errors and no console errors in the browser pass. |

Screenshots: `/tmp/routeguard_v29_desktop.png`, `/tmp/routeguard_v29_tablet.png`, `/tmp/routeguard_v29_mobile.png`. The backend, risk rules, provider adapters, SEO metadata and canonical URL were intentionally unchanged.

---

## Addendum — full audit fix pass (same date)

A project-wide audit found 13 issues (3 High, 6 Medium, 4 Low). All were fixed and each fix carries a regression test. Executed verification:

| Check | Status | Executed evidence |
|---|---|---|
| Airport markers stop stacking | Pass | Root cause: CSS `animation`/`transform` on `.rg-marker` overwrote MapLibre's geographic marker `transform`. Transforms moved to `.rg-marker > span`. Browser check: JFK `translate(190px,125px)`, SFO `translate(60px,135px)` — distinct; live route JFK→SFO places JFK near the US Northeast and SFO near the West Coast. Screenshot `/tmp/routeguard_marker_stage_jfk_sfo.png`. |
| Airport-location tracking end to end | Pass | Origin context reports New York / JFK / United States / America/New_York; destination reports San Francisco / SFO / United States / America/Los_Angeles. Switching to London→Singapore updates both country labels and marker transforms. API coordinates: JFK `40.6413,-73.7781`, SFO `37.6213,-122.3790`. |
| Partial-provider failure no longer 500 | Pass | C03 `MEDIUM_PARTIAL` now links recommendations to surviving-provider evidence and is skipped when none survives. Regression tests: no-surviving-evidence → no recommendation; surviving AWC evidence → cited; full degraded response still a valid `Assessment`. |
| Max-date overflow 500 fixed | Pass | `9999-12-31` returns a valid `INDETERMINATE` response instead of `OverflowError` → 500. |
| Uniform error envelopes | Pass | 404 → `NOT_FOUND`, 405 → `METHOD_NOT_ALLOWED`, both via the same `{code,message,request_id,details}` envelope as 422. |
| Validation precedence | Pass | Invalid route + invalid date together → `INVALID_ROUTE` (route wins). |
| Same airport rejected | Pass | `{"origin":"New York","destination":"New York"}` → 422 `INVALID_ROUTE`. |
| Open-Meteo hourly evidence is live | Pass | Hourly precipitation probability keeps `observed_at=null` (never an observation) but gains forecast-validity freshness (`FRESH`) and participates in classification. |
| Loading feedback before first result | Pass | Skeleton + announcement render outside the hidden `#results` section. |
| View pills no longer blank panels | Pass | Signal cards, map markers and priority findings read from the full assessment evidence, not the filtered view. |
| Failed refresh keeps last good data | Pass | Last assessment preserved; `lastPayload` set only on success. |
| Dialog focus containment | Pass | Command palette and evidence drawer trap Tab focus and restore it to the opener on close. |
| Keyboard-accessible glossary | Pass | Glossary terms are real `<button>`s with descriptive `aria-label`s; incorrect `role="listitem"` removed from buttons. |
| `safeUrl()` hardening | Pass | Rejects `undefined`/`null`/empty/literal placeholder strings before URL parsing. |
| No crawlable duplicate page | Pass | `/static/index.html` → 307 `/` via `CanonicalStaticFiles`, eliminating an indexed duplicate with unresolved `{{SITE_URL}}`. |
| Duplicate fullscreen control removed | Pass | MapLibre's `FullscreenControl` dropped; custom control retained. |
| Stale airport focus cleared | Pass | Switching view pills clears `activeAirport` and rerenders airport blocks. |

Final state: `python3 -m pytest -q` → **106 passed** (90 prior + 16 new regression tests across `test_api.py`, `test_risk.py`, `test_open_meteo.py`, `test_frontend.py`). No rule semantics, no-score architecture or provider contract changed.

---

## Addendum — UX pass: blank workspace, layout panning, date clarity (17 Nov 2026)

User browser reports (Safari, 1920px): a blank workspace despite a completed assessment; content cut off at the navigation-rail edge (horizontal pan); an unclear `INVALID_DATE: Request validation failed. body.date` error for past dates. All fixed and re-verified.

| Check | Status | Executed evidence |
|---|---|---|
| Blank workspace impossible | Pass | New `syncWorkspace()` owns visibility: results iff an assessment exists, skeleton only for a first in-flight run, empty state otherwise. `setBusy`, `render` and the error path all delegate to it; direct `show(dom.results, …)` calls are gone. A render exception is caught and surfaced as `RENDER_FAILED` instead of blanking the canvas. |
| No horizontal panning | Pass | `html, body { overflow-x: clip }` (scroll container avoided so sticky headers keep working). Rail narrowed 76→64px; context column min 300→280px. Chromium check at 1920/1512/1280px in the results view: `scrollWidth == clientWidth` everywhere, no page errors. |
| Past dates prevented at the picker | Pass | `#travel-date` gets `min=<local today>` at init plus an inline hint "Today onwards — past dates can't be assessed". |
| Past dates explained in plain language | Pass | Client guard blocks the request with "*INVALID_DATE: Travel dates in the past cannot be assessed. RouteGuard works from live forecasts and observations…*". API-side, `INVALID_DATE` now returns the human-readable bound ("Travel date 2026-11-14 is before the departure airport's local today (2026-11-16). RouteGuard assesses upcoming travel only: providers are forecast- and observation-based, so past dates cannot be evaluated."). Raw `body.date` field paths moved to the console, out of the visible message. |
| Mode switch self-documented | Pass | Overview tooltip "Plain-language summary for trip planning"; Analyst tooltip "Raw excerpts, reliability scores and technical detail"; group `aria-label` describes both modes. |
| Regression coverage | Pass | `python3 -m pytest -q` → **112 passed** (6 new tests: workspace invariant, render containment, client past-date guard, error-message clarity, mode-switch tooltips, overflow clip). |

---

## Addendum — retrospective mode: past-date assessments (17 Nov 2026)

The user asked to "proceed follow up" on genuine historical support. Provider research executed live: AWC METAR supports an anchored `date` + `hours` historical window (verified: 24 real KSFO observations returned for a date 2 days back); Open-Meteo's no-key forecast endpoint returns `past_days=7` hourly model data; NWS publishes no historical alert/gridpoint archive and AWC exposes no historical TAF. Design: a past date switches the run to AWC historical METAR + Open-Meteo recent-past model hours, classified by the unchanged decision table.

| Check | Status | Executed evidence |
|---|---|---|
| Provider research | Pass | Live curls: AWC `date=...T00:00:00Z&hours=24` → 24 obs covering exactly the anchored day; Open-Meteo `past_days=7` hourly weather codes/temperature/wind/precipitation present for dates 2-3 days back. |
| 7-day retrospective window | Pass | `AssessRequest` accepts dates ≥ origin-local today − 7; older dates → 422 `INVALID_DATE` "Retrospective coverage extends 7 days back". |
| Routing | Pass | New `tests/test_service.py`: retrospective run constructs Open-Meteo/AWC retrospective adapters (never NWS) and marks `assessment_mode="retrospective"`, basis `airport-level retrospective`; forward run keeps NWS + AWC. |
| Historical METAR | Pass | AWC retrospective anchors `date=<window end UTC>&hours=25` and skips TAF with an explanatory note (adapter test with MockTransport). |
| Recent-past model hours | Pass | Open-Meteo retrospective summarises the most severe in-window hour (shared WMO/wind severity rule) plus peak wind/precipitation per airport; hours outside the window are ignored. |
| Freshness semantics | Pass | In retrospective mode freshness is judged relative to the assessed window: in-day evidence is FRESH (unit tests: METAR IFR + retrospective model record), the same payloads under the forward normalizer are STALE/old. Reliability stays honest: AWC METAR HIGH, Open-Meteo retrospective MEDIUM (model reanalysis). |
| Live end-to-end | Pass | Local server, JFK→SFO on 2026-11-14 (2 days back): both providers OK with 4 evidence items (all FRESH), R07_CLEAR / HIGH confidence for a genuinely calm day, coverage note discloses reanalysis + missing NWS/TAF history. Forward run unchanged (NWS OK + AWC OK). |
| UI | Pass | Date picker min = local today − 7 with hint "Today onwards — or up to 7 days back"; client guard only trips beyond 7 days; coverage badge prefixes `RETROSPECTIVE`; journey basis shows `airport-level retrospective`. Browser run: no JS errors. |
| Regression coverage | Pass | `python3 -m pytest -q` → **120 passed** (8 new: 2 API bounds, 3 normalization, 1 AWC adapter, 2 service routing; frontend tests updated for the new bounds). |

---

## Addendum — History dataset view, final audit fixes and release verification (17 Nov 2026)

The brief was extended to browse historical datasets beyond the 7-day retrospective
window, and a second project-wide audit was run before release. This addendum records
the executed verification, including the dispositions of every audit finding.

### History feature

| Check | Status | Executed evidence |
|---|---|---|
| Backend contract | Pass | `GET /api/history?origin=JFK&destination=SFO&start_date=2026-09-18&end_date=2026-09-28` → HTTP 200, 11 daily rows per airport. Provenance: `Open-Meteo Archive API`, `ERA5 reanalysis (model), not observations`, docs URL and `retrieved_at`. First origin row: 28.5 °C max / 22.1 °C min / 0.6 mm / 14.7 km/h / code 51 — real archive values. |
| No classification leakage | Pass | A case-insensitive scan of the entire 200 payload for `classification`, `severity`, `score`, `confidence`, `risk_level` found **NONE**. History is a dataset view only. |
| Validation bounds | Pass | Inverted range → 422 `INVALID_DATE`; `end_date` 5 days back → 422 `INVALID_DATE` naming the 6-day lag bound (2026-11-11); 391-day range → 422 `INVALID_DATE`; unknown airport → 422 `INVALID_ROUTE`. All use the uniform envelope. |
| Missing-day honesty | Pass | Unit tests confirm padded/truncated series carry explicit `null`, rendered as literal "no data" in tables and a hatched empty slot in the SVG chart. No interpolation anywhere in `app/providers/open_meteo_archive.py`. |
| Partial upstream failure | Pass | Both airports fail → 502 `UPSTREAM_UNAVAILABLE`; one fails → HTTP 200 with `unavailable: true` for that airport only. |
| Frontend end to end | Pass | Chromium: History pill and context-panel entry button both open the view; JFK/SFO prefilled; client bounds block inverted and too-recent ranges with `INVALID_DATE`; successful fetch renders 11 rows per airport, 22 origin bars and the provenance line; switching back restores the assessment and hides history; no page errors. WebKit/Safari engine: same flow, 11 rows, 22 bars, no overflow and no page errors. |

### Audit findings and dispositions

| # | Severity | Finding / location | Disposition |
|---|---|---|---|
| F2 | Medium | Glossary chips in `static/index.html` were buttons with `aria-label` but no click handler — dead controls. | **Fixed.** Wired to `toast()` using the aria definitions. Browser check: first glossary chip surfaces "a routine aviation weather observation issued at an airport." |
| F3 | Medium | `#drawer-map` in `static/app.js` called `selectEvidence()` while the drawer still covered the map. | **Fixed.** Captures the evidence id, calls `closeDrawer()` first, then selects and scrolls. Browser check: drawer open → click map → drawer closed, evidence still selected, no page errors. |
| F4 | Low | `state.drawerEvidenceId` referenced but never declared in `static/app.js`. | **Fixed.** Declared at state initialisation. |
| F5 | Low | `app/providers/awc.py` assigned `role = "origin" if … else "destination"`, then overwrote unknown stations. | **Fixed.** Single `if/elif/else` assigns origin/destination/unknown once. |
| F6 | Low | Airport-local "today" duplicated in `app/models.py` and `app/service.py`. | **Fixed.** Shared `app/timeutils.py::airport_local_today()`; both modules delegate. Browser check: date `min` = 2026-11-10 before and after assessment. |
| F7 | Medium | `app/http_client.py` let 3xx responses fall through to JSON parsing, hiding endpoint drift as `MalformedJSON`. | **Fixed.** 300–399 raises `UpstreamError("RedirectDisallowed(<status>)")`; regression test added. |
| F8 | Low | Retrospective coverage was reported as missing by the audit. | **Rejected.** Tests already existed in `tests/test_adapters.py`, `tests/test_open_meteo.py` and `tests/test_service.py`; no change made. |
| — | — | A further Low finding on prior-pass toast/marker duplication was re-checked and found already resolved in `c84f12d`. | **No change.** |

### Release regression

| Check | Status | Executed evidence |
|---|---|---|
| Full suite | Pass | `python3 -m pytest -q` → **136 passed, 1 warning** (upstream Starlette/httpx deprecation notice only). |
| Live forward assessment | Pass | JFK→SFO on a future date → HTTP 200, `assessment_mode: forward`; NWS points/alerts/gridpoint and AWC METAR/TAF all returned HTTP 200. On a date outside the provider horizon the honest result is `INDETERMINATE/LOW`, never "all clear". |
| Live retrospective assessment | Pass | JFK→SFO two days back → HTTP 200, `assessment_mode: retrospective`, `HIGH/HIGH`, 19 AWC METAR + 2 Open-Meteo retrospective evidence items, AWC `date=…T05:00:00Z&hours=25` and Open-Meteo `past_days=7`. |
| Sandbox networking note | Pass | A detached shell process could not reach the egress proxy (`Connection refused os error 61`). Foreground `httpx` and the managed server both returned HTTP 200 from the archive, so this was an environment artifact, not an application defect. Live verification used the managed server and in-process `TestClient`. |
| Browser regression | Pass | 28 checks in Chromium covering empty state, no horizontal overflow, forward assessment, Analyst/Overview switch, command palette open/Escape, glossary toast, context entry into History, client validation, provenance, tables, SVG bars, view restoration and zero page errors. Two initial harness failures were corrected: `[data-view=history]` also matched `<body>`, and Inspect is intentionally disabled until evidence is selected (21 evidence cards → drawer opens and closes correctly). |
| Cross-engine | Pass | WebKit/Safari engine smoke test of the History flow: 11 rows, 22 bars, no overflow, no page errors. |

---

## Addendum — History flow polish (17 Nov 2026, final)

A user-reported review of the active-route History flow (JFK → SFO, "Fetch history")
identified integration gaps that were functional but not yet coherent: the date
pickers had no bounds, the archive cutoff was explained only after a failed request,
opening History left both dates empty, and loading/empty states were implicit. All
fixed and re-verified.

| Check | Status | Executed evidence |
|---|---|---|
| UTC cutoff parity with backend | Pass | `archiveMaxEndDate()` and `archiveMinStartDate()` now derive the UTC calendar date the same way `HistoryService._validate_dates` does. On 2026-11-17 the picker advertised cutoff **2026-11-11** and earliest **2025-11-11**; both inputs carry those exact `max`/`min` values in Chromium and WebKit. A browser in another timezone can no longer request a day the API rejects. |
| Proactive cutoff warnings | Pass | Persistent line: "ERA5 archive cutoff: 2026-11-11 — reanalysis is published ~6 days behind today. Available dates: 2025-11-11 through 2026-11-11." Selecting 2026-11-11 shows an amber "latest available archive day… may still be revised" warning. Selecting 2026-11-16 shows a red "beyond the ERA5 archive cutoff (2026-11-11)… choose 2026-11-11 or earlier", marks both inputs `aria-invalid`, and blocks the request before any network call. Inverted ranges and >366-day spans are warned live. |
| Active-route carry-over | Pass | Clicking "View historical conditions" after a JFK → SFO assessment prefills labelled route chips `JFK → SFO` with accessible titles, and a usable 30-day window ending at the cutoff (2026-10-13 → 2026-11-11). No manual date entry is needed to get a first result. |
| Loading / empty / error / success | Pass | 32 targeted browser checks: empty state and hidden panels on entry; "Loading daily ERA5 reanalysis for JFK → SFO…" spinner with disabled Fetch while the request is delayed; success clears loading/empty, reveals panels, provenance and 11 real rows; a mocked 502 clears panels, surfaces `UPSTREAM_UNAVAILABLE` and explains "No history loaded." in the empty state. No page errors. |
| Cross-engine regression | Pass | 42 checks across Chromium and WebKit: initial empty state, no horizontal overflow, retrospective assessment, evidence selection and drawer, "Show on map", command palette, glossary toast, History entry, cutoff warning, successful fetch and restoration of the assessment on switching back. All passed with zero page errors. |
| Static contract + suite | Pass | Three new tests in `tests/test_frontend.py` cover UTC bounds, the shared validator, explicit state transitions and route/default prefills. `python3 -m pytest -q` → **139 passed, 1 warning**; `node --check static/app.js` clean. |
