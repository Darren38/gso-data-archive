"""Public, read-only HTTP API + dashboard static files.

There are deliberately no write or admin endpoints: collection runs in a
separate process with its own (write-capable) credentials. Point
API_DATABASE_URL at a read-only database role in production.
"""

from __future__ import annotations

import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from .. import analytics, export
from ..config import Settings, load_settings
from ..db import make_engine
from ..timeutil import MYT, UTC, myt_day_bounds_utc, myt_today, utcnow

SERIES_KEY = re.compile(r"^[a-z0-9_]{1,64}\.[a-z0-9_]{1,64}$")
MAX_POINT_RANGE_DAYS = 400
MAX_DAILY_RANGE_DAYS = 366 * 30
MAX_EXPORT_SERIES = 12


def _parse_instant(value: str | None, default: datetime) -> datetime:
    if not value:
        return default
    try:
        if len(value) == 10:
            return datetime.combine(date.fromisoformat(value), datetime.min.time(), tzinfo=MYT).astimezone(UTC)
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(400, f"invalid date/time {value!r}; use ISO 8601") from None
    return (dt if dt.tzinfo else dt.replace(tzinfo=MYT)).astimezone(UTC)


def _parse_day(value: str | None, default: date) -> date:
    if not value:
        return default
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        raise HTTPException(400, f"invalid date {value!r}; use YYYY-MM-DD") from None


def create_app(settings: Settings | None = None, engine: Engine | None = None) -> FastAPI:
    settings = settings or load_settings()
    engine = engine or make_engine(os.environ.get("API_DATABASE_URL") or settings.database_url)
    app = FastAPI(title="GSO Data Archive API", version="2.0.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
    if settings.api_cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=settings.api_cors_origins, allow_methods=["GET"],
                           allow_headers=["*"])

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        return response

    def series_or_404(conn, key: str) -> analytics.SeriesInfo:
        if not SERIES_KEY.match(key):
            raise HTTPException(400, "invalid series key")
        info = analytics.get_series(conn, key)
        if info is None:
            raise HTTPException(404, f"unknown series {key!r}")
        return info

    @app.exception_handler(SQLAlchemyError)
    async def db_error(_request, exc):  # never leak connection strings
        return JSONResponse({"detail": "database unavailable"}, status_code=503)

    @app.get("/api/v1/health")
    def health():
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except SQLAlchemyError:
            return JSONResponse({"ok": False, "database": "unreachable"}, status_code=503)
        return {"ok": True, "database": "ok", "time": utcnow().isoformat()}

    @app.get("/api/v1/meta")
    def meta():
        from ..export_static import collection_info

        with engine.connect() as conn:
            return {**analytics.meta(conn), "collection": collection_info(settings)}

    @app.get("/api/v1/status")
    def status():
        with engine.connect() as conn:
            return analytics.status(conn, settings.adapters, settings.gso_live_enabled)

    @app.get("/api/v1/series/{key}/points")
    def points(key: str, start: str | None = None, end: str | None = None):
        now = utcnow()
        t1 = _parse_instant(end, now)
        t0 = _parse_instant(start, t1 - timedelta(days=1))
        if t0 >= t1:
            raise HTTPException(400, "start must be before end")
        if (t1 - t0).days > MAX_POINT_RANGE_DAYS:
            raise HTTPException(400, f"range too long for raw points (max {MAX_POINT_RANGE_DAYS} days); use /daily")
        with engine.connect() as conn:
            return analytics.points(conn, series_or_404(conn, key), t0, t1)

    @app.get("/api/v1/series/{key}/daily")
    def daily(key: str, start: str | None = None, end: str | None = None,
              period: str = Query("day", pattern="^(day|week|month|year)$")):
        d1 = _parse_day(end, myt_today())
        d0 = _parse_day(start, d1 - timedelta(days=30))
        if d0 > d1:
            raise HTTPException(400, "start must not be after end")
        if (d1 - d0).days > MAX_DAILY_RANGE_DAYS:
            raise HTTPException(400, "range too long")
        with engine.connect() as conn:
            info = series_or_404(conn, key)
            days = analytics.daily(conn, info, d0, d1)
        rows = days if period == "day" else analytics.rollup(days, period)
        return {"series": key, "unit": info.unit, "period": period, "rows": rows, "is_demo": info.is_demo}

    @app.get("/api/v1/series/{key}/revisions")
    def revisions(key: str, start: str | None = None, end: str | None = None):
        now = utcnow()
        t1 = _parse_instant(end, now)
        t0 = _parse_instant(start, t1 - timedelta(days=30))
        with engine.connect() as conn:
            return {"series": key, "revisions": analytics.revisions(conn, series_or_404(conn, key), t0, t1)}

    @app.get("/api/v1/export")
    def export_data(series: str, start: str | None = None, end: str | None = None,
                    format: str = Query("csv", pattern="^(csv|xlsx)$")):
        keys = [k for k in series.split(",") if k]
        if not keys or len(keys) > MAX_EXPORT_SERIES:
            raise HTTPException(400, f"give 1–{MAX_EXPORT_SERIES} comma-separated series keys")
        today = myt_today()
        t0, _ = myt_day_bounds_utc(_parse_day(start, today - timedelta(days=7)))
        _, t1 = myt_day_bounds_utc(_parse_day(end, today))
        if (t1 - t0).days > MAX_POINT_RANGE_DAYS:
            raise HTTPException(400, f"export range limited to {MAX_POINT_RANGE_DAYS} days per request")
        with engine.connect() as conn:
            payloads = []
            for k in keys:
                info = series_or_404(conn, k)
                payloads.append((analytics.points(conn, info, t0, t1, max_points=10**9), info))
        rows = export.rows_for_export(payloads)
        stem = f"gso_{'_'.join(k.replace('.', '-') for k in keys)[:80]}_{t0.date()}_{t1.date()}"
        if format == "csv":
            return PlainTextResponse(export.to_csv(rows), media_type="text/csv; charset=utf-8",
                                     headers={"Content-Disposition": f'attachment; filename="{stem}.csv"'})
        query = {"series": ",".join(keys), "start_utc": t0.isoformat(), "end_utc": t1.isoformat()}
        return Response(export.to_xlsx(rows, query),
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="{stem}.xlsx"'})

    web_dir = Path(settings.web_dir)
    if web_dir.is_dir():
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
    return app


def app_factory() -> FastAPI:  # for `uvicorn --factory gso_archive.api.app:app_factory`
    return create_app()
