"""FastAPI application: static UI, assessment API and structured errors."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Annotated, Any
from xml.sax.saxutils import escape

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import Scope

from app.cities import CityRegistry
from app.config import settings
from app.history import HistoryService
from app.logging import CorrelationIdMiddleware, emit, new_request_id
from app.models import AssessRequest, ErrorEnvelope, HistoryRequest
from app.service import AssessmentService, RouteInputError

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
SITE_URL_PLACEHOLDER = "{{SITE_URL}}"

class CanonicalStaticFiles(StaticFiles):
    """Serve assets without exposing the raw HTML template as a duplicate page."""

    async def get_response(self, path: str, scope: Scope):
        if path in {"index.html", "./index.html"}:
            return RedirectResponse(url="/", status_code=307)
        return await super().get_response(path, scope)


app = FastAPI(
    title="RouteGuard Prototype",
    description="Deterministic, evidence-driven US airport-level travel assessment.",
    version="0.1.0",
)
app.add_middleware(CorrelationIdMiddleware)
app.mount("/static", CanonicalStaticFiles(directory=str(STATIC_DIR)), name="static")

# Baseline hardening headers for every response. The CSP is tuned to the real
# frontend: an inline ES-module bootstrap imports MapLibre GL JS from unpkg,
# Geist fonts load from Google, and the map fetches OpenFreeMap vector tiles.
# 'unsafe-inline' on script/style is required because the inline module and
# MapLibre's injected styles cannot be nonced without editing the static HTML.
SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://unpkg.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://unpkg.com; "
        "font-src 'self' data: https://fonts.gstatic.com; "
        "img-src 'self' data: blob: https://tiles.openfreemap.org https://*.openfreemap.org; "
        "connect-src 'self' https://unpkg.com https://tiles.openfreemap.org https://*.openfreemap.org; "
        "worker-src 'self' blob: https://unpkg.com; "
        "frame-ancestors 'none'; "
        "object-src 'none'; "
        "base-uri 'self'"
    ),
}


@app.middleware("http")
async def security_headers(request: Request, call_next: Any) -> Response:
    """Attach the baseline security headers without altering request IDs."""
    response = await call_next(request)
    for name, value in SECURITY_HEADERS.items():
        response.headers[name] = value
    return response


_service = AssessmentService()
_history_service = HistoryService()


def _request_id(request: Request) -> str:
    """Return the correlation ID attached by middleware."""
    return getattr(request.state, "request_id", new_request_id())


def _site_url(request: Request) -> str:
    """Return the canonical public origin used in SEO and sitemap output."""
    if settings.site_url:
        return settings.site_url
    return str(request.base_url).rstrip("/")


def _error_response(
    *, code: str, message: str, request_id: str, status_code: int, details: Any = None
) -> JSONResponse:
    """Return the uniform error envelope."""
    envelope = ErrorEnvelope(
        code=code, message=message, request_id=request_id, details=details
    )
    return JSONResponse(
        status_code=status_code, content=envelope.model_dump(mode="json")
    )


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Return the uniform envelope for framework errors such as 404 and 405."""
    code = {
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
    }.get(exc.status_code, "HTTP_ERROR")
    emit(
        "request_rejected",
        request_id=_request_id(request),
        code=code,
        http_status=exc.status_code,
    )
    return _error_response(
        code=code,
        message=str(exc.detail) if exc.detail else "The requested resource is unavailable.",
        request_id=_request_id(request),
        status_code=exc.status_code,
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Map Pydantic validation failures to R00 error codes."""
    errors = exc.errors()
    locations = [tuple(str(part) for part in item.get("loc", ())) for item in errors]
    # Route shape is the first actionable problem: it tells the caller which
    # curated airport/city to replace before re-checking the travel date.
    if any(
        any(part in {"origin", "destination"} for part in location)
        for location in locations
    ):
        code = "INVALID_ROUTE"
    elif any("date" in ".".join(location) for location in locations):
        # Substring match so query.date, start_date and end_date all map here.
        code = "INVALID_DATE"
    else:
        code = "INVALID_REQUEST"
    details = {
        "errors": [
            {
                "field": ".".join(str(part) for part in item.get("loc", ())),
                "message": str(item.get("msg", "invalid value")),
            }
            for item in errors
        ]
    }
    # Surface the first human-readable validation message instead of a generic
    # banner: the Pydantic wording already names the offending value and bound.
    first_message = str(errors[0].get("msg", "")) if errors else ""
    if first_message.startswith("Value error, "):
        first_message = first_message[len("Value error, ") :]
    emit(
        "request_rejected",
        request_id=_request_id(request),
        code=code,
        error_count=len(errors),
    )
    return _error_response(
        code=code,
        message=first_message.strip() or "Request validation failed.",
        request_id=_request_id(request),
        status_code=422,
        details=details,
    )


@app.exception_handler(RouteInputError)
async def route_input_error_handler(
    request: Request, exc: RouteInputError
) -> JSONResponse:
    """Map unmapped cities and other input-resolution failures to 422."""
    # Keep the documented four-field envelope but give service-raised errors
    # the same machine-readable ``errors`` array that Pydantic validation gets.
    details = exc.details
    if not isinstance(details, dict) or "errors" not in details:
        normalized = dict(details) if isinstance(details, dict) else {}
        normalized["errors"] = [{"field": "request", "message": exc.message}]
        details = normalized
    emit("request_rejected", request_id=_request_id(request), code=exc.code)
    return _error_response(
        code=exc.code,
        message=exc.message,
        request_id=_request_id(request),
        status_code=422,
        details=details,
    )


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return a redacted 500 envelope for unexpected server errors."""
    emit(
        "unexpected_error",
        request_id=_request_id(request),
        exception_class=type(exc).__name__,
    )
    return _error_response(
        code="INTERNAL_ERROR",
        message="The assessment could not be completed.",
        request_id=_request_id(request),
        status_code=500,
    )


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def index(request: Request) -> HTMLResponse:
    """Serve the dependency-free frontend with the canonical origin resolved."""
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html.replace(SITE_URL_PLACEHOLDER, _site_url(request)))


