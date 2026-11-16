/* RouteGuard — V29-inspired intelligence workspace.
   Vanilla JS, no build step. Every server string is inserted with textContent or
   createElement. No client-side classification, no fabricated data, no simulated
   progress. MapLibre is progressive enhancement; the SVG map remains a fallback. */
(function () {
  "use strict";

  var SVG_NS = "http://www.w3.org/2000/svg";
  var MAP_STYLE_URL = "https://tiles.openfreemap.org/styles/positron";
  var MAP_BOUNDS = { lonMin: -125, lonMax: -66, latMin: 24, latMax: 50 };

  var state = {
    current: null,
    airports: [],
    view: "all",
    filter: "all",
    highlighted: null,
    selectedEvidenceId: null,
    activeAirport: null,
    previousClassification: null,
    lastPayload: null,
    lastRouteKey: "",
    busy: false,
    mode: "overview",
    map: null,
    mapReady: false,
    popup: null,
    markers: { airports: [], weather: [], aviation: [] },
    fallbackView: { cx: 400, cy: 210, zoom: 1 },
    toastTimer: null,
    fullscreenBefore: null,
  };

  var dom = {
    form: document.getElementById("assess-form"),
    origin: document.getElementById("origin"),
    destination: document.getElementById("destination"),
    date: document.getElementById("travel-date"),
    originCode: document.getElementById("origin-code"),
    destinationCode: document.getElementById("destination-code"),
    datalist: document.getElementById("airport-options"),
    submit: document.getElementById("submit-button"),
    swap: document.getElementById("swap-button"),
    refresh: document.getElementById("refresh-button"),
    error: document.getElementById("form-error"),
    empty: document.getElementById("empty-state"),
    emptyTitle: document.getElementById("empty-title"),
    emptySubtitle: document.getElementById("empty-subtitle"),
    results: document.getElementById("results"),
    loadingPill: document.getElementById("loading-pill"),
    loadingAnnouncement: document.getElementById("loading-announcement"),
    loadingSkeleton: document.getElementById("loading-skeleton"),
    freshness: document.getElementById("freshness-chip"),
    updatedAt: document.getElementById("updated-at"),
    coverageBadge: document.getElementById("coverage-badge"),
    requestShort: document.getElementById("request-short"),
    modeOverview: document.getElementById("mode-overview"),
    modeAnalyst: document.getElementById("mode-analyst"),
    viewBar: document.querySelector(".view-bar"),
    classification: document.getElementById("classification"),
    classificationNote: document.getElementById("classification-note"),
    verdictCore: document.getElementById("verdict-core"),
    confidence: document.getElementById("confidence"),
    degraded: document.getElementById("degraded"),
    evidenceCount: document.getElementById("evidence-count"),
    coverageNote: document.getElementById("coverage-note"),
    weatherSummary: document.getElementById("weather-summary"),
    aviationSummary: document.getElementById("aviation-summary"),
    operationsSummary: document.getElementById("operations-summary"),
    recommendations: document.getElementById("recommendations"),
    rules: document.getElementById("triggered-rules"),
    assumptions: document.getElementById("assumptions"),
    mapStage: document.getElementById("map-stage"),
    mapCanvas: document.getElementById("map-canvas"),
    map: document.getElementById("route-map"),
    mapTooltip: document.getElementById("map-tooltip"),
    mapReset: document.getElementById("map-reset"),
    mapFullscreen: document.getElementById("map-fullscreen"),
    layerAirports: document.getElementById("layer-airports"),
    layerRoutes: document.getElementById("layer-routes"),
    layerWeather: document.getElementById("layer-weather"),
    layerAviation: document.getElementById("layer-aviation"),
    layerOperations: document.getElementById("layer-operations"),
    mapLegend: document.getElementById("map-legend"),
    timeline: document.getElementById("timeline"),
    travelBand: document.getElementById("travel-band"),
    distribution: document.getElementById("distribution"),
    filters: document.getElementById("evidence-filters"),
    evidenceList: document.getElementById("evidence-list"),
    evidenceEmpty: document.getElementById("evidence-empty"),
    providers: document.getElementById("provider-status"),
    contextRouteTitle: document.getElementById("context-route-title"),
    contextRouteSub: document.getElementById("context-route-sub"),
    contextOriginCode: document.getElementById("context-origin-code"),
    contextOriginCity: document.getElementById("context-origin-city"),
    contextDestinationCode: document.getElementById("context-destination-code"),
    contextDestinationCity: document.getElementById("context-destination-city"),
    contextDate: document.getElementById("context-date"),
    contextProviders: document.getElementById("context-providers"),
    contextFocus: document.getElementById("context-focus"),
    contextSelectionTitle: document.getElementById("context-selection-title"),
    contextSelectionBody: document.getElementById("context-selection-body"),
    contextDetailButton: document.getElementById("context-detail-button"),
    priorityFindings: document.getElementById("priority-findings"),
    contextSources: document.getElementById("context-sources"),
    toast: document.getElementById("toast"),
    drawer: document.getElementById("evidence-drawer"),
    drawerOverlay: document.getElementById("drawer-overlay"),
    drawerTitle: document.getElementById("drawer-title"),
    drawerBody: document.getElementById("drawer-body"),
    drawerClose: document.getElementById("drawer-close"),
    drawerMap: document.getElementById("drawer-map"),
    drawerSource: document.getElementById("drawer-source"),
    palette: document.getElementById("command-palette"),
    paletteOverlay: document.getElementById("palette-overlay"),
    paletteOpen: document.getElementById("palette-open"),
    paletteInput: document.getElementById("palette-input"),
    paletteResults: document.getElementById("palette-results"),
    paletteKey: document.getElementById("palette-key"),
  };

  /* ---------- primitives ---------- */

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function svg(tag, attrs) {
    var node = document.createElementNS(SVG_NS, tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (key) {
        node.setAttribute(key, String(attrs[key]));
      });
    }
    return node;
  }

  function clear(node) {
    while (node && node.firstChild) node.removeChild(node.firstChild);
  }

  function show(node, visible) {
    if (node) node.hidden = !visible;
  }

  function reducedMotion() {
    return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  function fmtInstant(value) {
    if (!value) return "—";
    var parsed = new Date(value);
    if (isNaN(parsed.getTime())) return String(value);
    return parsed.toISOString().replace("T", " ").slice(0, 16) + "Z";
  }

  function shortInstant(value) {
    if (!value) return "—";
    var parsed = new Date(value);
    if (isNaN(parsed.getTime())) return String(value);
    return parsed.toISOString().slice(5, 16).replace("T", " ");
  }

  function truncate(value, length) {
    var text = value === undefined || value === null ? "" : String(value);
    return text.length > length ? text.slice(0, length - 1) + "…" : text;
  }

  function safeUrl(value, fallback) {
    try {
      var parsed = new URL(String(value), window.location.href);
      if (parsed.protocol === "https:" || parsed.protocol === "http:") return parsed.href;
    } catch (error) {
      return fallback;
    }
    return fallback;
  }

  function tomorrowLocal() {
    var now = new Date();
    var next = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
    return [
      next.getFullYear(),
      String(next.getMonth() + 1).padStart(2, "0"),
      String(next.getDate()).padStart(2, "0"),
    ].join("-");
  }

  function toast(message) {
    dom.toast.textContent = message;
    show(dom.toast, true);
    window.clearTimeout(state.toastTimer);
    state.toastTimer = window.setTimeout(function () {
      show(dom.toast, false);
    }, 4200);
  }

  function findAirport(query) {
    if (!query) return null;
    var needle = String(query).trim().toLowerCase().replace(/\s*\(.*\)\s*$/, "");
    for (var i = 0; i < state.airports.length; i += 1) {
      var a = state.airports[i];
      if (
        needle === a.city.toLowerCase() ||
        needle === a.iata.toLowerCase() ||
        needle === a.icao.toLowerCase() ||
        needle === (a.city + " (" + a.iata + ")").toLowerCase()
      ) {
        return a;
      }
    }
    return null;
  }

  function syncCodes() {
    var origin = findAirport(dom.origin.value);
    var destination = findAirport(dom.destination.value);
    dom.originCode.textContent = origin ? origin.iata : "—";
    dom.destinationCode.textContent = destination ? destination.iata : "—";
  }

  function evidenceById(id) {
    if (!state.current || !id) return null;
    return (state.current.evidence || []).filter(function (item) { return item.id === id; })[0] || null;
  }

  function isWeather(item) {
    return item.provider === "NWS" || item.provider === "OPEN_METEO";
  }

  function isAviation(item) {
    return item.provider === "AWC";
  }

  function hasCoords(item) {
    return item && item.latitude !== null && item.longitude !== null &&
      isFinite(item.latitude) && isFinite(item.longitude);
  }

  var SEVERITY_RANK = { UNKNOWN: 0, MINOR: 1, MODERATE: 2, SEVERE: 3, EXTREME: 4 };

  /* ---------- view and filter state ---------- */

  var VIEW_TESTS = {
    all: function () { return true; },
    routes: function (item) { return item.geography === "EXACT" || !!item.location_label; },
    weather: isWeather,
    operations: function () { return false; },
    advisories: function () { return false; },
    high: function (item) { return item.severity === "SEVERE" || item.severity === "EXTREME"; },
  };

  var VIEW_EMPTY = {
    operations: "No verified airport operational feed is integrated. Check the authority links in Data sources.",
    advisories: "No verified aviation advisory feed is integrated. METAR and TAF evidence remains available in the Aviation card.",
    routes: "No endpoint-attributed evidence was returned for this route.",
    weather: "No weather evidence was returned for this route.",
    high: "No high-priority evidence was returned for this route.",
    all: "No evidence was returned for this route.",
  };

  function baseEvidence() {
    if (!state.current) return [];
    var all = state.current.evidence || [];
    return all.filter(VIEW_TESTS[state.view] || VIEW_TESTS.all);
  }

  var FILTERS = [
    { id: "all", label: "All signals", test: function () { return true; } },
    { id: "weather", label: "Weather", test: isWeather },
    { id: "aviation", label: "METAR / TAF", test: isAviation },
    { id: "forecast", label: "Forecast", test: function (e) { return !!e.valid_from && e.temporal_overlap !== "NONE"; } },
    { id: "confirmed", label: "Observed", test: function (e) { return !!e.observed_at && e.freshness === "FRESH"; } },
    { id: "severe", label: "Severe+", test: function (e) { return e.severity === "SEVERE" || e.severity === "EXTREME"; } },
  ];

  function filteredEvidence() {
    var active = FILTERS.filter(function (f) { return f.id === state.filter; })[0] || FILTERS[0];
    return baseEvidence().filter(active.test);
  }

  function renderViewPills() {
    Array.prototype.forEach.call(dom.viewBar.querySelectorAll(".view-pill"), function (button) {
      var active = button.getAttribute("data-view") === state.view;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    });
  }

  function applyView(view) {
    state.view = view;
    state.highlighted = null;
    state.selectedEvidenceId = null;
    renderViewPills();
    if (!state.current) return;
    renderEvidence(state.current);
    renderSignalCards(state.current);
    renderContext(state.current);
    renderMap(state.current);
  }

  function renderMode() {
    document.body.setAttribute("data-mode", state.mode);
    dom.modeOverview.classList.toggle("is-active", state.mode === "overview");
    dom.modeAnalyst.classList.toggle("is-active", state.mode === "analyst");
    dom.modeOverview.setAttribute("aria-pressed", String(state.mode === "overview"));
    dom.modeAnalyst.setAttribute("aria-pressed", String(state.mode === "analyst"));
  }

  /* ---------- summary and cards ---------- */

  var CLASS_NOTES = {
    CLEAR: "Affirmative coverage from both sources; no adverse eligible signal.",
    LOW: "Limited adverse signal; routine monitoring is sufficient.",
    ELEVATED: "A moderate or downgraded signal needs attention.",
    HIGH: "A severe signal or an uncorroborated extreme signal was found.",
    CRITICAL: "Extreme signal corroborated by both independent providers.",
    INDETERMINATE: "No conclusive in-horizon coverage — absence of alerts is not a clean bill of health.",
  };

  function renderSummary(data) {
    var route = data.route || {};
    dom.requestShort.textContent = String(data.request_id || "—").slice(0, 8);
    dom.updatedAt.textContent = "Updated " + fmtInstant(data.generated_at);
    dom.freshness.textContent = "Updated " + shortInstant(data.generated_at) + "Z";
    dom.freshness.classList.toggle("is-live", !data.degraded);
    dom.freshness.classList.toggle("is-stale", !!data.degraded);

    document.getElementById("origin-iata").textContent = route.origin_iata || "—";
    document.getElementById("origin-city").textContent = route.origin_city || "—";
    document.getElementById("origin-country").textContent = route.origin_country || "—";
    document.getElementById("origin-meta").textContent =
      [route.origin_state, route.origin_icao, route.origin_timezone].filter(Boolean).join(" · ");
    document.getElementById("destination-iata").textContent = route.destination_iata || "—";
    document.getElementById("destination-city").textContent = route.destination_city || "—";
    document.getElementById("destination-country").textContent = route.destination_country || "—";
    document.getElementById("destination-meta").textContent =
      [route.destination_state, route.destination_icao, route.destination_timezone].filter(Boolean).join(" · ");

    var providerLabel = route.weather_provider === "NWS" ? "NWS + AWC" : "Open-Meteo + AWC";
    dom.coverageBadge.textContent = (route.coverage_focus || "Global") + " · " + providerLabel;

    document.getElementById("fact-date").textContent = data.travel_date || "—";
    document.getElementById("fact-window").textContent =
      shortInstant((data.travel_window_utc || {}).start) + " → " +
      shortInstant((data.travel_window_utc || {}).end) + " UTC";
    document.getElementById("fact-basis").textContent = route.basis || "airport-level";

    var firstRender = state.previousClassification === null;
    var changed = !firstRender && state.previousClassification !== data.classification;
    dom.classification.textContent = data.classification || "—";
    dom.classification.className = "classification " + (data.classification || "");
    if (firstRender || changed) {
      dom.classification.style.animation = "none";
      void dom.classification.offsetWidth;
      dom.classification.style.animation = "";
    } else {
      dom.classification.style.animation = "none";
    }
    dom.classificationNote.textContent = CLASS_NOTES[data.classification] || "See decision trace.";
    dom.confidence.textContent = data.confidence || "—";
    dom.degraded.textContent = data.degraded ? "DEGRADED" : "ALL SOURCES OK";
    dom.evidenceCount.textContent = String((data.evidence || []).length);
    dom.coverageNote.textContent = data.coverage_note || "";
    if (changed) toast("Classification changed: " + state.previousClassification + " → " + data.classification);
    state.previousClassification = data.classification;
    renderAirportBlocks();
  }

  function renderAirportBlocks() {
    document.querySelectorAll(".airport-block").forEach(function (node) {
      node.classList.toggle("is-active", node.getAttribute("data-airport") === state.activeAirport);
    });
  }

  function signalRow(label, value, chipClass) {
    var row = el("div", "signal-row");
    row.appendChild(el("span", "", label));
    if (chipClass) row.appendChild(el("span", "signal-chip " + chipClass, value));
    else row.appendChild(el("strong", "", value));
    return row;
  }

  function renderSignalCards(data) {
    var items = baseEvidence();
    var weather = items.filter(isWeather);
    var aviation = items.filter(isAviation);
    clear(dom.weatherSummary);
    clear(dom.aviationSummary);
    clear(dom.operationsSummary);

    dom.weatherSummary.appendChild(signalRow("Retrieved signals", String(weather.length)));
    dom.weatherSummary.appendChild(signalRow("Highest severity", highestSeverity(weather), severityChip(weather)));
    dom.weatherSummary.appendChild(signalRow("Weather providers", uniqueProviders(weather) || "none"));

    var metar = aviation.filter(function (e) { return e.signal_type === "AWC_METAR"; }).length;
    var taf = aviation.filter(function (e) { return e.signal_type === "AWC_TAF"; }).length;
    dom.aviationSummary.appendChild(signalRow("METAR observations", String(metar)));
    dom.aviationSummary.appendChild(signalRow("TAF forecast groups", String(taf)));
    dom.aviationSummary.appendChild(signalRow("Highest severity", highestSeverity(aviation), severityChip(aviation)));

    dom.operationsSummary.appendChild(signalRow("Verified operational feed", "NOT INTEGRATED", "calm"));
    dom.operationsSummary.appendChild(signalRow("Ground stops / GDP", "NO DATA", "calm"));
    dom.operationsSummary.appendChild(signalRow("Authority check", "REQUIRED", "moderate"));
  }

  function severityChip(items) {
    var max = highestSeverity(items);
    if (max === "SEVERE" || max === "EXTREME") return "severe";
    if (max === "MODERATE") return "moderate";
    if (max === "MINOR" || max === "CLEAR") return "calm";
    return "";
  }

  function highestSeverity(items) {
    var best = null;
    items.forEach(function (item) {
      if ((SEVERITY_RANK[item.severity] || 0) > (SEVERITY_RANK[best] || 0)) best = item.severity;
    });
    return best || "—";
  }

  function uniqueProviders(items) {
    var seen = [];
    items.forEach(function (item) { if (seen.indexOf(item.provider) < 0) seen.push(item.provider); });
    return seen.join(" · ");
  }

  function renderActions(data) {
    clear(dom.recommendations);
    var items = data.recommendations || [];
    if (!items.length) {
      dom.recommendations.appendChild(el("li", "empty-inline", "No actions were generated."));
      return;
    }
    items.forEach(function (item) {
      var li = el("li");
      li.appendChild(el("span", "priority " + (item.priority || ""), item.priority));
      var body = el("div");
      body.appendChild(el("div", "action-title", item.action));
      body.appendChild(el("div", "action-rule", item.rule_id + (item.evidence_ids && item.evidence_ids.length ? " · " + item.evidence_ids.join(", ") : "")));
      li.appendChild(body);
      dom.recommendations.appendChild(li);
    });
  }

  function renderRules(data) {
    clear(dom.rules);
    var rules = data.triggered_rules || [];
    if (!rules.length) {
      dom.rules.appendChild(el("li", "muted", "No rules fired."));
    } else {
      rules.forEach(function (rule) {
        var li = el("li");
        li.appendChild(el("span", "rule-id", rule.rule_id));
        li.appendChild(document.createTextNode(rule.description || ""));
        if (rule.evidence_ids && rule.evidence_ids.length) {
          li.appendChild(el("div", "action-rule", "Evidence: " + rule.evidence_ids.join(", ")));
        }
        dom.rules.appendChild(li);
      });
    }
    clear(dom.assumptions);
    (data.assumptions || []).forEach(function (assumption) {
      dom.assumptions.appendChild(el("li", "", assumption));
    });
  }

  function renderProviders(data) {
    clear(dom.providers);
    clear(dom.contextSources);
    (data.provider_status || []).forEach(function (status) {
      var card = el("div", "provider-card");
      var heading = el("h4");
      heading.appendChild(document.createTextNode(status.provider));
      heading.appendChild(el("span", "status-pill " + String(status.status).toLowerCase(), status.status));
      card.appendChild(heading);
      card.appendChild(el("p", "", "HTTP " + (status.http_status === null ? "—" : status.http_status) +
        " · " + status.latency_ms + " ms · " + status.evidence_count + " item(s)"));
      if (status.note) card.appendChild(el("p", "", status.note));
      if (status.error) card.appendChild(el("p", "", "Error: " + status.error));
      var link = el("a", "", "Authoritative source ↗");
      link.href = safeUrl(status.authoritative_url, "https://www.weather.gov/");
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      card.appendChild(link);
      dom.providers.appendChild(card);

      var line = el("div", "context-source");
      line.appendChild(el("span", "", status.provider));
      line.appendChild(el("span", "", String(status.status)));
      dom.contextSources.appendChild(line);
    });
  }

  /* ---------- map: shared helpers ---------- */

  function routePoints(data) {
    var route = data.route || {};
    var points = [];
    if (isFinite(parseFloat(route.origin_lat)) && isFinite(parseFloat(route.origin_lon))) {
      points.push({ lon: parseFloat(route.origin_lon), lat: parseFloat(route.origin_lat), role: "origin" });
    }
    if (isFinite(parseFloat(route.destination_lat)) && isFinite(parseFloat(route.destination_lon))) {
      points.push({ lon: parseFloat(route.destination_lon), lat: parseFloat(route.destination_lat), role: "destination" });
    }
    return points;
  }

  function routeKey(data) {
    var route = data.route || {};
    return [route.origin_iata, route.destination_iata, data.travel_date].join("|");
  }

  function mapEvidence() {
    return baseEvidence().filter(function (item) {
      if (!hasCoords(item)) return false;
      if (isWeather(item)) return dom.layerWeather.checked;
      if (isAviation(item)) return dom.layerAviation.checked;
      return false;
    });
  }

  function updateLegend() {
    clear(dom.mapLegend);
    function legend(colorClass, label) {
      var span = el("span");
      span.appendChild(el("i", "legend-dot " + colorClass));
      span.appendChild(document.createTextNode(label));
      return span;
    }
    if (dom.layerAirports.checked) {
      dom.mapLegend.appendChild(legend("origin", "Origin"));
      dom.mapLegend.appendChild(legend("destination", "Destination"));
    }
    if (dom.layerWeather.checked) dom.mapLegend.appendChild(legend("weather", "Weather signal"));
    if (dom.layerAviation.checked) dom.mapLegend.appendChild(legend("aviation", "METAR / TAF"));
    if (!dom.mapLegend.children.length) dom.mapLegend.appendChild(el("span", "", "All layers hidden"));
  }

  function markerElement(label, classNames, onClick, evidenceId) {
    var button = el("button", "rg-marker " + classNames);
    button.type = "button";
    button.title = label;
    button.setAttribute("aria-label", label);
    if (evidenceId) button.dataset.evidenceId = evidenceId;
    var initial = el("span", "", label.split(" ")[0].slice(0, 4));
    button.appendChild(initial);
    button.addEventListener("click", function (event) {
      event.stopPropagation();
      onClick();
    });
    return button;
  }

  /* ---------- map: MapLibre implementation ---------- */

  function initMapLibre() {
    if (window.RouteGuardMapLibre) {
      setupMapLibre();
    } else {
      window.addEventListener("routeguard:maplibre-ready", setupMapLibre, { once: true });
    }
  }

  function setupMapLibre() {
    var ml = window.RouteGuardMapLibre;
    if (!ml || state.map || !dom.mapCanvas) return;
    try {
      state.map = new ml.Map({
        container: dom.mapCanvas,
        style: MAP_STYLE_URL,
        center: [-96, 38],
        zoom: 3.2,
        attributionControl: true,
        cooperativeGestures: false,
      });
      state.map.addControl(new ml.NavigationControl({ showCompass: false }), "bottom-right");
      state.map.addControl(new ml.FullscreenControl({ container: dom.mapStage }), "top-right");
      state.map.on("load", function () {
        state.mapReady = true;
        document.body.classList.add("maplibre-ready");
        if (state.current) renderMap(state.current);
      });
      state.map.on("error", function () {
        // Keep the SVG fallback available if the external style cannot load.
        if (!state.mapReady) document.body.classList.remove("maplibre-ready");
      });
    } catch (error) {
      state.map = null;
      state.mapReady = false;
    }
  }

  function clearMapLibreMarkers() {
    Object.keys(state.markers).forEach(function (key) {
      state.markers[key].forEach(function (marker) {
        if (marker && typeof marker.remove === "function") marker.remove();
      });
      state.markers[key] = [];
    });
  }

  function updateRouteReference(data, ml) {
    if (!state.mapReady) return;
    var points = routePoints(data);
    if (points.length < 2) return;
    var feature = {
      type: "Feature",
      properties: { label: "Illustrative airport-pair reference" },
      geometry: { type: "LineString", coordinates: points.map(function (p) { return [p.lon, p.lat]; }) },
    };
    if (!state.map.getSource("route-reference")) {
      state.map.addSource("route-reference", { type: "geojson", data: feature });
      state.map.addLayer({
        id: "route-reference-line",
        type: "line",
        source: "route-reference",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": "#ef5545", "line-width": 2.6, "line-dasharray": [2, 1.6], "line-opacity": 0.9 },
      });
    } else {
      state.map.getSource("route-reference").setData(feature);
    }
    state.map.setLayoutProperty(
      "route-reference-line",
      "visibility",
      dom.layerRoutes.checked ? "visible" : "none"
    );
  }

  function openMapPopup(item) {
    if (!state.mapReady || !state.map || !hasCoords(item)) return;
    if (state.popup) state.popup.remove();
    var ml = window.RouteGuardMapLibre;
    var content = el("div");
    content.appendChild(el("strong", "", item.provider + " · " + item.signal_type.replace(/_/g, " ")));
    content.appendChild(el("div", "", truncate(item.signal, 140)));
    var meta = el("div", "action-rule", item.severity + " · " + item.freshness + " · " + item.temporal_overlap);
    content.appendChild(meta);
    state.popup = new ml.Popup({ closeButton: true, maxWidth: "270px" })
      .setLngLat([item.longitude, item.latitude])
      .setDOMContent(content)
      .addTo(state.map);
  }

  function focusMapOn(item) {
    if (!hasCoords(item)) return;
    if (state.mapReady && state.map) {
      state.map.easeTo({
        center: [item.longitude, item.latitude],
        zoom: Math.max(state.map.getZoom(), 4.2),
        duration: reducedMotion() ? 0 : 600,
      });
    } else {
      var point = project(item.longitude, item.latitude);
      state.fallbackView.cx = point.x;
      state.fallbackView.cy = point.y;
      state.fallbackView.zoom = Math.max(state.fallbackView.zoom, 1.5);
      applyFallbackView();
    }
  }

  function fitMapToData(data) {
    if (!state.mapReady || !state.map) return;
    var ml = window.RouteGuardMapLibre;
    var coords = routePoints(data).map(function (p) { return [p.lon, p.lat]; });
    mapEvidence().forEach(function (item) { coords.push([item.longitude, item.latitude]); });
    if (!coords.length) return;
    var bounds = new ml.LngLatBounds(coords[0], coords[0]);
    coords.forEach(function (coord) { bounds.extend(coord); });
    if (coords.length === 1) {
      state.map.easeTo({ center: coords[0], zoom: 4, duration: reducedMotion() ? 0 : 500 });
      return;
    }
    state.map.fitBounds(bounds, {
      padding: { top: 70, bottom: 110, left: 60, right: 210 },
      maxZoom: 8,
      duration: reducedMotion() ? 0 : 700,
    });
  }

  function renderMapLibre(data) {
    if (!state.mapReady || !state.map) return false;
    clearMapLibreMarkers();
    updateRouteReference(data, window.RouteGuardMapLibre);
    updateLegend();

    if (dom.layerAirports.checked) {
      routePoints(data).forEach(function (point) {
        var route = data.route || {};
        var isOrigin = point.role === "origin";
        var label = (isOrigin ? route.origin_iata : route.destination_iata) + " · " +
          (isOrigin ? route.origin_city : route.destination_city);
        var button = markerElement(label, isOrigin ? "origin" : "destination", function () {
          focusAirport(point.role);
        });
        var marker = new window.RouteGuardMapLibre.Marker({ element: button, anchor: "center" })
          .setLngLat([point.lon, point.lat])
          .addTo(state.map);
        state.markers.airports.push(marker);
      });
    }

    mapEvidence().forEach(function (item) {
      var forecast = item.signal_type.indexOf("TAF") >= 0 || item.signal_type.indexOf("FORECAST") >= 0;
      var high = item.severity === "SEVERE" || item.severity === "EXTREME";
      var classNames = (isWeather(item) ? "weather" : "aviation") + (forecast ? " forecast" : "") + (high ? " is-high" : "");
      var label = item.provider + " · " + truncate(item.signal, 48);
      var button = markerElement(label, classNames, function () {
        selectEvidence(item.id, { focusMap: false, openPopup: true });
      }, item.id);
      if (state.selectedEvidenceId === item.id) button.classList.add("is-selected");
      var marker = new window.RouteGuardMapLibre.Marker({ element: button, anchor: "center" })
        .setLngLat([item.longitude, item.latitude])
        .addTo(state.map);
      state.markers[isWeather(item) ? "weather" : "aviation"].push(marker);
    });

    var key = routeKey(data);
    if (state.lastRouteKey !== key) {
      state.lastRouteKey = key;
      fitMapToData(data);
    }
    return true;
  }

  /* ---------- map: SVG fallback with zoom, pan and fullscreen ---------- */

  function computeFallbackBounds(data) {
    var points = routePoints(data).map(function (p) { return [p.lon, p.lat]; });
    mapEvidence().forEach(function (item) { points.push([item.longitude, item.latitude]); });
    var lons = points.map(function (p) { return p[0]; });
    var lats = points.map(function (p) { return p[1]; });
    if (!lons.length) return;
    var lonMin = Math.min.apply(null, lons) - 12;
    var lonMax = Math.max.apply(null, lons) + 12;
    if (lonMax - lonMin > 220) { lonMin = -180; lonMax = 180; }
    var latMin = Math.max(-80, Math.min.apply(null, lats) - 10);
    var latMax = Math.min(85, Math.max.apply(null, lats) + 10);
    if (latMax - latMin < 30) {
      var mid = (latMax + latMin) / 2;
      latMin = Math.max(-80, mid - 15);
      latMax = Math.min(85, mid + 15);
    }
    MAP_BOUNDS = { lonMin: lonMin, lonMax: lonMax, latMin: latMin, latMax: latMax };
  }

  function project(lon, lat) {
    return {
      x: 24 + ((lon - MAP_BOUNDS.lonMin) / (MAP_BOUNDS.lonMax - MAP_BOUNDS.lonMin)) * 752,
      y: 20 + ((MAP_BOUNDS.latMax - lat) / (MAP_BOUNDS.latMax - MAP_BOUNDS.latMin)) * 380,
    };
  }

  function applyFallbackView() {
    var z = state.fallbackView.zoom;
    var cx = state.fallbackView.cx;
    var cy = state.fallbackView.cy;
    dom.map.setAttribute("viewBox", [
      cx - 400 / z, cy - 210 / z, 800 / z, 420 / z,
    ].join(" "));
  }

  function zoomFallback(delta) {
    state.fallbackView.zoom = Math.max(0.8, Math.min(4, state.fallbackView.zoom + delta));
    applyFallbackView();
  }

  function fallbackMarker(label, point, fill, onClick, extraClass) {
    var group = svg("g", {
      class: "map-marker " + (extraClass || ""), tabindex: "0", role: "button", "aria-label": label,
    });
    group.appendChild(svg("circle", { cx: point.x, cy: point.y, r: 13, fill: fill, opacity: 0.15 }));
    group.appendChild(svg("circle", { cx: point.x, cy: point.y, r: 9, fill: "transparent", "pointer-events": "all" }));
    group.appendChild(svg("circle", { cx: point.x, cy: point.y, r: 5.5, fill: fill, stroke: "#ffffff", "stroke-width": 1.8 }));
    group.addEventListener("click", onClick);
    group.addEventListener("keydown", function (event) {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onClick(); }
    });
    group.addEventListener("mouseenter", function () {
      dom.mapTooltip.textContent = "";
      dom.mapTooltip.appendChild(el("strong", "", label));
      dom.mapTooltip.appendChild(document.createTextNode("Select to inspect linked evidence"));
      dom.mapTooltip.style.left = (point.x / 8) + "%";
      dom.mapTooltip.style.top = (point.y / 4.2) + "%";
      show(dom.mapTooltip, true);
    });
    group.addEventListener("mouseleave", function () { show(dom.mapTooltip, false); });
    dom.map.appendChild(group);
    var text = svg("text", {
      x: point.x + 12, y: point.y - 10, fill: "#344154", "font-size": 11,
      "font-family": "Geist Mono, monospace", "pointer-events": "none",
    });
    text.textContent = label;
    dom.map.appendChild(text);
    return group;
  }

  function renderFallbackMap(data) {
    clear(dom.map);
    show(dom.mapTooltip, false);
    computeFallbackBounds(data);
    state.fallbackView = { cx: 400, cy: 210, zoom: 1 };
    applyFallbackView();
    updateLegend();

    var gridGroup = svg("g", { class: "decorative" });
    var pattern = svg("pattern", { id: "rg-grid", width: 56, height: 47, patternUnits: "userSpaceOnUse" });
    pattern.appendChild(svg("path", { d: "M 56 0 L 0 0 0 47", fill: "none", stroke: "rgba(71,85,105,0.10)", "stroke-width": 1 }));
    var defs = svg("defs");
    defs.appendChild(pattern);
    gridGroup.appendChild(defs);
    gridGroup.appendChild(svg("rect", { x: 0, y: 0, width: 800, height: 420, fill: "url(#rg-grid)" }));
    dom.map.appendChild(gridGroup);

    var points = routePoints(data);
    if (points.length === 2 && dom.layerRoutes.checked) {
      var a = project(points[0].lon, points[0].lat);
      var b = project(points[1].lon, points[1].lat);
      var line = svg("line", {
        class: "route-connector", x1: a.x, y1: a.y, x2: b.x, y2: b.y,
        stroke: "#ef5545", "stroke-width": 2.6, "stroke-dasharray": "9 7",
      });
      dom.map.appendChild(line);
    }

    mapEvidence().forEach(function (item, index) {
      var base = project(item.longitude, item.latitude);
      var offset = 17 + (index % 3) * 7;
      var point = { x: base.x + offset, y: base.y + offset };
      var color = isWeather(item) ? "#d97706" : "#3b82f6";
      fallbackMarker(truncate(item.signal, 24), point, color, function () {
        selectEvidence(item.id, { focusMap: false });
      }, isWeather(item) ? "weather" : "aviation");
    });

    if (dom.layerAirports.checked) {
      var route = data.route || {};
      points.forEach(function (point) {
        var isOrigin = point.role === "origin";
        var p = project(point.lon, point.lat);
        fallbackMarker(
          (isOrigin ? route.origin_iata : route.destination_iata) + " · " +
          (isOrigin ? route.origin_country : route.destination_country),
          p, isOrigin ? "#0f9f94" : "#7c3aed",
          function () { focusAirport(point.role); },
          isOrigin ? "origin" : "destination"
        );
      });
    }

    var caption = svg("text", { x: 28, y: 34, fill: "#6b7280", "font-size": 10, "font-family": "Geist Mono, monospace" });
    caption.textContent = "Fallback schematic · " + (data.route && data.route.coverage_focus || "global") +
      " focus · endpoints only, not a flight path";
    dom.map.appendChild(caption);
  }

  function renderMap(data) {
    if (renderMapLibre(data)) return;
    renderFallbackMap(data);
  }

  function resetMap() {
    if (state.mapReady && state.map && state.current) {
      fitMapToData(state.current);
    } else {
      state.fallbackView = { cx: 400, cy: 210, zoom: 1 };
      applyFallbackView();
    }
    toast("Map view reset");
  }

  function toggleFullscreen() {
    if (!dom.mapStage) return;
    if (document.fullscreenElement) {
      document.exitFullscreen();
      return;
    }
    if (dom.mapStage.requestFullscreen) {
      dom.mapStage.requestFullscreen().catch(function () { toast("Fullscreen was blocked by the browser."); });
    } else {
      toast("Fullscreen is not supported in this browser.");
    }
  }

  /* ---------- selection and context ---------- */

  function selectEvidence(id, options) {
    var item = evidenceById(id);
    if (!item) return;
    options = options || {};
    state.selectedEvidenceId = id;
    state.highlighted = id;
    state.activeAirport = null;
    renderAirportBlocks();
    highlightEvidence(id);
    markTimelineSelection(id);
    updateMarkerSelection(id);
    renderContext(state.current);
    if (options.focusMap) focusMapOn(item);
    if (options.openPopup) openMapPopup(item);
  }

  function updateMarkerSelection(id) {
    document.querySelectorAll(".rg-marker").forEach(function (node) {
      node.classList.toggle("is-selected", node.getAttribute("data-evidence-id") === id);
    });
    // MapLibre markers are recreated on each map render, so refresh them once.
    if (state.current && state.mapReady) renderMapLibre(state.current);
  }

  function contextDetailRow(label, value) {
    var row = el("div", "detail-row");
    row.appendChild(el("span", "", label));
    row.appendChild(el("strong", "", value === undefined || value === null || value === "" ? "—" : String(value)));
    return row;
  }

  function renderContext(data) {
    if (!data) return;
    var route = data.route || {};
    dom.contextRouteTitle.textContent = (route.origin_city || "—") + " → " + (route.destination_city || "—");
    dom.contextRouteSub.textContent = "Airport-level assessment · " + (route.origin_country || "—") + " → " + (route.destination_country || "—");
    dom.contextOriginCode.textContent = route.origin_iata || "—";
    dom.contextOriginCity.textContent = route.origin_city || "—";
    dom.contextDestinationCode.textContent = route.destination_iata || "—";
    dom.contextDestinationCity.textContent = route.destination_city || "—";
    dom.contextDate.textContent = data.travel_date || "—";
    dom.contextProviders.textContent = route.weather_provider === "NWS" ? "NWS + AWC" : "Open-Meteo + AWC";
    dom.contextFocus.textContent = route.coverage_focus || "Global";

    clear(dom.contextSelectionBody);
    dom.contextDetailButton.disabled = true;
    var item = evidenceById(state.selectedEvidenceId);
    if (item) {
      dom.contextSelectionTitle.textContent = item.provider + " · " + item.signal_type.replace(/_/g, " ").toLowerCase();
      dom.contextSelectionBody.appendChild(contextDetailRow("Signal", truncate(item.signal, 120)));
      dom.contextSelectionBody.appendChild(contextDetailRow("Severity", item.severity));
      dom.contextSelectionBody.appendChild(contextDetailRow("Location", item.location_label || "Not attributable"));
      dom.contextSelectionBody.appendChild(contextDetailRow("Validity", fmtInstant(item.valid_from) + " → " + fmtInstant(item.valid_to)));
      dom.contextSelectionBody.appendChild(contextDetailRow("Interpretation", item.relevance_reason));
      if (state.mode === "analyst") {
        dom.contextSelectionBody.appendChild(contextDetailRow("Raw excerpt", truncate(item.raw_excerpt, 160)));
        dom.contextSelectionBody.appendChild(contextDetailRow("Reliability", item.reliability));
      }
      dom.contextDetailButton.disabled = false;
    } else if (state.activeAirport) {
      var role = state.activeAirport;
      var city = route[role + "_city"] || role;
      var code = route[role + "_iata"] || "—";
      var attributed = (data.evidence || []).filter(function (e) {
        return e.location_label && e.location_label.toLowerCase().indexOf(role) === 0;
      });
      dom.contextSelectionTitle.textContent = city + " (" + code + ")";
      dom.contextSelectionBody.appendChild(contextDetailRow("Country", route[role + "_country"] || "—"));
      dom.contextSelectionBody.appendChild(contextDetailRow("Timezone", route[role + "_timezone"] || "—"));
      dom.contextSelectionBody.appendChild(contextDetailRow("Attributed signals", String(attributed.length)));
      dom.contextSelectionBody.appendChild(contextDetailRow("Highest severity", highestSeverity(attributed)));
    } else {
      dom.contextSelectionTitle.textContent = "Nothing selected";
      dom.contextSelectionBody.appendChild(el("p", "muted", "Select a map marker, evidence card or timeline item to see its source, geography and validity here."));
    }

    clear(dom.priorityFindings);
    var priority = baseEvidence().slice().sort(function (a, b) {
      return (SEVERITY_RANK[b.severity] || 0) - (SEVERITY_RANK[a.severity] || 0);
    }).slice(0, 3);
    if (!priority.length) {
      dom.priorityFindings.appendChild(el("p", "muted", "No priority evidence in this view."));
    } else {
      priority.forEach(function (entry) {
        var button = el("button", "priority-item");
        button.type = "button";
        button.appendChild(el("strong", "", entry.severity + " · " + entry.provider));
        button.appendChild(document.createTextNode(truncate(entry.signal, 78)));
        button.addEventListener("click", function () {
          selectEvidence(entry.id, { focusMap: true, openPopup: true });
        });
        dom.priorityFindings.appendChild(button);
      });
    }
  }

  function focusAirport(role) {
    if (!state.current) return;
    state.activeAirport = state.activeAirport === role ? null : role;
    state.selectedEvidenceId = null;
    renderAirportBlocks();
    renderContext(state.current);
    highlightEvidence(null);
    markTimelineSelection(null);
    if (!state.activeAirport) return;
    var route = state.current.route || {};
    var lat = parseFloat(route[role + "_lat"]);
    var lon = parseFloat(route[role + "_lon"]);
    if (isFinite(lat) && isFinite(lon)) {
      if (state.mapReady && state.map) {
        state.map.easeTo({ center: [lon, lat], zoom: Math.max(state.map.getZoom(), 4.5), duration: reducedMotion() ? 0 : 600 });
      } else {
        var p = project(lon, lat);
        state.fallbackView.cx = p.x;
        state.fallbackView.cy = p.y;
        state.fallbackView.zoom = Math.max(state.fallbackView.zoom, 1.5);
        applyFallbackView();
      }
    }
    var relevant = (state.current.evidence || []).filter(function (item) {
      return item.location_label && item.location_label.toLowerCase().indexOf(role) === 0;
    });
    if (relevant.length) highlightEvidence(relevant[0].id);
    toast("Focused " + role + " — " + relevant.length + " attributed signal(s)");
  }

  /* ---------- timeline, distribution, evidence ---------- */

  function renderTimeline(data) {
    clear(dom.timeline);
    clear(dom.travelBand);
    var window = data.travel_window_utc || {};
    dom.travelBand.appendChild(el("span", "", "Travel window " + shortInstant(window.start) + "Z"));
    dom.travelBand.appendChild(el("span", "", shortInstant(window.end) + "Z"));

    var items = (data.evidence || []).filter(function (item) {
      return item.observed_at || item.valid_from;
    }).map(function (item) {
      return { item: item, time: item.observed_at || item.valid_from };
    }).sort(function (a, b) { return new Date(a.time) - new Date(b.time); });

    if (!items.length) {
      dom.timeline.appendChild(el("div", "empty-inline", "No provider timestamps were available for this assessment."));
      return;
    }
    items.forEach(function (entry, index) {
      var item = entry.item;
      var isForecast = item.signal_type.indexOf("TAF") >= 0 || item.signal_type.indexOf("FORECAST") >= 0;
      var button = el("button", "timeline-item");
      button.type = "button";
      button.setAttribute("role", "listitem");
      button.dataset.evidenceId = item.id;
      button.style.animationDelay = Math.min(index * 35, 280) + "ms";
      button.appendChild(el("div", "timeline-kind " + (isForecast ? "forecast" : "observed"),
        (isForecast ? "Forecast" : "Observed") + " · " + item.provider));
      button.appendChild(el("div", "timeline-time", fmtInstant(entry.time)));
      button.appendChild(el("div", "timeline-signal", truncate(item.signal, 42)));
      button.appendChild(el("div", "action-rule", item.severity + " · " + item.temporal_overlap + " overlap"));
      button.addEventListener("click", function () {
        selectEvidence(item.id, { focusMap: true, openPopup: true });
      });
      dom.timeline.appendChild(button);
    });
  }

  function markTimelineSelection(id) {
    Array.prototype.forEach.call(dom.timeline.querySelectorAll(".timeline-item"), function (node) {
      node.classList.toggle("is-selected", node.dataset.evidenceId === id);
    });
  }

  function distributionGroup(title, key, values) {
    var group = el("div", "dist-group");
    group.appendChild(el("h4", "", title));
    var evidence = state.current ? state.current.evidence || [] : [];
    var counts = {};
    values.forEach(function (value) { counts[value] = 0; });
    evidence.forEach(function (item) { if (item[key] in counts) counts[item[key]] += 1; });
    var total = evidence.length || 1;
    values.forEach(function (value) {
      var row = el("div", "dist-row");
      row.appendChild(el("span", "", value));
      var track = el("span", "dist-track");
      var fill = el("span", "dist-fill " + value);
      fill.style.width = (counts[value] / total) * 100 + "%";
      track.appendChild(fill);
      row.appendChild(track);
      row.appendChild(el("span", "", String(counts[value])));
      group.appendChild(row);
    });
    return group;
  }

  function renderDistribution() {
    clear(dom.distribution);
    dom.distribution.appendChild(distributionGroup("By severity", "severity", ["EXTREME", "SEVERE", "MODERATE", "MINOR", "UNKNOWN"]));
    dom.distribution.appendChild(distributionGroup("By provider", "provider", ["NWS", "OPEN_METEO", "AWC"]));
  }

  function renderFilters() {
    clear(dom.filters);
    FILTERS.forEach(function (filter) {
      var button = el("button", "filter-chip", filter.label);
      button.type = "button";
      button.setAttribute("aria-pressed", String(state.filter === filter.id));
      button.addEventListener("click", function () {
        state.filter = filter.id;
        renderFilters();
        if (state.current) renderEvidence(state.current);
      });
      dom.filters.appendChild(button);
    });
  }

  function renderEvidence(data) {
    clear(dom.evidenceList);
    var items = filteredEvidence();
    dom.evidenceEmpty.textContent = VIEW_EMPTY[state.view] || VIEW_EMPTY.all;
    show(dom.evidenceEmpty, items.length === 0);
    items.forEach(function (item, index) {
      var card = el("button", "evidence-card" + (state.highlighted === item.id ? " is-selected" : ""));
      card.type = "button";
      card.setAttribute("role", "listitem");
      card.dataset.evidenceId = item.id;
      card.style.animationDelay = Math.min(index * 25, 250) + "ms";
      var top = el("div", "evidence-top");
      top.appendChild(el("span", "provider-chip " + item.provider, item.provider));
      top.appendChild(el("span", "severity-chip " + item.severity, item.severity));
      card.appendChild(top);
      card.appendChild(el("div", "evidence-signal", truncate(item.signal, 90)));
      card.appendChild(el("div", "evidence-reason", item.relevance_reason));
      var foot = el("div", "evidence-foot");
      foot.appendChild(el("span", "", item.signal_type.replace("NWS_", "").replace("AWC_", "").replace("OPEN_METEO_", "")));
      foot.appendChild(el("span", "", item.freshness));
      foot.appendChild(el("span", "", item.temporal_overlap));
      if (item.location_label) foot.appendChild(el("span", "", item.location_label));
      card.appendChild(foot);
      card.addEventListener("click", function () {
        selectEvidence(item.id, { focusMap: true, openPopup: true });
      });
      dom.evidenceList.appendChild(card);
    });
  }

  function highlightEvidence(id) {
    state.highlighted = id;
    Array.prototype.forEach.call(dom.evidenceList.querySelectorAll(".evidence-card"), function (card) {
      card.classList.toggle("is-selected", card.dataset.evidenceId === id);
    });
    var card = dom.evidenceList.querySelector('[data-evidence-id="' + id + '"]');
    if (card) card.scrollIntoView({ block: "nearest" });
  }

  /* ---------- evidence drawer ---------- */

  function drawerRow(label, value, raw) {
    var row = el("div", "detail-row");
    row.appendChild(el("span", "", label));
    if (raw) row.appendChild(el("div", "raw-box", value === undefined || value === null ? "—" : String(value)));
    else if (label === "Evidence ID") row.appendChild(el("code", "", String(value || "—")));
    else row.appendChild(el("strong", "", value === undefined || value === null || value === "" ? "—" : String(value)));
    return row;
  }

  function openEvidenceDrawer(id) {
    if (!state.current || !id) return;
    var item = evidenceById(id);
    if (!item) return;
    var status = (state.current.provider_status || []).filter(function (p) { return p.provider === item.provider; })[0] || {};
    dom.drawerTitle.textContent = item.signal_type.replace(/_/g, " ").toLowerCase();
    clear(dom.drawerBody);
    dom.drawerBody.appendChild(drawerRow("Evidence ID", item.id));
    dom.drawerBody.appendChild(drawerRow("Source", item.provider));
    dom.drawerBody.appendChild(drawerRow("Signal", item.signal));
    dom.drawerBody.appendChild(drawerRow("Severity", item.severity));
    dom.drawerBody.appendChild(drawerRow("Verification", item.reliability + " reliability · " + item.freshness + " freshness"));
    dom.drawerBody.appendChild(drawerRow("Affected location", item.location_label || "Not attributable in this run"));
    dom.drawerBody.appendChild(drawerRow("Observation timestamp (UTC)", fmtInstant(item.observed_at)));
    dom.drawerBody.appendChild(drawerRow("Forecast validity (UTC)", fmtInstant(item.valid_from) + " → " + fmtInstant(item.valid_to)));
    dom.drawerBody.appendChild(drawerRow("Retrieved from provider (UTC)", fmtInstant(status.fetched_at)));
    dom.drawerBody.appendChild(drawerRow("Geographic relevance", item.geography + " · temporal overlap " + item.temporal_overlap));
    dom.drawerBody.appendChild(drawerRow("Interpretation by RouteGuard", item.relevance_reason));
    dom.drawerBody.appendChild(drawerRow("Original information", truncate(item.raw_excerpt, 240), true));
    dom.drawerSource.href = safeUrl(item.source_url, "https://www.weather.gov/");
    state.drawerEvidenceId = id;
    show(dom.drawerOverlay, true);
    show(dom.drawer, true);
    dom.drawerClose.focus();
  }

  function closeDrawer() {
    show(dom.drawer, false);
    show(dom.drawerOverlay, false);
    state.drawerEvidenceId = null;
  }

  /* ---------- master render and request flow ---------- */

  function render(data) {
    state.current = data;
    state.highlighted = null;
    state.selectedEvidenceId = null;
    state.activeAirport = null;
    state.lastRouteKey = "";
    dom.emptyTitle.textContent = "Awaiting an assessment";
    dom.emptySubtitle.textContent = "Enter a route above to populate the intelligence workspace.";
    show(dom.empty, false);
    show(dom.results, true);
    renderSummary(data);
    renderSignalCards(data);
    renderActions(data);
    renderRules(data);
    renderTimeline(data);
    renderDistribution();
    renderFilters();
    renderEvidence(data);
    renderProviders(data);
    renderContext(data);
    renderViewPills();
    renderMap(data);
  }

  function setBusy(busy) {
    state.busy = busy;
    dom.submit.disabled = busy;
    dom.refresh.disabled = busy || !state.current;
    dom.submit.querySelector("span").textContent = busy ? "Assessing…" : "Assess route";
    show(dom.loadingPill, busy);
    show(dom.loadingAnnouncement, busy);
    show(dom.loadingSkeleton, busy && !state.current);
    dom.results.classList.toggle("is-refreshing", busy && !!state.current);
    if (dom.results) dom.results.setAttribute("aria-busy", String(busy));
  }

  function submit(payload, isRefresh) {
    if (state.busy) return;
    state.lastPayload = payload;
    show(dom.error, false);
    setBusy(true);
    fetch("/api/assess", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then(function (response) {
        return response.json().then(function (body) {
          if (!response.ok) throw body;
          return body;
        });
      })
      .then(function (data) {
        render(data);
        if (isRefresh) toast("Sources refreshed · " + (data.evidence || []).length + " evidence item(s) · " + data.classification);
      })
      .catch(function (envelope) {
        show(dom.results, false);
        show(dom.empty, true);
        dom.emptyTitle.textContent = "Assessment could not be completed";
        dom.emptySubtitle.textContent = "Check the highlighted input above, then try again.";
        show(dom.error, true);
        dom.error.textContent = (envelope && envelope.code ? envelope.code + ": " : "REQUEST_FAILED: ") +
          (envelope && envelope.message ? envelope.message : "The assessment could not be completed.");
        if (envelope && envelope.details && envelope.details.errors) {
          dom.error.textContent += " " + envelope.details.errors.map(function (e) { return e.field; }).join(", ");
        }
      })
      .finally(function () { setBusy(false); });
  }

  /* ---------- navigation ---------- */

  function handleNav(section) {
    Array.prototype.forEach.call(document.querySelectorAll(".rail-item[data-nav]"), function (node) {
      var active = node.getAttribute("data-nav") === section;
      node.classList.toggle("is-active", active);
      if (active) node.setAttribute("aria-current", "page"); else node.removeAttribute("aria-current");
    });
    var target = null;
    if (section === "overview") target = document.getElementById("top");
    else if (section === "intelligence") target = dom.results.hidden ? dom.form : dom.results;
    else if (section === "map") target = document.getElementById("map-card");
    else if (section === "disruptions") { applyView("high"); target = dom.evidenceList; }
    else if (section === "sources") target = document.getElementById("providers-heading");
    else if (section === "methodology") {
      target = document.getElementById("methodology-card");
      var details = document.querySelector(".assumptions-details");
      if (details) details.open = true;
    } else if (section === "help") {
      toast("Glossary terms are in the methodology panel.");
      target = document.getElementById("glossary");
    }
    if (target) target.scrollIntoView({ block: "start", behavior: reducedMotion() ? "auto" : "smooth" });
  }

  /* ---------- command palette ---------- */

  function commandList() {
    var commands = [
      { label: "New assessment", hint: "Focus origin", run: function () { dom.origin.focus(); dom.origin.select(); } },
      { label: "Refresh current assessment", hint: "Re-query sources", run: function () { if (state.lastPayload) submit(state.lastPayload, true); } },
      { label: "Go to interactive map", hint: "Scroll", run: function () { handleNav("map"); } },
      { label: "Go to evidence ledger", hint: "Scroll", run: function () { dom.evidenceList.scrollIntoView({ block: "center" }); } },
      { label: "Go to signal timeline", hint: "Scroll", run: function () { dom.timeline.scrollIntoView({ block: "center" }); } },
      { label: "Go to data sources", hint: "Scroll", run: function () { handleNav("sources"); } },
      { label: "Switch to Analyst mode", hint: "Technical detail", run: function () { state.mode = "analyst"; renderMode(); renderContext(state.current); } },
      { label: "Switch to Overview mode", hint: "Plain English", run: function () { state.mode = "overview"; renderMode(); renderContext(state.current); } },
      { label: "Show high-priority evidence", hint: "Filter", run: function () { applyView("high"); } },
      { label: "Clear evidence filters", hint: "View all", run: function () { state.filter = "all"; renderFilters(); if (state.current) renderEvidence(state.current); } },
    ];
    state.airports.forEach(function (airport) {
      commands.push({
        label: "Set origin → " + airport.city + " (" + airport.iata + ")",
        hint: airport.country,
        run: function () { dom.origin.value = airport.city; syncCodes(); dom.destination.focus(); },
      });
      commands.push({
        label: "Set destination → " + airport.city + " (" + airport.iata + ")",
        hint: airport.country,
        run: function () { dom.destination.value = airport.city; syncCodes(); dom.date.focus(); },
      });
    });
    return commands;
  }

  var paletteItems = [];
  var paletteIndex = 0;

  function renderPalette() {
    clear(dom.paletteResults);
    var query = dom.paletteInput.value.trim().toLowerCase();
    paletteItems = commandList().filter(function (command) {
      return !query || command.label.toLowerCase().indexOf(query) >= 0 || command.hint.toLowerCase().indexOf(query) >= 0;
    }).slice(0, 40);
    paletteIndex = 0;
    if (!paletteItems.length) {
      dom.paletteResults.appendChild(el("div", "empty-inline", "No matching commands or airports."));
      return;
    }
    paletteItems.forEach(function (command, index) {
      var button = el("button", "palette-item" + (index === 0 ? " is-active" : ""));
      button.type = "button";
      button.appendChild(el("span", "", command.label));
      button.appendChild(el("small", "", command.hint));
      button.addEventListener("click", function () { runPaletteCommand(index); });
      dom.paletteResults.appendChild(button);
    });
  }

  function runPaletteCommand(index) {
    var command = paletteItems[index];
    if (!command) return;
    closePalette();
    command.run();
  }

  function movePalette(delta) {
    if (!paletteItems.length) return;
    paletteIndex = (paletteIndex + delta + paletteItems.length) % paletteItems.length;
    Array.prototype.forEach.call(dom.paletteResults.querySelectorAll(".palette-item"), function (node, index) {
      node.classList.toggle("is-active", index === paletteIndex);
    });
  }

  function openPalette() {
    show(dom.paletteOverlay, true);
    show(dom.palette, true);
    dom.paletteInput.value = "";
    renderPalette();
    dom.paletteInput.focus();
  }

  function closePalette() {
    show(dom.palette, false);
    show(dom.paletteOverlay, false);
  }

  /* ---------- wiring ---------- */

  dom.date.value = tomorrowLocal();
  renderMode();
  renderViewPills();

  dom.form.addEventListener("submit", function (event) {
    event.preventDefault();
    submit({
      origin: dom.origin.value.trim(),
      destination: dom.destination.value.trim(),
      date: dom.date.value,
    }, false);
  });

  [dom.origin, dom.destination].forEach(function (input) {
    input.addEventListener("input", syncCodes);
    input.addEventListener("blur", syncCodes);
  });

  dom.swap.addEventListener("click", function () {
    var previous = dom.origin.value;
    dom.origin.value = dom.destination.value;
    dom.destination.value = previous;
    syncCodes();
  });

  dom.refresh.addEventListener("click", function () {
    if (state.lastPayload) submit(state.lastPayload, true);
  });

  dom.modeOverview.addEventListener("click", function () {
    state.mode = "overview"; renderMode(); renderContext(state.current);
  });
  dom.modeAnalyst.addEventListener("click", function () {
    state.mode = "analyst"; renderMode(); renderContext(state.current);
  });

  Array.prototype.forEach.call(dom.viewBar.querySelectorAll(".view-pill"), function (button) {
    button.addEventListener("click", function () { applyView(button.getAttribute("data-view")); });
  });

  [dom.layerAirports, dom.layerRoutes, dom.layerWeather, dom.layerAviation].forEach(function (input) {
    input.addEventListener("change", function () {
      if (state.current) { renderMap(state.current); updateLegend(); }
    });
  });

  dom.mapReset.addEventListener("click", resetMap);
  dom.mapFullscreen.addEventListener("click", toggleFullscreen);
  document.addEventListener("fullscreenchange", function () {
    dom.mapFullscreen.textContent = document.fullscreenElement ? "Exit fullscreen" : "Fullscreen";
  });

  document.querySelectorAll(".airport-block").forEach(function (node) {
    node.addEventListener("click", function () { focusAirport(node.getAttribute("data-airport")); });
    node.addEventListener("keydown", function (event) {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        focusAirport(node.getAttribute("data-airport"));
      }
    });
  });

  Array.prototype.forEach.call(document.querySelectorAll(".rail-item[data-nav]"), function (node) {
    node.addEventListener("click", function () { handleNav(node.getAttribute("data-nav")); });
  });

  dom.contextDetailButton.addEventListener("click", function () {
    if (state.selectedEvidenceId) openEvidenceDrawer(state.selectedEvidenceId);
  });
  dom.drawerClose.addEventListener("click", closeDrawer);
  dom.drawerOverlay.addEventListener("click", closeDrawer);
  dom.drawerMap.addEventListener("click", function () {
    if (state.drawerEvidenceId) {
      selectEvidence(state.drawerEvidenceId, { focusMap: true, openPopup: true });
      dom.mapStage.scrollIntoView({ block: "center", behavior: reducedMotion() ? "auto" : "smooth" });
    }
  });

  dom.paletteOpen.addEventListener("click", openPalette);
  dom.paletteOverlay.addEventListener("click", closePalette);
  dom.paletteInput.addEventListener("input", renderPalette);
  dom.paletteInput.addEventListener("keydown", function (event) {
    if (event.key === "ArrowDown") { event.preventDefault(); movePalette(1); }
    else if (event.key === "ArrowUp") { event.preventDefault(); movePalette(-1); }
    else if (event.key === "Enter") { event.preventDefault(); runPaletteCommand(paletteIndex); }
  });

  document.addEventListener("keydown", function (event) {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      if (!dom.palette.hidden) closePalette(); else openPalette();
    } else if (event.key === "Escape") {
      if (!dom.palette.hidden) closePalette();
      else if (!dom.drawer.hidden) closeDrawer();
    }
  });

  if (/Mac|iPhone|iPad/.test(navigator.platform)) dom.paletteKey.textContent = "⌘ K";
  else dom.paletteKey.textContent = "Ctrl K";

  /* SVG fallback pan and zoom. */
  var dragging = false;
  var dragStart = null;
  dom.map.addEventListener("pointerdown", function (event) {
    if (event.target.closest && event.target.closest(".map-marker")) return;
    dragging = true;
    dragStart = { x: event.clientX, y: event.clientY, cx: state.fallbackView.cx, cy: state.fallbackView.cy };
    dom.map.setPointerCapture(event.pointerId);
  });
  dom.map.addEventListener("pointermove", function (event) {
    if (!dragging || !dragStart) return;
    var rect = dom.map.getBoundingClientRect();
    var scale = (800 / state.fallbackView.zoom) / rect.width;
    state.fallbackView.cx = dragStart.cx - (event.clientX - dragStart.x) * scale;
    state.fallbackView.cy = dragStart.cy - (event.clientY - dragStart.y) * scale;
    applyFallbackView();
  });
  dom.map.addEventListener("pointerup", function () { dragging = false; dragStart = null; });
  dom.map.addEventListener("wheel", function (event) {
    event.preventDefault();
    zoomFallback(event.deltaY < 0 ? 0.16 : -0.16);
  }, { passive: false });

  fetch("/api/airports")
    .then(function (response) { return response.ok ? response.json() : []; })
    .then(function (airports) {
      state.airports = Array.isArray(airports) ? airports : [];
      state.airports.forEach(function (airport) {
        var option = el("option", "", airport.city + " (" + airport.iata + ")");
        option.setAttribute("label", airport.country);
        dom.datalist.appendChild(option);
      });
      syncCodes();
    })
    .catch(function () { /* autocomplete is an enhancement; assessment still works */ });

  syncCodes();
  updateLegend();
  initMapLibre();
})();
