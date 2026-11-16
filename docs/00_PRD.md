# RouteGuard — Product Requirements Document

**Owner:** Xu (PM) · **Implementer:** Kou · **Language:** English.

**Sources:** `01_assessment_prep_brief.md` (FDE responsibilities §3, mindset §10 — light use), `02_route_guard_execution_guardrails.md` (binding controls, take precedence), `03_project_assignment_email.md` (logistics, source of truth). No external research needed; no external URLs/access dates cited.

## 1. Purpose & success definition

Ops checks too many places to know if a traveller's US trip will be disrupted (email). RouteGuard gives one view of disruptions, their evidence, and the action to take.

Per guardrails §4, demo succeeds only if: frontend accepts route + date; genuine external API calls execute; ≥2 providers contribute; backend normalizes/validates; engine explains results; evidence displayed; recommendations generated; partial failures transparent; app runs locally; QA validates workflow; ZIP created and verified. Deliver an evidence-driven prototype — not a static dashboard.

## 2. Source-of-truth & assumptions

| Statement | Source | Status |
|---|---|---|
| Commercial US air travel only | Guardrails §1 | Binding guardrail |
| City-to-city = airport-level assessment, not a verified itinerary | Guardrails §1 | Binding guardrail |
| Date = departure airport local calendar date unless specified | Guardrails §1 | Binding guardrail |
| No departure time ⇒ assess travel day, disclose reduced precision | Guardrails §1 | Binding guardrail |
| No invented connections/schedules/routes or flight-specific claims without flight evidence | Guardrails §1 | Binding guardrail |
| No paid services; no fragile scrapers | Email ("don't purchase access"); Guardrails §2 | Verified from assignment email / Binding guardrail |
| Backend-side API calls; no assumed browser CORS; respect limits/identification | Guardrails §2 | Binding guardrail |
| Deterministic classification; risk ≠ confidence; missing ≠ LOW; unverified ≠ CRITICAL | Guardrails §3 | Binding guardrail |
| No maps/animations/AI summaries as core features | Guardrails §4 | Binding guardrail |
| ~3h work; ZIP to info@redalphacyber.com, subject "FDE Assessment - [Your Name]"; explain decisions, assumptions, integrations, AI use, pre-deployment changes | Email | Verified from assignment email |
| Submit within **4 business days from receipt**; receipt date not supplied — do not invent | Email | Verified from assignment email |
| Physical presence in Singapore required if candidate passes | Email | Verified from assignment email |
| Singapore local business calendar (weekends/holidays excluded) | Inference | Assumption |
| Vite + React + MUI + Tailwind; Python backend | Unspecified | Assumption (implementation choice) |
| Fixed city→airport lookup, no live schedule data | Unspecified | Assumption (implementation choice) |

## 3. User stories

| ID | Story | Acceptance criteria |
|---|---|---|
| US-1 | Analyst enters route + date for an assessment | Origin/destination/date accepted; "NY → SF, tomorrow" works; invalid input blocked |
| US-2 | Analyst sees disaggregated evidence | Each item shows provider, value, timestamp/freshness, relevance |
| US-3 | Analyst gets explainable risk | Classification cites triggered decision-table factors; risk and confidence separate; no bare 0–100 score |
| US-4 | Analyst gets actions | Every non-clear result yields ≥1 concrete action tied to evidence |
| US-5 | Analyst sees partial failures | Failed provider shown, result marked degraded, external link offered; no silent empty result |
| US-6 | Derren shows assumption transparency | UI/README state air-travel scope, airport-level basis, whole-day precision |
| US-7 | Derren hands over reproducibly | README run steps; decision table + scenario tests; ZIP manifest |

## 4. Scope boundaries

**In:** US city-pair (airport-level) route + date; ≥2 public providers; backend fetch/normalize/validate; deterministic decision-table classification; evidence display; recommendations; partial-failure transparency; local run; tests; README/ZIP.

**Out:** real-time flight status; booked itinerary/ticket data; flight-specific claims without evidence; invented connections/schedules; paid APIs; fragile scrapers; maps/animations/AI summaries as core; non-US/non-commercial travel; MVP auth/accounts.

## 5. Functional requirements

