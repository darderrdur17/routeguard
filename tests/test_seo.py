"""SEO and public-web metadata checks for the served product page."""

from __future__ import annotations

import struct
from pathlib import Path

from fastapi.testclient import TestClient

import app.main as main_module

TITLE = "RouteGuard | US Travel Disruption Intelligence"
DESCRIPTION = (
    "Assess potential US air-travel disruptions with consolidated weather, "
    "airport and aviation intelligence. Explore evidence, understand travel "
    "risks and discover actionable recommendations."
)
CANONICAL = "https://routeguard.example"


def _client(monkeypatch) -> TestClient:
    """Pin the canonical origin so metadata assertions stay deterministic."""
    monkeypatch.setattr(main_module, "_site_url", lambda request: CANONICAL)
    return TestClient(main_module.app)


def test_index_serves_exact_seo_identity(monkeypatch) -> None:
    """The browser title and meta description match the approved wording."""
    response = _client(monkeypatch).get("/")
    assert response.status_code == 200
    html = response.text
    assert f"<title>{TITLE}</title>" in html
    assert f'name="description"\n      content="{DESCRIPTION}"' in html
    assert f'property="og:title"\n      content="{TITLE}"' in html
    assert 'name="twitter:card" content="summary_large_image"' in html


def test_index_resolves_canonical_and_social_urls(monkeypatch) -> None:
    """Template placeholders never reach the browser unresolved."""
    html = _client(monkeypatch).get("/").text
    assert "{{SITE_URL}}" not in html
    assert f'<link rel="canonical" href="{CANONICAL}/" />' in html
    assert f'property="og:url" content="{CANONICAL}/"' in html
    assert (
        f'property="og:image" content="{CANONICAL}/static/og-image.png"'
        in html
    )
    assert 'rel="icon" href="/static/favicon.svg"' in html
    assert 'rel="apple-touch-icon" href="/static/apple-touch-icon.png"' in html


def test_robots_exposes_only_public_pages(monkeypatch) -> None:
    """Robots points crawlers to the sitemap and excludes non-product routes."""
    response = _client(monkeypatch).get("/robots.txt")
    assert response.status_code == 200
    body = response.text
    assert "User-agent: *" in body
    assert "Allow: /" in body
    assert "Disallow: /api/" in body
    assert "Disallow: /docs" in body
    assert f"Sitemap: {CANONICAL}/sitemap.xml" in body


def test_sitemap_contains_only_the_public_homepage(monkeypatch) -> None:
    """No API, documentation or preview route is offered for indexing."""
    response = _client(monkeypatch).get("/sitemap.xml")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    body = response.text
    assert "<loc>https://routeguard.example/</loc>" in body
    assert body.count("<loc>") == 1
    assert "/api/" not in body
    assert "/docs" not in body


def test_open_graph_image_has_required_dimensions() -> None:
    """The social preview is a real 1200x630 PNG, not a placeholder."""
    path = main_module.STATIC_DIR / "og-image.png"
    payload = path.read_bytes()
    assert payload[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", payload[16:24])
    assert (width, height) == (1200, 630)
    assert (main_module.STATIC_DIR / "apple-touch-icon.png").exists()
