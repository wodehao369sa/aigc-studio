"""Task API: create, query, retry, delete and bulk delete."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..catalog import CAPABILITIES, TASK_STATUSES
from ..serializers import task_detail_dict, task_dict, task_list_dict
from ..services import tasks as tasks_service

router = APIRouter()


class AssetRef(BaseModel):
    role: str = Field(min_length=1, max_length=64)
    assetId: str = Field(min_length=1, max_length=64)


class CreateTaskRequest(BaseModel):
    modelId: str = Field(min_length=1, max_length=64)
    capability: str
    mode: str | None = Field(default=None, max_length=64)
    prompt: str = Field(min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)
    assets: list[AssetRef] = Field(default_factory=list, max_length=8)
    originalPrompt: str | None = Field(default=None, max_length=20000)
    enhanceTemplateId: str | None = Field(default=None, max_length=64)
    promptTemplateId: str | None = Field(default=None, max_length=64)


class BulkDeleteRequest(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=100)


class UpdateTaskRequest(BaseModel):
    favorite: bool | None = None
    tags: list[str] | None = Field(default=None, max_length=50)


def _validate_enum(value: str | None, allowed: list[str], label: str) -> None:
    if value is not None and value not in allowed:
        raise HTTPException(status_code=400, detail=f"无效的{label}。")


@router.get("/api/tasks")
def list_tasks(
    request: Request,
    page: int = 1,
    pageSize: int = 20,
    status: str | None = None,
    capability: str | None = None,
    favorite: bool = False,
    tag: str | None = None,
):
    status = status or None
    capability = capability or None
    _validate_enum(status, TASK_STATUSES, "状态")
    _validate_enum(capability, CAPABILITIES, "能力")
    result = tasks_service.list_task_summaries(
        request.app.state.ctx,
        page=max(1, page),
        page_size=min(100, max(1, pageSize)),
        status=status,
        capability=capability,
        favorite_only=favorite,
        tag=tag,
        order_by="favorited_at" if favorite else "created_at",
    )
    return task_list_dict(result)


@router.post("/api/tasks", status_code=202)
async def create_task(request: Request, body: CreateTaskRequest):
    _validate_enum(body.capability, CAPABILITIES, "能力")
    try:
        task = await tasks_service.create_task(
            request.app.state.ctx,
            model_id=body.modelId,
            capability=body.capability,
            prompt=body.prompt,
            parameters=body.parameters,
            assets=[item.model_dump() for item in body.assets],
            mode=body.mode,
            original_prompt=body.originalPrompt,
            enhance_template_id=body.enhanceTemplateId,
            prompt_template_id=body.promptTemplateId,
        )
    except tasks_service.TaskError as error:
        raise HTTPException(status_code=400, detail=str(error))
    return task_dict(task)


@router.post("/api/tasks/bulk")
def bulk_delete(request: Request, body: BulkDeleteRequest):
    count = tasks_service.delete_tasks(request.app.state.ctx, body.ids)
    return {"ok": True, "count": count}


@router.get("/api/tasks/{task_id}")
def get_task(task_id: str, request: Request):
    task = tasks_service.get_task_detail(request.app.state.ctx, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task_detail_dict(task)


@router.patch("/api/tasks/{task_id}")
def update_task(task_id: str, request: Request, body: UpdateTaskRequest):
    try:
        if body.favorite is not None:
            tasks_service.set_favorite(request.app.state.ctx, task_id, body.favorite)
        if body.tags is not None:
            return task_detail_dict(
                tasks_service.set_task_tags(request.app.state.ctx, task_id, body.tags)
            )
    except tasks_service.TaskError as error:
        raise HTTPException(status_code=400, detail=str(error))
    task = tasks_service.get_task_detail(request.app.state.ctx, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task_detail_dict(task)


@router.delete("/api/tasks/{task_id}", status_code=204)
def delete_task(task_id: str, request: Request):
    tasks_service.delete_task(request.app.state.ctx, task_id)
    return None


@router.post("/api/tasks/{task_id}/retry", status_code=202)
async def retry_task(task_id: str, request: Request):
    try:
        task = await tasks_service.retry_task(request.app.state.ctx, task_id)
    except tasks_service.TaskError as error:
        raise HTTPException(status_code=400, detail=str(error))
    return task_dict(task)
