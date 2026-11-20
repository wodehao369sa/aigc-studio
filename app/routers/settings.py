"""Provider connection and model catalog settings API."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ..serializers import model_dict
from ..services import settings as settings_service
from ..services.settings import SettingsError

router = APIRouter()


class ProviderUpdateRequest(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    enabled: bool
    maxConcurrency: int = Field(default=1, ge=1, le=16)


class ModelRequest(BaseModel):
    providerId: str = Field(min_length=1, max_length=64)
    preset: str | None = None
    name: str = Field(min_length=1, max_length=100)
    externalModelId: str | None = None
    description: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    parameterSchema: list[dict] = Field(default_factory=list, max_length=32)
    inputConstraints: dict = Field(default_factory=dict)
    enabled: bool = True
    sortOrder: int = Field(default=0, ge=0, le=99999)


class ModelUpdateRequest(ModelRequest):
    id: str = Field(min_length=1, max_length=64)


@router.get("/api/settings/providers")
def list_providers(request: Request):
    return settings_service.list_providers(request.app.state.ctx)


@router.patch("/api/settings/providers")
def update_provider(request: Request, body: ProviderUpdateRequest):
    try:
        settings_service.update_provider(
            request.app.state.ctx,
            body.id,
            body.enabled,
            body.maxConcurrency,
        )
    except SettingsError as error:
        raise HTTPException(status_code=400, detail=str(error))
    return {"ok": True}


@router.post("/api/settings/providers/reload")
def reload_providers(request: Request):
    return settings_service.reload_providers(request.app.state.ctx)


@router.get("/api/settings/presets")
def list_presets(request: Request):
    return settings_service.list_presets(request.app.state.ctx)


@router.get("/api/settings/models")
def list_models(
    request: Request,
    capability: str | None = None,
    includeDisabled: bool = False,
):
    models = settings_service.list_models(
        request.app.state.ctx,
        capability=capability,
        include_disabled=includeDisabled,
    )
    return [model_dict(model) for model in models]


@router.post("/api/settings/models", status_code=201)
def create_model(request: Request, body: ModelRequest):
    try:
        model = settings_service.create_model(request.app.state.ctx, body.model_dump())
    except SettingsError as error:
        raise HTTPException(status_code=400, detail=str(error))
    return {"id": model.id}


@router.patch("/api/settings/models")
def update_model(request: Request, body: ModelUpdateRequest):
    try:
        model = settings_service.update_model(
            request.app.state.ctx,
            body.id,
            body.model_dump(exclude={"id"}),
        )
    except SettingsError as error:
        raise HTTPException(status_code=400, detail=str(error))
    return {"id": model.id}


@router.delete("/api/settings/models")
def delete_model(request: Request, id: str = Query(..., min_length=1, max_length=64)):
    try:
        settings_service.delete_model(request.app.state.ctx, id)
    except SettingsError as error:
        raise HTTPException(status_code=404, detail=str(error))
    return {"ok": True}
