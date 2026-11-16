# RouteGuard — Independent QA Report

**Date:** 2026-11-16 · **Reviewer:** Yan (QA) · **Scope:** independent validation of the local prototype against the binding guardrails, PRD, architecture §§8/10/11/13 and the QA brief.

## Validation coverage — executed vs static-only

| # | Check | Mode | Result |
|---|---|---|---|
| 1 | `python3 -m pytest -q` | **EXECUTED** | `59 passed in 2.51s` (exit 0). Not relying on engineer's claim. |
| 2 | `tests/test_risk.py` S01–S12 + reconciliations | **EXECUTED** (file inspection + test run) | All 12 scenarios present; class, rule IDs, confidence and degraded inputs asserted. Reconciliation drift found (F-02, F-03). |
| 3 | `app/risk.py`, `app/normalize.py` vs decision table; greps | **STATIC + grep EXECUTED** | Rule order, missing/unverified guards and no-score invariant hold. Spec drift found (F-02, F-03, F-04). |
| 4 | Live uvicorn + curl (a)–(e) | **EXECUTED** | All five exercised, plus two extra date cases. Server started on 127.0.0.1:8766 and stopped afterwards. Past-date defect found (F-01). |
| 5 | Frontend rendering / XSS / notices | **STATIC-ONLY** (plus live `GET /` and asset fetches) | No `innerHTML`; textContent throughout; notices present; field omissions found (F-05). Browser rendering not executed. |
| 6 | Security/ops review | **STATIC + grep EXECUTED** | No secrets; identifying UA; bounded retries; 204 handled; errors redacted; no live calls in tests. |
| 7 | README accuracy | **STATIC comparison + executed commands** | Run/test commands match what I executed (I used the brief's port 8766 vs README's 8765). Limitations and FAA exclusion stated. |

Not executed: simulated provider failure in the live server (adapter failure paths are covered offline by `httpx.MockTransport`); JavaScript behaviour in a real browser.

## Required summary table

| Item | Status | Finding | Required correction |
|---|---|---|---|
| Technical accuracy | Fail | Architecture §8.1/§8.3 tables contradict the implemented and §10-expected behaviour for `eligible`, C01 and C04; README admits two reconciliations but the binding design doc was not updated (F-02, F-03). | Update `docs/01_architecture.md` §§8.1/8.3 with architect sign-off so one source of truth remains. |
| Code correctness | Fail | Past travel dates are accepted and trigger live provider calls (`HTTP 200`) instead of a 422 (F-01). | Add R00 date-bound validation + test. |
| Edge cases | Fail | 204/429/malformed JSON/unmapped city are handled and tested; past date is not (F-01). | Same as above. |
| Clarity | Fail | Evidence table omits `reliability`, `observed_at`, `geography` and `raw_excerpt`; the no-evidence recommendation exemption in `models.py` is broader than the spec (F-04, F-05). | Render the missing fields; narrow `NO_EVIDENCE_RULE_IDS`. |
| Assessment relevance | Fail | Live healthy runs for 2026-11-18 and 2026-11-17 returned `INDETERMINATE/LOW` with 0 NWS evidence and only out-of-window AWC METAR; both providers were called but did not both contribute evidence (F-06). | Make benign in-horizon coverage visible to R07 or reframe the demo claim. |

## Detailed findings

| ID | Severity | Component | Observed evidence (quote / exact output) | Expected | Required correction | Owner |
|---|---|---|---|---|---|---|
| F-01 | **High** | `app/models.py` / `app/main.py` | `curl -X POST ... -d '{"origin":"JFK","destination":"SFO","date":"2020-01-01"}'` → `HTTP 200`, body `"travel_date":"2020-01-01"`, `"classification":"INDETERMINATE"`; server log then shows four live provider calls for request `41f9299a…`. `AssessRequest.date: date` has no past-date check. | QA brief: "POST /api/assess with a past date (expect clear 422)"; PRD US-1 "invalid input blocked"; R00 = 422. | Validate date ≥ departure-local today (and sensible max horizon); emit `INVALID_DATE` 422 envelope; add automated test. | Engineer |
| F-02 | Medium | `app/risk.py` / docs | `risk.py:153-155`: "Eligible set for R01 is the geography/overlap/time eligible core…" vs architecture `:297-302` `eligible(e) = trustworthy(e)` and `:313` "eligible set is empty". `risk.py:237-239`: "C01 additionally requires at least one HIGH-reliability trustworthy item…" vs architecture `:328` C01 with no reliability clause. README `:93-96` calls these "reconciliations of internally inconsistent example rows". | Faithful decision table. The code matches §10 S11/S06 but **not** the §8 tables; the spec was fitted to the scenarios, not updated. | Amend §8.1/§8.3 (or revert code and accept §10 failures) with explicit architect approval. Transparent in README, but the binding doc is still wrong. | Engineer / Qi |
| F-03 | Medium | `app/risk.py` | `:260-265` uses `or not core` for C04; architecture `:331` says C04 applies on "no trustworthy evidence". Effect: stale-only evidence (S11) gets MEDIUM, not the table's LOW. This **third** reconciliation is not listed in README `:93-96`. | C04 condition in the table, or a documented reconciliation. | Document the change in architecture + README and add a dedicated confidence test. | Engineer |
| F-04 | Medium | `static/app.js` | `renderEvidence` (`:157-184`) renders provider, signal, relevance, id, severity, freshness, overlap, valid times and source link, but not `reliability`, `observed_at`, `geography` or `raw_excerpt`. Architecture §9 requires the listed evidence fields verbatim; reliability is a decision-table input. | All returned evidence fields needed to audit classification are visible. | Add columns for reliability and observed timestamp (and geography/excerpt). | Engineer |
| F-05 | Low | `app/models.py` | `:26-34` `NO_EVIDENCE_RULE_IDS` adds `C03_MEDIUM_PARTIAL`, `HORIZON_NOTE` and `R00_NO_COVERAGE` alias. Architecture `:204` permits empty `evidence_ids` only for `R00_NO_COVERAGE`. `test_assessment_rejects_unlinked_recommendation` probes only `R04_HIGH` (`tests/test_risk.py:273-299`). Runtime `C03` currently does set IDs (`risk.py:322-338`), so no live impact observed. | Validator invariant exactly as specified. | Narrow the exemption and extend the negative test to C03/HORIZON_NOTE. | Engineer |
| F-06 | Medium | End-to-end value | Live JFK→SFO 2026-11-18: `HTTP 200`, `"evidence_counts":{"AWC":1,"NWS":0}`, one evidence item `AWC_METAR … "temporal_overlap":"NONE"`, `"classification":"INDETERMINATE","confidence":"LOW"`. Same for 2026-11-17. Static cause: `normalize.py:454` METAR validity = obs+1 h; `:421-422` suppresses benign NWS periods; `risk.py:214-220` R07 needs ≥1 trustworthy item per provider. | PRD FR-03 "Healthy run cites both providers"; R07 "affirmative clean coverage required". Network-level contribution is confirmed (two `provider_status` entries); evidence-level contribution is not. | Emit benign coverage evidence or revise R07 for in-horizon coverage; otherwise state this as an MVP limitation in README/UI. | Engineer / Qi |

