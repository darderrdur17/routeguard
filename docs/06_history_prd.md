# RouteGuard — Incremental PRD: Year-Deep History Browsing (Delta Only)

Language: English · Author: Xu (PM) · Status: Draft for architect review

## 1. Project Info

- Programming Language: FastAPI backend + vanilla-JS single-page frontend (no build step), unchanged.
- Project Name: routeguard (increment on existing codebase).
- Original requirement restated: Extend data viewing beyond the existing 7-day retrospective window — users can browse historical weather datasets from previous periods (up to ~1 year) for selected origin/destination, including DATE-RANGE selection, displayed alongside existing views. This is a DATASET VIEW, not a risk assessment.

## 2. Product Goal

Let users explore day-by-day historical weather conditions at origin/destination airports for any date range in the past year, using the Open-Meteo Archive API (ERA5 reanalysis, free, no key, ~5–7 day publication lag), while keeping the existing forward/retrospective assessment flows and the no-score, evidence-provenance guarantees untouched.

## 3. User Stories

1. As a traveler, I can pick a past date range up to 1 year and see day-by-day conditions (temp max/min, precipitation, max wind, weather code) at origin and destination, so I can judge seasonal risk for a future trip.
2. As a traveler, I can see clearly that this data is a climate reanalysis model, not station observations, so I am not misled about data provenance.
3. As an analyst, I can see gaps/missing days explicitly marked as "no data", so I never mistake absence for calm weather.
4. As a traveler, I can open the history view from the current journey's origin/destination (codes prefilled), so I don't retype the route.
5. As an analyst, I can tell which provider supplied each value (Open-Meteo Archive; optionally AWC METAR counts), so the evidence ledger stays honest.

## 4. Requirements Pool

### P0 (Must have)
- P0-1 Backend: `GET /api/history?origin=&destination=&start_date=&end_date=` — new endpoint that fetches Open-Meteo Archive daily aggregates for both airports (temperature_2m_max/min, precipitation_sum, wind_speed_10m_max, weather_code; timezone=UTC). Validate range: end_date ≤ today − 6 days (respect reanalysis lag), start_date ≥ end_date − 365 days, range ≤ 366 days. No risk classification, no score in the response.
- P0-2 Frontend: date-range picker (start/end date inputs, capped at 1 year) with client-side validation mirroring P0-1 bounds.
- P0-3 Frontend: history results panel per airport — daily aggregate table plus a simple visual (e.g., bar/strip chart of precipitation and wind per day). Missing days rendered as explicit "no data" rows/gaps.

### P1 (Should have)
- P1-1 Severity-color coding reusing the existing severity palette (calm/moderate/severe tokens already in design tokens) — same thresholds vocabulary, but labeled "historic condition intensity", never reusing risk classification R01–R08.
- P1-2 Provenance labeling: persistent badge "ERA5 reanalysis (model), not observations" on the panel and in each tooltip; cite Open-Meteo Archive URL in the sources area.
- P1-3 Entry link: "View historical conditions" button in the journey/context panel; prefill origin/destination codes from current assessment.

### P2 (Nice to have)
- P2-1 AWC METAR observation counts per day (short ranges only, e.g., ≤ 14 days) as a supplementary "station coverage" line — clearly separated from reanalysis rows.
- P2-2 Export history table as CSV.
- P2-3 Side-by-side origin vs destination comparison view.

## 5. Hard Constraints (non-negotiable)

- No API keys anywhere; Open-Meteo Archive is key-free like existing providers.
- No invented data: any day the archive does not return must be shown as "no data"; interpolation is forbidden.
- Reanalysis output must never be labeled "observations" or "METAR"; provider + model type always visible.
- Must not break forward mode, retrospective mode (≤7 days), risk decision table R01–R08, or the no-numerical-score guarantee — history endpoint returns no classification.
- Whole existing pytest suite stays green; new endpoint gets new tests (validation bounds, missing-day passthrough, provenance fields).
- No new third-party UI dependencies (vanilla JS, no build step).

## 6. UI Placement Sketch

The current workspace flows: search panel (`#assess-form`) → view-bar (dashboard view pills) → results section with panel grid + context column. Placement:

- Add a new pill "History" to the existing `.view-bar` group, sibling to Overview/Analyst modes — it toggles a history view instead of the assessment view.
- The history view itself is a new section in the results area, same panel-grid styling: a slim toolbar row (origin/destination code chips + start/end date inputs + "Fetch" button) at top, then one panel per airport with table + chart, mirroring the existing WEATHER panel look.
- The P1-3 entry link lives in the existing context column (`#context-panel`), under route details, as a secondary button — one click activates the History pill with codes prefilled.
- The view uses the existing skeleton/toast/error patterns; while loading, reuse `#loading-skeleton`.

## 7. Open Questions (for architect/lead)

1. Frontend chart approach: hand-rolled SVG bars (consistent with existing SVG map fallback, zero deps) vs. a tiny chart lib — recommend hand-rolled SVG; confirm.
2. Range cap: exactly 365 days, or smaller default (e.g., 90) with 365 as max to keep payload size responsive? Recommend 365 max, default last 30 days.
3. Should AWC METAR daily counts (P2-1) block this increment or be deferred to a follow-up? Recommend defer.

## 8. Acceptance Criteria (measurable)

- Any date range ≤ 1 year within ERA5 availability returns per-day rows for both airports; days with no data display "no data" (spot-check a known gap).
- Panel displays "ERA5 reanalysis (model)" provenance text; the word "observation(s)" never appears attached to archive data.
- Existing Playwright/pytest flows unchanged: all current tests pass; ≥ 3 new backend tests for /api/history.
- Forward/retrospective assessment UI and outputs are pixel- and behavior-identical when History view is unused.
