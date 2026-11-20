"""Model catalog API."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..catalog import CAPABILITIES
from ..serializers import model_dict
from ..services import tasks as tasks_service

router = APIRouter()


@router.get("/api/models")
def list_models(request: Request, capability: str | None = None):
    if capability is not None and capability not in CAPABILITIES:
        raise HTTPException(status_code=400, detail="无效的能力。")
    models = tasks_service.list_models(request.app.state.ctx, capability=capability)
    return [model_dict(model) for model in models]
