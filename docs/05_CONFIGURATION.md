# RouteGuard — API Keys and Environment Variables

**Status (16 November 2026): no API key is required to run this prototype.**

Every integrated provider is public, undocumented-key-free and non-commercial-use friendly. Nothing needs to be purchased, and there is no `.env` file to create.

## 1. Keys: none

| Provider | Used for | API key | Why |
|---|---|---|---|
| National Weather Service (`api.weather.gov`) | US alerts + gridpoint forecast | **None** | Public US government API. Requires an identifying `User-Agent` by policy. |
| NOAA Aviation Weather Center (`aviationweather.gov/api/data`) | Global METAR + TAF | **None** | Public NOAA data API. Requires a custom `User-Agent` by policy; documented limit 100 requests/min. |
| Open-Meteo (`api.open-meteo.com`) | Non-US current conditions + hourly forecast | **None** | Free public forecast API for non-commercial use; no key is requested by the documented endpoint. |

FAA operational status is **not** integrated. Do not look for an FAA key: no supported no-key programmatic feed was found. The UI links to `https://nasstatus.faa.gov/` and `https://www.fly.faa.gov/flyfaa/usmap.jsp` as out-of-app verification steps only.

## 2. Environment variables

| Variable | Required | Default | Effect |
|---|---|---|---|
| `ROUTEGUARD_CONTACT_EMAIL` | Optional — **recommended** | `derren@example.com` | Sets the contact address embedded in the `User-Agent` header on 100% of outbound provider calls. Both NWS and AWC ask for identification. Set it to a real address before demonstrating repeatedly. |

Example:

```bash
export ROUTEGUARD_CONTACT_EMAIL="you@example.com"
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

No other environment variable is read by the application. Host and port are uvicorn command-line options, not application settings. All timeouts, retry counts, provider URLs, freshness thresholds and authoritative fallback links are constants in `app/config.py`.

## 3. What is deliberately not configurable yet

- No authentication, API gateway, secrets store or per-user rate limiting.
- No database or cache; provider `Cache-Control` headers are honoured by the HTTP client only insofar as the client does not defeat them.
- No LLM key: RouteGuard has no model call at runtime. Classification is deterministic.
- No paid data provider, no scraper, no protected-account access.

## 4. Current focus and global extension

- **Current/default focus:** 48 curated United States airports. When the departure airport is in the United States, the weather provider is NWS and the aviation provider is AWC.
- **Global extension:** 27 additional curated airports across 25 other countries/regions, including Hong Kong, China. When the departure airport is outside the United States, the weather provider is Open-Meteo and the aviation provider remains AWC (its METAR/TAF network is international).
- The route's cities, countries and active weather provider are displayed in the journey panel and decision trace. Absence of an official national alert feed outside the US is stated in the coverage note.