No Critical findings. Genuine defects (F-01, F-05) are separated from acknowledged/limitation-adjacent issues (F-06 partly covered by architecture §13.3; F-02/F-03 are spec defects, not runtime failures).

## Live test evidence (real output)

Server: `python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8766` (started in background, stopped after tests).

| Request | Status | Short real excerpt |
|---|---|---|
| `curl http://127.0.0.1:8766/api/health` | **200** | `{"status":"ok"}` |
| `curl -X POST ... -d '{"origin":"JFK","destination":"SFO","date":"2026-11-18"}'` | **200** | `time=2.259610s`; `classification: INDETERMINATE confidence: LOW degraded: False`; top-level keys: `assumptions, classification, confidence, coverage_note, degraded, evidence, generated_at, provider_status, recommendations, request_id, route, travel_date, travel_window_utc, triggered_rules` |
| unmapped city `Atlantis` | **422** | `{"code":"UNMAPPED_CITY","message":"'Atlantis' is not a mapped US airport/city. Use a curated city name or IATA code from the form.", …}` |
| past date `2020-01-01` | **200** (expected 422) | `"travel_date":"2020-01-01"`, `"classification":"INDETERMINATE"` — see F-01 |
| malformed date `"not-a-date"` | **422** | `{"code":"INVALID_DATE", "details":{"errors":[{"field":"body.date","message":"Input should be a valid date or datetime…"}]}}` |
| extra: `2026-11-17` | **200** | same INDETERMINATE/LOW and NWS evidence count 0 |
| `curl http://127.0.0.1:8766/` | **200** | 6953 bytes, `text/html`; contains `<section class="scope-notice">`, `<form id="assess-form">`, `FAA operational status: not integrated`, `/static/app.js` |
| `/static/app.js`, `/static/styles.css` | **200**, **200** | 9071 bytes `text/javascript`; 5159 bytes `text/css` |

Additional live assertions:
- `provider_status` length = **2** (`NWS OK 200`, `AWC OK 200`), `degraded:false` — consistent with the model invariant.
- `grep -oiE '"(score|risk_score|probability)"' /tmp/rg_assess.json | wc -l` → **0**. Source grep found no score output field (only provider raw `probabilityOfPrecipitation` in fixtures/raw excerpts).
- Evidence `source_url` in the live response was `https://aviationweather.gov/api/data/metar?ids=KJFK,KSFO&format=json&hours=2` — a real provider URL. No NWS evidence existed in this run, so an NWS evidence URL in a live response remains **unverified**.
- NWS forecast URL provenance: server log for the assessment shows `https://api.weather.gov/points/40.6413,-73.7781` then `https://api.weather.gov/gridpoints/OKX/42,40/forecast`. Direct verification call returned `properties.forecast: https://api.weather.gov/gridpoints/OKX/42,40/forecast` — exact match, not synthesised.

## Verdict

**READY AFTER FIXES.** F-01 is a High-severity input-validation defect that blocks packaging; a past date produces live upstream calls and a 200 response where the QA brief requires a clear 422. F-02/F-03 also leave the binding decision table inconsistent with shipped behaviour, and F-06 means the observed healthy demo did not demonstrate two providers contributing evidence. All 59 unit tests pass and the core pipeline runs locally, so the fixes are bounded; no Critical defect or architectural redesign is required.

## What I would change before real users

1. Reject past dates (and dates beyond the disclosed forecast horizon) at R00 with a `INVALID_DATE` 422 envelope; add a regression test.
2. Resolve F-02–F-03 in `docs/01_architecture.md` so the decision table, §10 scenarios and code agree; add confidence tests for C01/C04 boundaries.
3. Make in-horizon benign coverage auditable so a normal future-date run can reach CLEAR instead of always INDETERMINATE.
4. Show `reliability`, `observed_at` and `geography` in the evidence table; narrow the evidence-free recommendation exemption.
5. Add automated HTTP-layer tests for `/api/assess` (422 envelopes, degraded provider simulation, static serving) — current live checks are manual and non-repeatable.