| ID | Requirement | Pri | Acceptance criterion |
|---|---|---|---|
| FR-01 | Frontend route + date input | P0 | Valid input accepted, bad input blocked, example runs end-to-end |
| FR-02 | Backend proxies genuine external API calls | P0 | No client-side provider calls; live responses observed |
| FR-03 | ≥2 contributing providers | P0 | Healthy run cites both providers |
| FR-04 | Normalization + validation | P0 | Typed schema; malformed/stale records flagged |
| FR-05 | Deterministic explainable classification | P0 | Same input ⇒ same output; decision table in repo; factors shown |
| FR-06 | Evidence display | P0 | Provider, value, freshness, relevance visible |
| FR-07 | Operational recommendations | P0 | ≥1 action per non-clear result, linked to evidence |
| FR-08 | Transparent partial failures | P0 | Failure shown in UI/logs; degraded result returned |
| FR-09 | Local run | P0 | Documented start command works |
| FR-10 | Tests | P0 | Classification scenarios + input validation covered |
| FR-11 | Risk/confidence integrity | P0 | Risk separate; missing never LOW; unverified never CRITICAL |
| FR-12 | City→airport resolution | P1 | Common cities mapped; unmapped input errors clearly |
| FR-13 | In-product assumption disclosure | P1 | Scope and reduced precision shown on results |
| FR-14 | No flight-specific claims | P1 | No flight number/gate/time/connection emitted |
| FR-15 | Optional heuristic index | P2 | Only with documented, tested weights — else omitted |
| FR-16 | BTS historical context | P2 | Labelled historical only, never real-time |

## 6. Non-functional requirements

| Area | Measurable requirement |
|---|---|
| Security | 100% of calls backend-originated (code review); no secrets in client bundle (grep); identifying User-Agent on every call |
| Reliability | ≤10 s timeout, ≤2 retries per call; zero silent empties — provider status in every response; degraded result on partial failure |
| Performance | <15 s p95 locally; providers concurrent |
| Observability | Structured log/request with correlation ID, route, date, provider, status, latency, freshness |
| Maintainability | One adapter interface per provider; decision table + tests in repo; README run in <5 commands |

## 7. Data-source strategy

| Provider | Supplies | Why fit | Constraints / limits | Fallback |
|---|---|---|---|---|
| NWS (api.weather.gov) | Public alerts + forecasts | Free, official, US-wide, no key | Rate limits; User-Agent; point/zone based; forecast ≠ airport ops | Mark unavailable, disclose, use AWC only |
| NOAA Aviation Weather Center | METAR/TAF, advisories | Aviation-specific, public, complements NWS | Parsing complexity; advisories ≠ ops; label as weather | Degrade to NWS only, disclose |
| FAA status/delays | Airport operational delays | Authoritative ops signal | **Conditional only** if reliable programmatic access; no scraping | Disclose limitation + authoritative external link |
| BTS statistics | Long-run delay context | Public background | Historical only | Never real-time; omit if leaking into live result |

Verify endpoints and response shapes before adapters. Never present aviation weather as airport status. Missing FAA integration is acceptable if disclosed.

## 8. Discovery questions (live explanation, not blockers)

| Group | Question |
|---|---|
| Scope | Commercial passengers only, or also cargo/private? |
| Scope | Which US airports/corridors matter most? |
| Data | Which sources does Operations already trust? |
| Data | What identification/rate limits must we respect? |
| Timing | Day-of, 24-hour, or multi-day need? |
| Timing | Is departure time normally known, or whole-day precision? |
| Actions | What can Ops do — rebook, reroute, notify, monitor — and who owns it? |
| Success metrics | What builds trust — false alarms, coverage, latency? |

## 9. Demo narrative

1. **Problem:** Ops checks too many places; one disruption view with evidence and actions.
2. **Input:** NY → SF, tomorrow. State assumptions: commercial US air, airport-level not itinerary, departure-airport local date.
3. **Live calls:** Show backend executing NWS + AWC; name providers and identification headers.
4. **Evidence:** Walk items — source, value, freshness, geographic/temporal relevance.
5. **Classification:** Explain decision table (severity, geography, temporal overlap, reliability, freshness, corroboration); risk separate from confidence; missing ≠ LOW, unverified ≠ CRITICAL.
6. **Actions + failure:** Show recommendations; simulate one provider down; show degraded result + authoritative link.
7. **AI use:** AI as development aid — adapter scaffolding, decision-table/test and doc drafting. Runtime classification is deterministic; no AI claims or AI summary in the product.
8. **Before production:** Verify endpoints; add auth, caching, rate limits, monitoring; add FAA only if reliable; real itineraries/times; calibrate any index; keep human escalation.

## 10. Definition of Done

- [ ] Frontend accepts route + date
- [ ] Genuine external API requests executed
- [ ] ≥2 providers contribute
- [ ] Backend normalizes/validates
- [ ] Engine produces explainable results
- [ ] Evidence displayed
- [ ] Recommendations generated
- [ ] Partial failures transparent
- [ ] Runs locally
- [ ] QA validates full workflow
- [ ] ZIP created and verified
- [ ] Decision table + scenario tests documented
- [ ] Air-travel assumption + reduced precision disclosed
- [ ] No paid services or fragile scrapers
