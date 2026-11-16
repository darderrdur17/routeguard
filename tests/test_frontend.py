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
    assert "show(dom.loadingSkeleton, busy && !state.current)" in APP
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
