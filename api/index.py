"""Vercel serverless entrypoint for the RouteGuard FastAPI application."""

from __future__ import annotations

from app.main import app as fastapi_app

# Vercel's Python builder recognises either ``app`` or ``application``.
app = fastapi_app
application = fastapi_app
