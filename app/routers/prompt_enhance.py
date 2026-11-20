"""Prompt enhancement settings and preview API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .. import repository
from ..catalog import CAPABILITIES
from ..entities import ModelPromptBinding, PromptTemplate
from ..services import prompt_enhance as service
from ..services.prompt_enhance import PromptEnhanceError

router = APIRouter()


class TemplateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    content: str = Field(min_length=1, max_length=20000)
    asSystem: bool = False


class TemplateUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    content: str = Field(min_length=1, max_length=20000)
    asSystem: bool = False


class BindingItem(BaseModel):
    templateId: str = Field(min_length=1)
    enhancerModelId: str = Field(min_length=1)
    capability: str | None = None
    isDefault: bool = False
    sortOrder: int = 0


class BindingsRequest(BaseModel):
    bindings: list[BindingItem] = Field(default_factory=list, max_length=50)


class GlobalConfigRequest(BaseModel):
    enabled: bool
    templateId: str | None = None
    enhancerModelId: str | None = None


class PreviewRequest(BaseModel):
    templateId: str = Field(min_length=1)
    enhancerModelId: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    modelId: str = Field(min_length=1)
    capability: str
    hasReference: bool = False


def _template_dict(template: PromptTemplate) -> dict[str, Any]:
    return {
        "id": template.id,
        "name": template.name,
        "content": template.content,
        "asSystem": template.as_system,
        "createdAt": template.created_at,
        "updatedAt": template.updated_at,
    }


def _binding_dict(binding: ModelPromptBinding, template_name: str | None = None) -> dict[str, Any]:
    return {
        "templateId": binding.template_id,
        "enhancerModelId": binding.enhancer_model_id,
        "isDefault": binding.is_default,
        "sortOrder": binding.sort_order,
        "templateName": template_name,
        "capability": binding.capability,
    }


@router.get("/api/settings/prompt-templates")
def list_templates(request: Request):
    return [_template_dict(item) for item in service.list_templates(request.app.state.ctx)]


@router.post("/api/settings/prompt-templates", status_code=201)
def create_template(request: Request, body: TemplateRequest):
    try:
        template = service.create_template(
            request.app.state.ctx, body.name, body.content, as_system=body.asSystem
        )
    except PromptEnhanceError as error:
        raise HTTPException(status_code=400, detail=str(error))
    return _template_dict(template)


@router.patch("/api/settings/prompt-templates/{template_id}")
def update_template(template_id: str, request: Request, body: TemplateUpdateRequest):
    try:
        template = service.update_template(
            request.app.state.ctx, template_id, body.name, body.content, as_system=body.asSystem
        )
    except PromptEnhanceError as error:
        raise HTTPException(status_code=400, detail=str(error))
    return _template_dict(template)


@router.delete("/api/settings/prompt-templates/{template_id}", status_code=204)
def delete_template(template_id: str, request: Request):
    service.delete_template(request.app.state.ctx, template_id)
    return None


@router.get("/api/settings/models/{model_id}/prompt-templates")
def list_bindings(model_id: str, request: Request):
    if not repository.get_model(request.app.state.ctx.db, model_id):
        raise HTTPException(status_code=404, detail="模型不存在")
    names = {
        item.id: item.name for item in repository.list_prompt_templates(request.app.state.ctx.db)
    }
    return [
        _binding_dict(item, names.get(item.template_id))
        for item in service.list_bindings(request.app.state.ctx, model_id)
    ]


@router.put("/api/settings/models/{model_id}/prompt-templates")
def set_bindings(model_id: str, request: Request, body: BindingsRequest):
    try:
        bindings = [
            {
                "templateId": item.templateId,
                "enhancerModelId": item.enhancerModelId,
                "capability": item.capability,
                "isDefault": item.isDefault,
                "sortOrder": item.sortOrder,
            }
            for item in body.bindings
        ]
        saved = service.set_bindings(request.app.state.ctx, model_id, bindings)
    except PromptEnhanceError as error:
        raise HTTPException(status_code=400, detail=str(error))
    names = {
        item.id: item.name for item in repository.list_prompt_templates(request.app.state.ctx.db)
    }
    return [_binding_dict(item, names.get(item.template_id)) for item in saved]


@router.get("/api/settings/prompt-enhance-default")
def get_enhance_default(request: Request):
    return service.get_global_config(request.app.state.ctx)


@router.put("/api/settings/prompt-enhance-default")
def save_enhance_default(request: Request, body: GlobalConfigRequest):
    try:
        return service.save_global_config(
            request.app.state.ctx, body.enabled, body.templateId, body.enhancerModelId
        )
    except PromptEnhanceError as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.post("/api/prompt-enhance/preview")
async def preview(request: Request, body: PreviewRequest):
    if body.capability not in CAPABILITIES:
        raise HTTPException(status_code=400, detail="无效的能力。")
    try:
        return await service.preview(
            request.app.state.ctx,
            template_id=body.templateId,
            enhancer_model_id=body.enhancerModelId,
            prompt=body.prompt,
            model_id=body.modelId,
            capability=body.capability,
            has_reference=body.hasReference,
        )
    except PromptEnhanceError as error:
        raise HTTPException(status_code=400, detail=str(error))
