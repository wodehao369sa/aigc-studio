"""Health check."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/api/health")
def health(request: Request):
    ctx = request.app.state.ctx
    checks: dict[str, str] = {"app": "ok"}
    try:
        ctx.db.query_one("SELECT 1")
        checks["database"] = "ok"
    except Exception:  # noqa: BLE001
        checks["database"] = "error"
    try:
        ctx.media.ensure_root()
        checks["media"] = "ok"
    except Exception:  # noqa: BLE001
        checks["media"] = "error"
    status_code = 200 if all(value == "ok" for value in checks.values()) else 503
    return JSONResponse(checks, status_code=status_code)
