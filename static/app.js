/* RouteGuard command centre — vanilla JS, no build step.
   Every server string is inserted with textContent or createElement/NS.
   No client-side classification, no fabricated data, no simulated progress. */
(function () {
  "use strict";

  var SVG_NS = "http://www.w3.org/2000/svg";
  // Bounds are recomputed per assessment so regional and global routes both
  // render honestly. Never claim a drawn line is an aircraft route.
  var MAP_BOUNDS = { lonMin: -125, lonMax: -66, latMin: 24, latMax: 50 };

  var state = {
    current: null,
    airports: [],
    filter: "all",
    highlighted: null,
    activeAirport: null,
    previousClassification: null,
    lastPayload: null,
    busy: false,
    toastTimer: null,
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
    updatedAt: document.getElementById("updated-at"),
    coverageBadge: document.getElementById("coverage-badge"),
    requestShort: document.getElementById("request-short"),
    classification: document.getElementById("classification"),
    classificationNote: document.getElementById("classification-note"),
    verdictCore: document.getElementById("verdict-core"),
    confidence: document.getElementById("confidence"),
    degraded: document.getElementById("degraded"),
    evidenceCount: document.getElementById("evidence-count"),
    coverageNote: document.getElementById("coverage-note"),
    recommendations: document.getElementById("recommendations"),
    rules: document.getElementById("triggered-rules"),
    assumptions: document.getElementById("assumptions"),
    originIntel: document.getElementById("origin-intel"),
    destinationIntel: document.getElementById("destination-intel"),
    map: document.getElementById("route-map"),
    mapTooltip: document.getElementById("map-tooltip"),
    timeline: document.getElementById("timeline"),
    travelBand: document.getElementById("travel-band"),
    distribution: document.getElementById("distribution"),
    filters: document.getElementById("evidence-filters"),
    evidenceList: document.getElementById("evidence-list"),
    evidenceEmpty: document.getElementById("evidence-empty"),
    providers: document.getElementById("provider-status"),
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

  /* ---------- rendering: summary + verdict ---------- */

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
    dom.classification.textContent = data.classification;
    dom.classification.className = "classification " + data.classification;
    // Only animate on first load or a genuine classification change.
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

    document.querySelectorAll(".airport-block").forEach(function (node) {
      node.classList.toggle("is-active", node.getAttribute("data-airport") === state.activeAirport);
    });

    if (changed) {
      toast("Classification changed: " + state.previousClassification + " → " + data.classification);
    }
    state.previousClassification = data.classification;
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
      return;
    }
    rules.forEach(function (rule) {
      var li = el("li");
      li.appendChild(el("span", "rule-id", rule.rule_id));
      li.appendChild(document.createTextNode(rule.description || ""));
      if (rule.evidence_ids && rule.evidence_ids.length) {
        li.appendChild(el("div", "action-rule", "Evidence: " + rule.evidence_ids.join(", ")));
      }
      dom.rules.appendChild(li);
    });
    clear(dom.assumptions);
    (data.assumptions || []).forEach(function (assumption) {
      dom.assumptions.appendChild(el("li", "", assumption));
    });
  }

  function renderIntel(data) {
    var evidence = data.evidence || [];
    [["origin", dom.originIntel], ["destination", dom.destinationIntel]].forEach(function (pair) {
      var role = pair[0];
      var container = pair[1];
      clear(container);
      var relevant = evidence.filter(function (item) {
        return item.location_label && String(item.location_label).toLowerCase().indexOf(role) === 0;
      });
      var route = data.route || {};
      var city = route[role + "_city"] || "—";
      var code = route[role + "_iata"] || "—";
      var rows = [
        ["Airport", city + " (" + code + ")"],
        ["Country", route[role + "_country"] || "—"],
        ["Timezone", route[role + "_timezone"] || "—"],
        ["Signals attributed", String(relevant.length)],
        ["Highest severity", highestSeverity(relevant)],
      ];
      if (!relevant.length) {
        rows.push(["Coverage", "No location-attributed signal in this run"]);
      }
      rows.forEach(function (row) {
        var line = el("div", "intel-row");
        line.appendChild(el("span", "", row[0]));
        line.appendChild(el("strong", "", row[1]));
        container.appendChild(line);
      });
      var button = el("button", "ghost-button", "Focus on map");
      button.type = "button";
      button.addEventListener("click", function () {
        focusAirport(role);
        document.getElementById("map-heading").scrollIntoView({ block: "center" });
      });
      container.appendChild(button);
    });
  }

  function highestSeverity(items) {
    var order = ["UNKNOWN", "MINOR", "MODERATE", "SEVERE", "EXTREME"];
    var best = null;
    items.forEach(function (item) {
      if (order.indexOf(item.severity) > order.indexOf(best)) best = item.severity;
    });
    return best || "—";
  }

  /* ---------- map ---------- */

  function project(lon, lat) {
    return {
      x: 24 + ((lon - MAP_BOUNDS.lonMin) / (MAP_BOUNDS.lonMax - MAP_BOUNDS.lonMin)) * 752,
      y: 20 + ((MAP_BOUNDS.latMax - lat) / (MAP_BOUNDS.latMax - MAP_BOUNDS.latMin)) * 380,
    };
  }

  function marker(title, point, fill, onClick, extraClass) {
    var group = svg("g", {
      class: "map-marker " + (extraClass || ""),
      tabindex: "0",
      role: "button",
      "aria-label": title,
    });
    group.appendChild(svg("circle", { cx: point.x, cy: point.y, r: 13, fill: fill, opacity: 0.14 }));
    // Precise hit target: labels live outside the group so they cannot steal clicks.
    group.appendChild(svg("circle", { cx: point.x, cy: point.y, r: 9, fill: "transparent", "pointer-events": "all" }));
    group.appendChild(svg("circle", { cx: point.x, cy: point.y, r: 5.5, fill: fill, stroke: "#070a11", "stroke-width": 1.5 }));
    group.addEventListener("click", onClick);
    group.addEventListener("keydown", function (event) {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        onClick();
      }
    });
    group.addEventListener("mouseenter", function () {
      dom.mapTooltip.textContent = "";
      dom.mapTooltip.appendChild(el("strong", "", title));
      dom.mapTooltip.appendChild(document.createTextNode("Select to inspect linked evidence"));
      dom.mapTooltip.style.left = point.x / 8 + "%";
      dom.mapTooltip.style.top = point.y / 4.2 + "%";
      show(dom.mapTooltip, true);
    });
    group.addEventListener("mouseleave", function () {
      show(dom.mapTooltip, false);
    });
    dom.map.appendChild(group);
    var label = svg("text", {
      x: point.x + 12,
      y: point.y - 10,
      fill: "#eaf0fb",
      "font-size": 11,
      "font-family": "Geist Mono, monospace",
      "pointer-events": "none",
    });
    label.textContent = title;
    dom.map.appendChild(label);
    return group;
  }

  function renderMap(data) {
    clear(dom.map);
    show(dom.mapTooltip, false);
    var route = data.route || {};
    var evidence = data.evidence || [];
    var oLat = parseFloat(route.origin_lat);
    var oLon = parseFloat(route.origin_lon);
    var dLat = parseFloat(route.destination_lat);
    var dLon = parseFloat(route.destination_lon);
    if (!isFinite(oLat) || !isFinite(oLon) || !isFinite(dLat) || !isFinite(dLon)) return;

    var signals = evidence.filter(function (item) {
      return item.latitude !== null && item.longitude !== null &&
        isFinite(item.latitude) && isFinite(item.longitude);
    });
    var lons = [oLon, dLon];
    var lats = [oLat, dLat];
    signals.forEach(function (item) { lons.push(item.longitude); lats.push(item.latitude); });
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

    var defs = svg("defs");
    var gridPattern = svg("pattern", { id: "grid", width: 56, height: 47, patternUnits: "userSpaceOnUse" });
    gridPattern.appendChild(svg("path", { d: "M 56 0 L 0 0 0 47", fill: "none", stroke: "rgba(158,181,220,0.09)", "stroke-width": 1 }));
    defs.appendChild(gridPattern);
    dom.map.appendChild(defs);
    dom.map.appendChild(svg("rect", { x: 0, y: 0, width: 800, height: 420, fill: "url(#grid)" }));

    var lonSpan = lonMax - lonMin;
    var lonStep = lonSpan > 200 ? 60 : (lonSpan > 80 ? 30 : 10);
    var latStep = (latMax - latMin) > 80 ? 30 : 10;
    var lon, lat, p, line, label;
    for (lat = Math.ceil(latMin / latStep) * latStep; lat <= latMax; lat += latStep) {
      p = project(lonMin, lat);
      line = svg("line", { x1: 24, y1: p.y, x2: 776, y2: p.y, stroke: "rgba(158,181,220,0.08)", "stroke-dasharray": "3 6" });
      dom.map.appendChild(line);
      label = svg("text", { x: 28, y: p.y - 5, fill: "#5f6f88", "font-size": 9, "font-family": "Geist Mono, monospace" });
      label.textContent = Math.abs(lat) + (lat < 0 ? "°S" : "°N");
      dom.map.appendChild(label);
    }
    for (lon = Math.ceil(lonMin / lonStep) * lonStep; lon <= lonMax; lon += lonStep) {
      p = project(lon, latMin);
      line = svg("line", { x1: p.x, y1: 20, x2: p.x, y2: 400, stroke: "rgba(158,181,220,0.07)", "stroke-dasharray": "3 6" });
      dom.map.appendChild(line);
      label = svg("text", { x: p.x + 3, y: 414, fill: "#5f6f88", "font-size": 9, "font-family": "Geist Mono, monospace" });
      label.textContent = Math.abs(lon) + (lon < 0 ? "°W" : "°E");
      dom.map.appendChild(label);
    }

    var originPoint = project(oLon, oLat);
    var destinationPoint = project(dLon, dLat);
    dom.map.appendChild(svg("line", {
      class: "route-connector",
      x1: originPoint.x, y1: originPoint.y, x2: destinationPoint.x, y2: destinationPoint.y,
      stroke: "rgba(90,209,200,0.55)", "stroke-width": 1.4,
    }));

    signals.forEach(function (item, index) {
      var point = project(item.longitude, item.latitude);
      var offset = 18 + (index % 3) * 8;
      var shifted = { x: point.x + offset, y: point.y + offset };
      dom.map.appendChild(svg("line", {
        x1: point.x, y1: point.y, x2: shifted.x, y2: shifted.y,
        stroke: "rgba(251,191,92,0.5)", "stroke-width": 1,
      }));
      var color = item.severity === "EXTREME" || item.severity === "SEVERE" ? "#fb7185" : "#fbbf5c";
      marker(
        truncate(item.signal, 26),
        shifted,
        color,
        function () {
          openEvidence(item.id);
          highlightEvidence(item.id);
        },
        "signal-marker"
      );
    });

    marker(route.origin_iata + " · " + (route.origin_country || "origin"), originPoint, "#5ad1c8",
      function () { focusAirport("origin"); });
    marker(route.destination_iata + " · " + (route.destination_country || "destination"), destinationPoint,
      "#a78bfa", function () { focusAirport("destination"); });

    var caption = svg("text", { x: 28, y: 34, fill: "#8493ac", "font-size": 10, "font-family": "Geist Mono, monospace" });
    caption.textContent = "Schematic lon/lat projection · " +
      (route.coverage_focus || "global") + " focus · endpoints only, not a flight path";
    dom.map.appendChild(caption);
  }

  function focusAirport(role) {
    state.activeAirport = state.activeAirport === role ? null : role;
    document.querySelectorAll(".airport-block").forEach(function (node) {
      node.classList.toggle("is-active", node.getAttribute("data-airport") === state.activeAirport);
    });
    if (state.activeAirport) {
      var container = state.activeAirport === "origin" ? dom.originIntel : dom.destinationIntel;
      container.style.outline = "1px solid rgba(90,209,200,0.5)";
      container.style.outlineOffset = "4px";
      window.setTimeout(function () {
        container.style.outline = "";
        container.style.outlineOffset = "";
      }, 900);
      filterEvidence("all");
      var relevant = (state.current && state.current.evidence || []).filter(function (item) {
        return item.location_label && item.location_label.toLowerCase().indexOf(state.activeAirport) === 0;
      });
      if (relevant.length) highlightEvidence(relevant[0].id);
      toast("Focused " + state.activeAirport + " — " + relevant.length + " attributed signal(s)");
    } else if (state.current) {
      renderEvidence(state.current);
    }
  }

  /* ---------- timeline ---------- */

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
    }).sort(function (a, b) {
      return new Date(a.time) - new Date(b.time);
    });

    if (!items.length) {
      dom.timeline.appendChild(el("div", "empty-inline", "No provider timestamps were available for this assessment."));
      return;
    }

    items.forEach(function (entry) {
      var item = entry.item;
      var isForecast = item.signal_type.indexOf("TAF") >= 0 || item.signal_type.indexOf("FORECAST") >= 0;
      var button = el("button", "timeline-item");
      button.type = "button";
      button.setAttribute("role", "listitem");
      button.appendChild(el("div", "timeline-kind " + (isForecast ? "forecast" : "observed"),
        (isForecast ? "Forecast" : "Observed") + " · " + item.provider));
      button.appendChild(el("div", "timeline-time", fmtInstant(entry.time)));
      button.appendChild(el("div", "timeline-signal", truncate(item.signal, 42)));
      button.appendChild(el("div", "action-rule", item.severity + " · " + item.temporal_overlap + " overlap"));
      button.addEventListener("click", function () {
        openEvidence(item.id);
        highlightEvidence(item.id);
      });
      dom.timeline.appendChild(button);
    });
  }

  /* ---------- distribution ---------- */

  function distributionGroup(title, key, values, colors) {
    var group = el("div");
    group.appendChild(el("h4", "", title));
    var evidence = state.current && state.current.evidence || [];
    var counts = {};
    values.forEach(function (value) { counts[value] = 0; });
    evidence.forEach(function (item) {
      var value = item[key];
      if (value in counts) counts[value] += 1;
    });
    var total = evidence.length || 1;
    values.forEach(function (value) {
      var row = el("div", "dist-row");
      row.appendChild(el("span", "", value));
      var track = el("span", "dist-track");
      var fill = el("span", "dist-fill " + (colors && colors[value] ? colors[value] : value));
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
    dom.distribution.appendChild(distributionGroup("By severity", "severity",
      ["EXTREME", "SEVERE", "MODERATE", "MINOR", "UNKNOWN"]));
    dom.distribution.appendChild(distributionGroup("By provider", "provider", ["NWS", "AWC"]));
  }

  /* ---------- evidence ledger ---------- */

  var FILTERS = [
    { id: "all", label: "All signals", test: function () { return true; } },
    { id: "weather", label: "Weather", test: function (e) { return e.signal_type.indexOf("NWS") === 0; } },
    { id: "aviation", label: "Aviation observation", test: function (e) { return e.signal_type === "AWC_METAR"; } },
    { id: "forecast", label: "Forecast", test: function (e) { return !!e.valid_from && e.temporal_overlap !== "NONE"; } },
    { id: "confirmed", label: "Confirmed", test: function (e) { return !!e.observed_at && e.freshness === "FRESH"; } },
    { id: "severe", label: "Severe+", test: function (e) { return e.severity === "SEVERE" || e.severity === "EXTREME"; } },
  ];

  function filterEvidence(filterId) {
    state.filter = filterId;
    if (state.current) renderEvidence(state.current);
  }

  function renderFilters() {
    clear(dom.filters);
    FILTERS.forEach(function (filter) {
      var button = el("button", "filter-chip", filter.label);
      button.type = "button";
      button.setAttribute("aria-pressed", String(state.filter === filter.id));
      button.addEventListener("click", function () {
        filterEvidence(filter.id);
        renderFilters();
      });
      dom.filters.appendChild(button);
    });
    dom.filters.appendChild(el("span", "muted small", "Airport operations and aviation advisories are not integrated in this prototype."));
  }

  function renderEvidence(data) {
    clear(dom.evidenceList);
    var active = FILTERS.filter(function (f) { return f.id === state.filter; })[0] || FILTERS[0];
    var items = (data.evidence || []).filter(active.test);
    show(dom.evidenceEmpty, items.length === 0);

    items.forEach(function (item) {
      var card = el("button", "evidence-card" + (state.highlighted === item.id ? " is-highlighted" : ""));
      card.type = "button";
      card.setAttribute("role", "listitem");
      card.dataset.evidenceId = item.id;
      var top = el("div", "evidence-top");
      top.appendChild(el("span", "provider-chip " + item.provider, item.provider));
      top.appendChild(el("span", "severity-chip " + item.severity, item.severity));
      card.appendChild(top);
      card.appendChild(el("div", "evidence-signal", truncate(item.signal, 90)));
      card.appendChild(el("div", "evidence-reason", item.relevance_reason));
      var foot = el("div", "evidence-foot");
      foot.appendChild(el("span", "", item.signal_type.replace("NWS_", "").replace("AWC_", "")));
      foot.appendChild(el("span", "", item.freshness));
      foot.appendChild(el("span", "", item.temporal_overlap));
      if (item.location_label) foot.appendChild(el("span", "", item.location_label));
      card.appendChild(foot);
      card.addEventListener("click", function () {
        openEvidence(item.id);
        highlightEvidence(item.id);
      });
      dom.evidenceList.appendChild(card);
    });
  }

  function highlightEvidence(id) {
    state.highlighted = id;
    Array.prototype.forEach.call(dom.evidenceList.querySelectorAll(".evidence-card"), function (card) {
      card.classList.toggle("is-highlighted", card.dataset.evidenceId === id);
    });
    var card = dom.evidenceList.querySelector('[data-evidence-id="' + id + '"]');
    if (card) card.scrollIntoView({ block: "nearest" });
  }

  /* ---------- evidence drawer ---------- */

  function detailRow(label, value, raw) {
    var row = el("div", "detail-row");
    row.appendChild(el("span", "", label));
    if (raw) {
      row.appendChild(el("div", "raw-box", value === undefined || value === null ? "—" : String(value)));
    } else if (label === "Evidence ID") {
      row.appendChild(el("code", "", String(value || "—")));
    } else {
      row.appendChild(el("strong", "", value === undefined || value === null || value === "" ? "—" : String(value)));
    }
    return row;
  }

  function openEvidence(id) {
    if (!state.current) return;
    var item = (state.current.evidence || []).filter(function (entry) { return entry.id === id; })[0];
    if (!item) return;
    var status = (state.current.provider_status || []).filter(function (p) { return p.provider === item.provider; })[0] || {};

    dom.drawerTitle.textContent = item.signal_type.replace(/_/g, " ").toLowerCase();
    clear(dom.drawerBody);
    dom.drawerBody.appendChild(detailRow("Evidence ID", item.id));
    dom.drawerBody.appendChild(detailRow("Source", item.provider));
    dom.drawerBody.appendChild(detailRow("Signal", item.signal));
    dom.drawerBody.appendChild(detailRow("Severity", item.severity));
    dom.drawerBody.appendChild(detailRow("Verification", item.reliability + " reliability · " + item.freshness + " freshness"));
    dom.drawerBody.appendChild(detailRow("Affected location", item.location_label || "Not attributable in this run"));
    dom.drawerBody.appendChild(detailRow("Observation timestamp (UTC)", fmtInstant(item.observed_at)));
    dom.drawerBody.appendChild(detailRow("Forecast validity (UTC)", fmtInstant(item.valid_from) + " → " + fmtInstant(item.valid_to)));
    dom.drawerBody.appendChild(detailRow("Retrieved from provider (UTC)", fmtInstant(status.fetched_at)));
    dom.drawerBody.appendChild(detailRow("Geographic relevance", item.geography + " · temporal overlap " + item.temporal_overlap));
    dom.drawerBody.appendChild(detailRow("Interpretation by RouteGuard", item.relevance_reason));
    dom.drawerBody.appendChild(detailRow("Original information", truncate(item.raw_excerpt, 240), true));
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

  /* ---------- provider status ---------- */

  function renderProviders(data) {
    clear(dom.providers);
    (data.provider_status || []).forEach(function (status) {
      var card = el("div", "provider-card");
      var heading = el("h4");
      heading.appendChild(document.createTextNode(status.provider));
      heading.appendChild(el("span", "status-pill " + String(status.status).toLowerCase(), status.status));
      card.appendChild(heading);
      card.appendChild(el("p", "", "HTTP " + (status.http_status === null ? "—" : status.http_status) +
        " · " + status.latency_ms + " ms · " + status.evidence_count + " evidence item(s)"));
      if (status.note) card.appendChild(el("p", "", status.note));
      if (status.error) card.appendChild(el("p", "", "Error: " + status.error));
      var link = el("a", "", "Authoritative source ↗");
      link.href = safeUrl(status.authoritative_url, "https://www.weather.gov/");
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      card.appendChild(link);
      dom.providers.appendChild(card);
    });
  }

  /* ---------- master render ---------- */

  function render(data) {
    state.current = data;
    state.highlighted = null;
    state.activeAirport = null;
    dom.emptyTitle.textContent = "Awaiting an assessment";
    dom.emptySubtitle.textContent = "Enter a route above to populate the command centre.";
    show(dom.empty, false);
    show(dom.results, true);
    renderSummary(data);
    renderActions(data);
    renderRules(data);
    renderIntel(data);
    renderMap(data);
    renderTimeline(data);
    renderDistribution();
    renderFilters();
    renderEvidence(data);
    renderProviders(data);
  }

  /* ---------- request flow ---------- */

  function setBusy(busy) {
    state.busy = busy;
    dom.submit.disabled = busy;
    dom.refresh.disabled = busy || !state.current;
    dom.submit.querySelector("span").textContent = busy ? "Assessing…" : "Assess route";
    show(dom.loadingPill, busy);
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
        if (isRefresh) {
          toast("Sources refreshed · " + (data.evidence || []).length + " evidence item(s) · " + data.classification);
        }
      })
      .catch(function (envelope) {
        // Never leave a previous assessment on screen after a failed request:
        // stale results next to a fresh error are actively misleading.
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
      .finally(function () {
        setBusy(false);
      });
  }

  /* ---------- command palette ---------- */

  function commandList() {
    var commands = [
      { label: "New assessment", hint: "Focus origin", run: function () { dom.origin.focus(); dom.origin.select(); } },
      { label: "Refresh current assessment", hint: "Re-query sources", run: function () { if (state.lastPayload) submit(state.lastPayload, true); } },
      { label: "Go to evidence ledger", hint: "Scroll", run: function () { dom.evidenceList.scrollIntoView({ block: "center" }); } },
      { label: "Go to route map", hint: "Scroll", run: function () { dom.map.scrollIntoView({ block: "center" }); } },
      { label: "Go to signal timeline", hint: "Scroll", run: function () { dom.timeline.scrollIntoView({ block: "center" }); } },
      { label: "Go to source coverage", hint: "Scroll", run: function () { dom.providers.scrollIntoView({ block: "center" }); } },
      { label: "Clear evidence filters", hint: "View all", run: function () { filterEvidence("all"); renderFilters(); } },
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

  document.querySelectorAll(".airport-block").forEach(function (node) {
    node.addEventListener("click", function () { focusAirport(node.getAttribute("data-airport")); });
    node.addEventListener("keydown", function (event) {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        focusAirport(node.getAttribute("data-airport"));
      }
    });
  });

  dom.drawerClose.addEventListener("click", closeDrawer);
  dom.drawerOverlay.addEventListener("click", closeDrawer);
  dom.drawerMap.addEventListener("click", function () {
    if (state.drawerEvidenceId) {
      highlightEvidence(state.drawerEvidenceId);
      dom.map.scrollIntoView({ block: "center" });
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
})();
