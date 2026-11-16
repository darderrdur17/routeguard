# RouteGuard — API verification evidence log

**Access date:** 2026-11-16 (all live calls). **Method:** `curl` with identifying `User-Agent: RouteGuardPrototype/0.1 (contact: derren@example.com)` unless stated otherwise; official documentation fetched with WebFetch; OpenAPI specs downloaded and parsed locally.

**Tags:** `[LIVE]` = HTTP response observed from this environment; `[DOC]` = official documentation text/spec observed; `[UNVERIFIED]` = not confirmed. Short excerpts below are verbatim substrings of actual responses; **nothing here is a invented sample presented as observed**. Full raw responses are not committed; the excerpts are sufficient for adapter field names.

---

## 1. NWS — api.weather.gov

### 1.1 Documentation observed `[DOC]`

| Source URL | Access date | What was read |
|---|---|---|
| `https://www.weather.gov/documentation/services-web-api` | 2026-11-16 | Pricing: "open data, free to use for any purpose"; rate limit "not public information", exceeded requests return an error, "may be retried after the limit clears (typically within 5 seconds)"; Authentication example: `User-Agent: (myweatherapp.com, contact@myweatherapp.com)`; endpoints `https://api.weather.gov/points/{latitude},{longitude}`, `/gridpoints/{office}/{gridX},{gridY}/forecast`, `/alerts/active?area={state}`. |
| `https://weather-gov.github.io/api/general-faqs` | 2026-11-16 | On 403: "Make sure your program is including a `User-Agent` header in your request. We recommend setting the value to something that identifies your application and includes a contact email." Coordinates: "doesn't support more than four decimal places of precision". Caching: "Please don't use cache busting techniques like random numbers in the query string" (400 for unrecognised params). `/points` result is cacheable. |
| `https://api.weather.gov/openapi.json` | 2026-11-16 (122,897 bytes) | Paths `/points/{latitude},{longitude}`, `/gridpoints/{wfo}/{x},{y}/forecast`, `/alerts/active`. `components.parameters.AlertPoint`: `name: point`, `in: query`, description "Point (latitude,longitude)… incompatible with… area, region, region_type, zone". `AlertSeverity` enum: extreme, severe, moderate, minor, unknown. `[DOC]` |

### 1.2 Live observations

