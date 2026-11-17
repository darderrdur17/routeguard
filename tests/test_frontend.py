"""Static contract checks for the V29-inspired RouteGuard frontend shell."""

from __future__ import annotations

from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parents[1] / "static"
INDEX = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
STYLES = (STATIC_DIR / "styles.css").read_text(encoding="utf-8")
APP = (STATIC_DIR / "app.js").read_text(encoding="utf-8")


def test_shell_has_dark_rail_light_canvas_map_and_context_panel() -> None:
    """The product uses the three-part V29-inspired workspace, not a dark bento page."""
    assert 'class="rail"' in INDEX
    assert 'class="app-frame"' in INDEX
    assert "<h1>Travel Intelligence</h1>" in INDEX
    assert 'id="map-stage"' in INDEX
    assert 'id="context-panel"' in INDEX
    assert "--canvas: #f3f4f6" in STYLES
    assert "background: var(--canvas)" in STYLES


def test_map_layer_controls_are_real_and_unavailable_layer_is_disabled() -> None:
    """Every visible layer has data; airport operations is honestly unavailable."""
    for layer_id in (
        "layer-airports",
        "layer-routes",
        "layer-weather",
        "layer-aviation",
    ):
        assert f'id="{layer_id}"' in INDEX
        assert f'id="{layer_id}" type="checkbox" checked' in INDEX
    assert 'id="layer-operations" type="checkbox" disabled' in INDEX
    assert "Illustrative airport-pair reference" in INDEX
    assert "OpenFreeMap" in INDEX and "OpenStreetMap" in INDEX


def test_progressive_disclosure_controls_exist() -> None:
    """Beginner/analyst modes and operational view pills are present."""
    assert 'id="mode-overview"' in INDEX
    assert 'id="mode-analyst"' in INDEX
    for view in ("all", "routes", "weather", "operations", "advisories", "high"):
        assert f'data-view="{view}"' in INDEX
    assert 'body[data-mode="overview"] .analyst-only' in STYLES
    assert 'body[data-mode="analyst"] .overview-only' in STYLES
    assert 'id="glossary"' in INDEX


def test_loading_states_are_honest_and_accessible() -> None:
    """Skeletons and announcements carry no fabricated progress or source stages."""
    assert 'id="loading-skeleton"' in INDEX
    assert 'id="loading-announcement"' in INDEX
    assert 'role="status"' in INDEX and 'aria-live="polite"' in INDEX
    assert "aria-busy" in APP
    assert "show(dom.loadingSkeleton, busy && !hasCurrent)" in APP
    assert "Contacting public sources" in INDEX
    assert "percent" not in APP.lower()


def test_maplibre_is_progressive_enhancement_with_svg_fallback() -> None:
    """A keyless basemap is used when available; the SVG map remains usable."""
    assert "https://tiles.openfreemap.org/styles/positron" in APP
    assert "window.RouteGuardMapLibre" in APP
    assert 'id="map-canvas"' in INDEX
    assert 'id="route-map"' in INDEX
    assert "body.maplibre-ready #route-map" in STYLES
    assert "route-reference-line" in APP
    assert ".innerHTML" not in APP


def test_accessibility_and_motion_rules_are_preserved() -> None:
    """Keyboard access, hidden semantics and reduced motion survive the redesign."""
    assert ".skip-link" in STYLES
    assert ":focus-visible" in STYLES
    assert "[hidden] { display: none !important; }" in STYLES
    assert "@media (prefers-reduced-motion: reduce)" in STYLES
    assert "focusAirport" in APP and "keydown" in APP


def test_first_assessment_loading_feedback_is_visible_outside_results() -> None:
    """Skeleton/status are not buried inside the initially hidden results section."""
    skeleton_position = INDEX.find('id="loading-skeleton"')
    announcement_position = INDEX.find('id="loading-announcement"')
    results_position = INDEX.find('id="results"')
    assert 0 < skeleton_position < results_position
    assert 0 < announcement_position < results_position
    assert "show(dom.loadingAnnouncement, busy)" in APP
    assert "show(dom.loadingSkeleton, busy && !hasCurrent)" in APP


def test_marker_transforms_do_not_override_geographic_placement() -> None:
    """MapLibre owns the marker element transform; visual transforms stay inside."""
    marker_block = STYLES[STYLES.find(".rg-marker {"):STYLES.find(".rg-marker > span")]
    assert "transform:" not in marker_block
    assert "animation:" not in marker_block
    assert ".rg-marker > span" in STYLES
    assert "animation: markerIn" in STYLES


def test_dialogs_manage_focus() -> None:
    """Drawer and palette trap focus and restore it when closed."""
    assert "trapDialogFocus" in APP
    assert "releaseDialogFocus" in APP
    assert "trapDialogFocus(dom.drawer)" in APP
    assert "releaseDialogFocus()" in APP
    assert "trapDialogFocus(dom.palette)" in APP


def test_buttons_do_not_override_button_semantics() -> None:
    """Evidence and timeline buttons keep native button roles."""
    assert 'button.setAttribute("role", "listitem")' not in APP


def test_glossary_terms_are_keyboard_accessible() -> None:
    """Glossary entries are real buttons with full accessible names."""
    assert 'class="glossary-term"' in INDEX
    assert "<title>" not in INDEX.split('id="glossary"')[1].split("</div>")[0]
    assert "aria-label=" in INDEX.split('id="glossary"')[1]


def test_safe_url_rejects_empty_or_placeholder_sources() -> None:
    """The defensive URL helper falls back instead of making local junk URLs."""
    assert "/^(undefined|null)$/i.test(text)" in APP
    assert "if (value === undefined || value === null) return fallback;" in APP


