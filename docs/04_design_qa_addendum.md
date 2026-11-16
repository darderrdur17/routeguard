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