| # | URL | Status / headers `[LIVE]` | Verbatim excerpt `[LIVE]` | Note |
|---|---|---|---|---|
| N1 | `https://api.weather.gov/points/37.6213,-122.3790` | **200**; `content-type: application/geo+json`; `cache-control: public, max-age=72034, s-maxage=86400`; `date: Mon, 16 Nov 2026 06:39:51 GMT`; `x-request-id: 01a1e23a-27ef-73f6-80df-2cfc8031a63e`; `x-correlation-id: 5f059b46` | `"type": "Feature"`, `"cwa": "MTR"`, `"gridId": "MTR"`, `"gridX": 85`, `"gridY": 98`, `"forecast": "https://api.weather.gov/gridpoints/MTR/85,98/forecast"`, `"forecastHourly": "https://api.weather.gov/gridpoints/MTR/85,98/forecast/hourly"`, `"relativeLocation": {… "city": "South San Francisco", "state": "CA" …}`, `"forecastZone": "https://api.weather.gov/zones/forecast/CAZ508"` | Identifying UA present. Returned `id` uses 4-decimal latitude / 3-decimal longitude: `"https://api.weather.gov/points/37.6213,-122.379"`. |
| N2 | `https://api.weather.gov/points/37.6213,-122.3790` with `-A curl/8.0` (no identifying contact) | **200**; body starts `"@context": ["https://geojson.org/geojson-ld/geojson-context.jsonld", …]` | — | Identification is a **documented requirement/policy** `[DOC]`; denial was **not observed** here. Adapter still sends it unconditionally. |
| N3 | `https://api.weather.gov/alerts/active?point=37.6213,-122.3790` | **200**; `cache-control: public, max-age=5, s-maxage=5`; `date: Mon, 16 Nov 2026 06:40:07 GMT`; length 233 | `{"@context":{"@version":"1.1"},"type":"FeatureCollection","features":[],"title":"Current watches, warnings, and advisories for 37.6213 N, 122.379 W","updated":"2026-11-16T06:37:40+00:00"}` | Empty `features` with 200. Confirms point query syntax works and is compliant with OpenAPI `point` param. |
| N4 | `https://api.weather.gov/alerts/active?point=34.23,-119.20` | **200**; `features` length 1 | `"event": "High Surf Advisory"`, `"severity": "Minor"`, `"areaDesc": "Ventura County Beaches"`, `"expires": "2026-11-16T10:00:00-08:00"` | Point filtering works server-side. |
| N5 | `https://api.weather.gov/alerts/active?area=CA` (used only to inspect full feature shape) | **200**; 26 features; `date: Mon, 16 Nov 2026 06:40:07 GMT` | Feature top keys: `id`, `type`, `geometry`, `properties`. `geometry` was **`null`** on the first feature. `properties` keys: `id`, `areaDesc`, `geocode`, `affectedZones`, `references`, `sent`, `effective`, `onset`, `expires`, `ends`, `status`, `messageType`, `category`, `severity`, `certainty`, `urgency`, `event`, `sender`, `senderName`, `headline`, `description`, `instruction`, `response`, `note`, `parameters`, `scope`, `code`, `language`, `web`, `eventCode`. Verbatim values: `"severity": "Minor"`, `"certainty": "Likely"`, `"urgency": "Expected"`, `"status": "Actual"`, `"messageType": "Update"`, `"geocode": {"SAME": ["006111"], "UGC": ["CAZ354"]}`. | Do **not** require non-null geometry; rely on server point filtering + `geocode.UGC` / `affectedZones`. |
| N6 | `https://api.weather.gov/gridpoints/MTR/85,98/forecast` (URL taken from N1, not guessed) | **200**; `content-type: application/geo+json`; `cache-control: public, max-age=2463, s-maxage=3600`; `last-modified: Mon, 16 Nov 2026 04:37:23 GMT`; length 14,023 | `"units": "us"`, `"forecastGenerator": "BaselineForecastGenerator"`, `"generatedAt": "2026-11-16T05:27:03+00:00"`, `"updateTime": "2026-11-16T04:37:23+00:00"`, `"validTimes": "2026-11-15T22:00:00+00:00/P7DT3H"`. Period 2: `"number": 2`, `"name": "Monday"`, `"startTime": "2026-11-16T06:00:00-08:00"`, `"endTime": "2026-11-16T18:00:00-08:00"`, `"probabilityOfPrecipitation": {"unitCode": "wmoUnit:percent", "value": 53}`, `"windSpeed": "5 to 16 mph"`, `"shortForecast": "Chance Light Rain"`. | Horizon ≈7 days from `validTimes` `[LIVE]`; beyond that the adapter must report no coverage, not LOW risk. |

**Unverified for NWS:** exact numeric rate-limit ceiling (`[DOC]` explicitly says not public); behaviour under 403/429 from this environment; whether `features[].geometry` is always null for zone-based alerts (only one null observed).

---

## 2. NOAA Aviation Weather Center — aviationweather.gov/data/api

### 2.1 Documentation observed `[DOC]`

| Source URL | Access date | What was read |
|---|---|---|
| `https://aviationweather.gov/data/api/` | 2026-11-16 | Products table lists METAR (JSON), TAF (JSON), G-AIRMETs (JSON/GeoJSON/XML), CWA, SIGMETs. "Set a custom user agent to prevent automated filtering inadvertently blocking valid traffic." "Wait between consecutive requests — maximum 100 requests per minute." "Most endpoints return a maximum of 400 entries." "Cross-origin resource sharing is not permitted at this time." "Undocumented query parameter requests are restricted and will result in an error." 204 = "valid request however there is no data". 429 = too many requests. Database allows "up to the previous 30 days of data". |
| `https://aviationweather.gov/data/schema/openapi.yaml` | 2026-11-16 (93,112 bytes) | Paths `/api/data/metar`, `/taf`, `/gairmet`, `/cwa`, `/airsigmet`, `/sigmet`, etc. METAR params: `ids`, `bbox`, `format` (raw/decoded/json/geojson/xml/iwxxm), `taf`, `hours`, `date`. TAF params: `ids`, `bbox`, `format` (raw/json/geojson/xml/iwxxm), `metar`, `time=valid|issue`, `date` — **no `hours` param**. `bbox`: "Geographic bounding box (lat0, lon0, lat1, lon1) with a maximum of three decimals". `hours`: "Hours back to search". G-AIRMET params: `product` (sierra/tango/zulu), `hazard` (turb-hi,turb-lo,llws,sfc-wind,ifr,mtn-obs,ice,fzlvl), `fore` (0/3/6/9/12), `date`, `format`. |