def test_maplibre_does_not_add_a_second_fullscreen_control() -> None:
    """Fullscreen is handled once by the shared custom control."""
    assert "new ml.FullscreenControl" not in APP
    assert "toggleFullscreen" in APP


def test_raw_index_template_is_not_served_as_a_duplicate_page() -> None:
    """The static handler redirects the template to the templated canonical page."""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app, follow_redirects=False)
    response = client.get("/static/index.html")
    assert response.status_code == 307
    assert response.headers["location"] == "/"


def test_workspace_visibility_cannot_go_blank() -> None:
    """One synchronizer owns results/skeleton/empty so the canvas never blanks."""
    assert "function syncWorkspace()" in APP
    assert "show(dom.results, hasCurrent)" in APP
    assert "show(dom.empty, !hasCurrent && !busy)" in APP
    assert "show(dom.loadingSkeleton, busy && !hasCurrent)" in APP
    # setBusy, render and the error path all delegate to the synchronizer.
    assert APP.count("syncWorkspace()") >= 4
    assert "show(dom.results, true)" not in APP
    assert "show(dom.results, false)" not in APP


def test_render_failure_is_contained_not_silent() -> None:
    """A rendering exception surfaces a message instead of a blank workspace."""
    assert "catch (renderError)" in APP
    assert '"RENDER_FAILED"' in APP


def test_past_dates_are_guarded_in_the_client() -> None:
    """The picker spans the retrospective window and the guard explains it."""
    assert "dom.date.min = originAwareMinDate();" in APP
    assert "function todayLocal()" in APP
    assert "function retrospectiveMinDate()" in APP
    assert "function originAwareMinDate()" in APP
    assert "payload.date < retrospectiveMinDate()" in APP
    assert "Retrospective assessments reach 7 days back only" in APP
    assert "Today onwards — or up to 7 days back" in INDEX


def test_retrospective_assessments_are_labelled_in_the_ui() -> None:
    """A retrospective run is marked in the coverage badge and journey basis."""
    assert 'data.assessment_mode === "retrospective"' in APP
    assert "RETROSPECTIVE · " in APP
    assert 'String(route.basis || "").indexOf("retrospective")' in APP


def test_validation_field_paths_no_longer_clutter_the_visible_error() -> None:
    """Raw machine paths stay in the console, not in the user-facing message."""
    assert "console.info(\"Validation details:\", envelope.details.errors)" in APP
    assert 'join(", ")' not in APP.split("function submit(")[1].split("/* ----------")[0]


def test_mode_switch_explains_its_functionality() -> None:
    """Overview/Analyst buttons carry descriptive tooltips for discovery."""
    assert 'title="Plain-language summary for trip planning"' in INDEX
    assert 'title="Raw excerpts, reliability scores and technical detail"' in INDEX
    assert "aria-label=\"Experience mode: Overview shows plain-language summaries" in INDEX


def test_horizontal_overflow_is_clipped_for_safari() -> None:
    """The page never pans horizontally; sticky positioning is preserved."""
    assert "html, body { overflow-x: clip; }" in STYLES
    assert "--rail-w: 64px" in STYLES


def test_history_view_shell_is_wired_into_the_workspace() -> None:
    """The History pill, section, toolbar and context entry point all exist."""
    assert 'data-view="history"' in INDEX
    assert 'id="history-section"' in INDEX
    assert 'id="history-origin"' in INDEX and 'id="history-destination"' in INDEX
    assert 'id="history-start"' in INDEX and 'id="history-end"' in INDEX
    assert 'id="history-fetch"' in INDEX
    assert 'id="history-error"' in INDEX
    assert 'id="history-provenance"' in INDEX
    assert 'id="history-origin-panel"' in INDEX and 'id="history-destination-panel"' in INDEX
    assert 'id="history-origin-table"' in INDEX and 'id="history-destination-table"' in INDEX
    assert 'id="history-origin-svg"' in INDEX and 'id="history-destination-svg"' in INDEX
    assert 'id="history-open"' in INDEX
    # The reanalysis labelling must be visible in both the markup and the JS.
    assert "ERA5 reanalysis (model), not observations" in INDEX
    assert "ERA5 reanalysis (model), not observations" in APP


def test_history_view_visibility_rules_and_renderers_exist() -> None:
    """The body[data-view] rules own section switching and the JS renders offline."""
    assert 'body[data-view="history"] #results { display: none; }' in STYLES
    assert 'body[data-view="history"] #history-section { display: block; }' in STYLES
    assert "function fetchHistory()" in APP
    assert "function renderHistory(" in APP
    assert "function renderHistoryAirport(" in APP
    assert "function drawHistoryBarGroup(" in APP
    assert 'applyView("history")' in APP
    assert '"no data"' in APP
    # History rendering stays on the safe-DOM path: no innerHTML anywhere.
    assert ".innerHTML" not in APP


def test_glossary_terms_surface_their_definitions() -> None:
    """Glossary buttons are wired to the shared toast, not dead controls."""
    assert 'querySelectorAll(".glossary-term")' in APP
    assert " definition: " in APP
    assert "function toast(" in APP


def test_show_on_map_closes_the_drawer_before_focusing_the_map() -> None:
    """The map is revealed (drawer + overlay closed) before it is scrolled to."""
    drawer_block = APP[APP.find('dom.drawerMap.addEventListener'):APP.find("dom.paletteOpen.addEventListener")]
    assert "closeDrawer();" in drawer_block
    assert drawer_block.index("closeDrawer();") < drawer_block.index("selectEvidence(")