@app.get("/robots.txt", include_in_schema=False)
async def robots(request: Request) -> PlainTextResponse:
    """Expose indexable public pages only; APIs and generated docs stay out."""
    base = _site_url(request)
    content = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /api/\n"
        "Disallow: /docs\n"
        "Disallow: /redoc\n"
        "Disallow: /openapi.json\n"
        f"Sitemap: {base}/sitemap.xml\n"
    )
    return PlainTextResponse(
        content, headers={"Cache-Control": "public, max-age=3600"}
    )


@app.get("/sitemap.xml", include_in_schema=False)
async def sitemap(request: Request) -> Response:
    """Publish a sitemap containing only the genuinely public product page."""
    base = escape(_site_url(request))
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        "  <url>\n"
        f"    <loc>{base}/</loc>\n"
        f"    <lastmod>{date.today().isoformat()}</lastmod>\n"
        "    <changefreq>weekly</changefreq>\n"
        "    <priority>1.0</priority>\n"
        "  </url>\n"
        "</urlset>\n"
    )
    return Response(
        content=xml,
        media_type="application/xml",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@app.get("/api/health")
async def health() -> dict[str, str]:
    """Return a minimal liveness response."""
    return {"status": "ok"}


@app.get("/api/airports")
async def airports() -> list[dict[str, str]]:
    """Return the curated airport registry backing the UI autocomplete.

    This is the same registry the assessment service resolves against, so the
    interface never offers an airport the backend cannot assess.
    """
    return [
        {
            "city": airport.city,
            "state": airport.state,
            "country": airport.country,
            "region": airport.region,
            "iata": airport.iata,
            "icao": airport.icao,
        }
        for airport in CityRegistry().all()
    ]


@app.post("/api/assess")
async def assess(payload: AssessRequest, request: Request) -> JSONResponse:
    """Assess one origin/destination/date route.

    FastAPI validates the body (R00); provider failures are represented in the
    Assessment response, never raised to the client.
    """
    assessment = await _service.assess(payload, _request_id(request))
    return JSONResponse(status_code=200, content=assessment.model_dump(mode="json"))


@app.get("/api/history")
async def history(
    query: Annotated[HistoryRequest, Query()], request: Request
) -> JSONResponse:
    """Return daily ERA5 archive reanalysis for one route and date range.

    Field-level validation is handled by the shared RequestValidationError
    handler. RouteInputError from the history service maps INVALID_DATE and
    INVALID_ROUTE to 422 and UPSTREAM_UNAVAILABLE to 502, all with the uniform
    error envelope. Partial upstream failures stay inside the 200 payload as
    per-airport ``unavailable`` blocks.
    """
    request_id = _request_id(request)
    try:
        payload = await _history_service.fetch_history(
            query.origin,
            query.destination,
            query.start_date,
            query.end_date,
            request_id,
        )
    except RouteInputError as exc:
        emit("request_rejected", request_id=request_id, code=exc.code)
        return _error_response(
            code=exc.code,
            message=exc.message,
            request_id=request_id,
            status_code=502 if exc.code == "UPSTREAM_UNAVAILABLE" else 422,
            details=exc.details,
        )
    return JSONResponse(status_code=200, content=payload)