### 2.2 Live observations

| # | URL | Status / headers `[LIVE]` | Verbatim excerpt `[LIVE]` | Note |
|---|---|---|---|---|
| A1 | `https://aviationweather.gov/api/data/metar?ids=KSFO&format=json&hours=2` | **200**; `content-type: application/json; charset=utf-8`; `cache-control: max-age=60`; `date: Mon, 16 Nov 2026 06:39:53 GMT`; length 1152 | JSON array of 2 objects. First object keys: `icaoId`, `receiptTime`, `obsTime`, `reportTime`, `temp`, `dewp`, `wdir`, `wspd`, `visib`, `altim`, `slp`, `qcField`, `wxString`, `presTend`, `maxT`, `minT`, `precip`, `pcp6hr`, `metarType`, `rawOb`, `lat`, `lon`, `elev`, `name`, `cover`, `clouds`, `fltCat`. Values: `"icaoId":"KSFO"`, `"reportTime":"2026-11-16T06:00:00.000Z"`, `"obsTime":1794808560`, `"visib":9`, `"wxString":"-RA"`, `"fltCat":"VFR"`, `"cover":"OVC"`, `"clouds":[{"cover":"SCT","base":1100},{"cover":"OVC","base":6500}]`, `"name":"San Francisco Intl, CA, US"`. | `hours=2` accepted, despite being a METAR-only documented param. `obsTime` is epoch seconds. |
| A2 | `https://aviationweather.gov/api/data/taf?ids=KSFO&format=json` | **200**; `content-type: application/json; charset=utf-8`; `cache-control: max-age=60`; `date: Mon, 16 Nov 2026 06:40:10 GMT`; length 2333 | JSON array. First object keys: `icaoId`, `dbPopTime`, `bulletinTime`, `issueTime`, `validTimeFrom`, `validTimeTo`, `rawTAF`, `mostRecent`, `remarks`, `lat`, `lon`, `elev`, `prior`, `name`, `fcsts`. Values: `"issueTime":"2026-11-16T05:43:00.000Z"`, `"validTimeFrom":1794808800`, `"validTimeTo":1794916800`, `"mostRecent":1`. `fcsts[0]` keys include `timeFrom`, `timeTo`, `timeBec`, `fcstChange`, `probability`, `wdir`, `wspd`, `wgst`, `visib`, `wxString`, `clouds`, `icgTurb`, `temp`; values `"visib":"6+"`, `"wxString":"-SHRA"`, `"wdir":330`, `"wspd":8`. | Validity ≈30 h. `visib` is a **string** in TAF but a **number** in METAR — normalizer must handle both. |
| A3 | `https://aviationweather.gov/api/data/gairmet?bbox=-123,36,-120,39&format=json` | **200**; length 40,699 | Array of **45** objects. Keys: `tag`, `forecastHour`, `validTime`, `hazard`, `geometryType`, `latlonpairs`, `frequency`, `severity`, `due_to`, `status`, `top`, `base`, `fzltop`, `fzlbase`, `level`, `receiptTime`, `issueTime`, `expireTime`, `product`, `geom`, `coords`. First: `"tag":"1C"`, `"hazard":"FZLVL"`, `"product":"ZULU"`, `"geom":"LINE"`, `"coords":[{"lat":"39.37","lon":"-106.63"}, …]`, `"severity":null`. | Returned records in Colorado/Idaho, **outside** the requested California box. |
| A4 | `https://aviationweather.gov/api/data/gairmet?format=json` | **200** | Array of **45** objects; first keys and first hazard/product/coords identical to A3. | **Observed `bbox` had no filtering effect.** Treat server-side bbox filtering as unreliable `[LIVE]`; any future use must filter polygons client-side. |
| A5 | `https://aviationweather.gov/api/data/cwa?bbox=-123,36,-120,39&format=json` | **204 No Content**, empty body, `cache-control: max-age=60` | — | Valid request, no active advisories at access time. |
| A6 | `https://aviationweather.gov/api/data/airsigmet?bbox=-123,36,-120,39&format=json` | **204 No Content**, empty body, `cache-control: max-age=180` | — | Same. |
| A7 | `https://aviationweather.gov/api/data/cwa?format=json` | **204**, size 0 | — | Confirms A5 was not a bbox artefact. |
| A8 | `https://aviationweather.gov/api/data/airsigmet?format=json` | **204**, size 0 | — | Confirms A6. |

