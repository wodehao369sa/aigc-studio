"""Local-only polling endpoint for the systemd timer."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..serializers import task_dict

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/api/internal/poll")
async def poll(request: Request):
    scheduler = request.app.state.scheduler
    try:
        task = await scheduler.poll_once()
    except Exception as error:  # noqa: BLE001
        logger.exception("internal poll failed")
        return JSONResponse({"error": str(error)}, status_code=500)
    return {"task": task_dict(task) if task else None}