**Unverified for AWC:** actual rate-limit enforcement behaviour (429 not triggered); whether `bbox` filtering works for METAR/TAF (only tested on G-AIRMET); full set of `fltCat` values (only `VFR` observed); error JSON body shape for 400 (only `[DOC]` standardised error statement, no `[LIVE]` error body).

---

## 3. FAA — deliberate non-integration

| # | URL / source | Status `[LIVE]` vs `[DOC]` | Verbatim excerpt | Finding |
|---|---|---|---|---|
| F1 | `https://www.faa.gov/air_traffic/flight_info` (WebFetch) | `[DOC]` page last updated Friday, January 27, 2023 | Links: "Airport Status & Delays (real time)" → `https://www.fly.faa.gov/flyfaa/usmap.jsp`; "National Airspace System Status" → `https://www.fly.faa.gov/ois/`. "Top Tasks → Check airport status & delays" → same `usmap.jsp`. | **No developer API, JSON/XML feed, documentation, or terms for programmatic use is published on the official FAA flight-info page.** |
| F2 | `https://www.faa.gov/travelers/prepare_fly` (search result) | `[DOC]` | "Check NASstatus.faa.gov to view flight delays and airport status." | Human-facing guidance only. |
| F3 | `https://nasstatus.faa.gov/api/airport-status-information` | **200**, `Content-Type: application/xml`, 1532 bytes, `date: Mon, 16 Nov 2026 06:41:12 GMT`, `Cache-Control: no-cache, no-store, must-revalidate` `[LIVE]` | `<AIRPORT_STATUS_INFORMATION><Update_Time>Mon Nov 16 06:41:12 2026 GMT</Update_Time><Dtd_File>http://www.fly.faa.gov/AirportStatus.dtd</Dtd_File><Delay_type><Name>Ground Delay Programs</Name><Ground_Delay_List><Ground_Delay><ARPT>SFO</ARPT><Reason>low ceilings</Reason><Avg>2 hours and 46 minutes</Avg><Max>14 hours and 55 minutes</Max></Ground_Delay></Ground_Delay_List></Delay_type><Delay_type><Name>Airport Closures</Name><Airport_Closure_List><Airport><ARPT>SNA</ARPT><Reason>!SNA 11/020 SNA AD AP CLSD DLY 0730-1415 2611150730-2611211415</Reason>…` (excerpt truncated; full response contained `Start`, `Reopen`, and additional `ARPT` entries for LAX, SAN, LAS) | Endpoint is **reachable but undocumented** `[UNVERIFIED as supported API]`. XML, legacy DTD, mixes long-term GA closures with active ground-delay programs. **Decision: do not integrate.** No HTML scraping proposed. |
| F4 | `https://nasstatus.faa.gov/` | **200**, `Content-Type: text/html;charset=UTF-8`, React app shell (`<title>National Airspace System</title>`) `[LIVE]` | — | Human-facing dashboard; confirms authoritative link target. |

**FAA conclusion:** no reliable, **documented**, no-key programmatic feed could be confirmed. RouteGuard will not present FAA data as evidence. UI shows authoritative links: `https://nasstatus.faa.gov/` and `https://www.fly.faa.gov/flyfaa/usmap.jsp`.

---

## 4. Consolidated verification verdict

| Integration | Verdict | Rationale |
|---|---|---|
| NWS alerts by point | **INTEGRATE** | `[DOC]` OpenAPI `point` param + `[LIVE]` 200 with real feature schema and real empty case |
| NWS points + gridpoint forecast | **INTEGRATE** | `[DOC]` 2-step flow + `[LIVE]` 200; horizon explicitly observed as `P7DT3H` |
| AWC METAR + TAF by ICAO, JSON | **INTEGRATE** | `[DOC]` documented params/formats + `[LIVE]` 200 arrays with real field names |
| AWC G-AIRMET | **VERIFIED, NOT INTEGRATED (MVP)** | `[LIVE]` 200, but bbox ignored and polygon filtering out of MVP scope |
| AWC CWA / SIGMET | **VERIFIED AVAILABLE (204), NOT INTEGRATED** | No data at access time; schema documented but no live payload observed |
| FAA airport status/delays | **NOT INTEGRATED** | Undocumented legacy XML only; guardrails require documented reliability and forbid scrapers |
| BTS historical statistics | **EXCLUDED** | No real-time value; guardrails allow only as clearly labelled context |
