"""Server-rendered pages."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.templating import Jinja2Templates

from .. import repository
from ..catalog import CAPABILITIES, CAPABILITY_LABELS, TASK_STATUSES, WORKSPACES
from ..config import BASE_DIR, MEDIA_LIMIT_BYTES, MEDIA_WARN_BYTES
from ..serializers import conversation_dict, model_dict, tag_dict, task_detail_dict
from ..services import conversations as conversations_service
from ..services import settings as settings_service
from ..services import tasks as tasks_service

router = APIRouter()
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def _format_ms(value: int | None) -> str:
    if not value:
        return ""
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")


templates.env.filters["datetime"] = _format_ms
templates.env.filters["caplabel"] = lambda value: CAPABILITY_LABELS.get(value, value)


def _json_pretty(value) -> str:
    """Human-readable JSON for display, keeping the original text (not \\uXXXX)."""
    return json.dumps(value, ensure_ascii=False, indent=2)


templates.env.filters["json_pretty"] = _json_pretty


@router.get("/")
def home(request: Request):
    ctx = request.app.state.ctx
    models = tasks_service.list_models(ctx)
    usage = ctx.media.usage()
    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "models": [model_dict(model) for model in models],
            "usage": usage,
            "warn_bytes": MEDIA_WARN_BYTES,
            "limit_bytes": MEDIA_LIMIT_BYTES,
            "capability_labels": CAPABILITY_LABELS,
            "workspaces": WORKSPACES,
        },
    )


@router.get("/tasks")
def tasks_page(
    request: Request,
    page: int = 1,
    status: str | None = None,
    capability: str | None = None,
):
    status = status or None
    capability = capability or None
    if status is not None and status not in TASK_STATUSES:
        raise HTTPException(status_code=400, detail="无效的状态。")
    if capability is not None and capability not in CAPABILITIES:
        raise HTTPException(status_code=400, detail="无效的能力。")
    result = tasks_service.list_task_summaries(
        request.app.state.ctx,
        page=max(1, page),
        page_size=20,
        status=status,
        capability=capability,
    )
    query = ""
    if status:
        query += f"&status={status}"
    if capability:
        query += f"&capability={capability}"
    total_pages = max(1, math.ceil(result.total / result.page_size))
    return templates.TemplateResponse(
        request,
        "tasks.html",
        {
            "result": result,
            "status": status,
            "capability": capability,
            "capabilities": CAPABILITIES,
            "capability_labels": CAPABILITY_LABELS,
            "statuses": TASK_STATUSES,
            "prev_url": f"/tasks?page={result.page - 1}{query}" if result.page > 1 else None,
            "next_url": f"/tasks?page={result.page + 1}{query}" if result.page < total_pages else None,
            "total_pages": total_pages,
        },
    )


@router.get("/tasks/{task_id}")
def task_detail_page(task_id: str, request: Request):
    task = tasks_service.get_task_detail(request.app.state.ctx, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return templates.TemplateResponse(
        request,
        "task_detail.html",
        {"task": task_detail_dict(task), "capability_labels": CAPABILITY_LABELS},
    )


@router.get("/settings")
def settings_page(request: Request):
    ctx = request.app.state.ctx
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "providers": settings_service.list_providers(ctx),
            "models": [model_dict(model) for model in settings_service.list_models(ctx, include_disabled=True)],
            "presets": settings_service.list_presets(ctx),
            "capability_labels": CAPABILITY_LABELS,
            "capabilities": CAPABILITIES,
        },
    )


@router.get("/conversations")
def conversations_page(request: Request):
    ctx = request.app.state.ctx
    models = {
        model.id: model.name
        for model in tasks_service.list_models(ctx)
        if "text_generation" in model.capabilities
    }
    conversations = [
        conversation_dict(conversation, models.get(conversation.model_id))
        for conversation in conversations_service.list_conversations(ctx)
    ]
    return templates.TemplateResponse(
        request,
        "conversations.html",
        {
            "conversations": conversations,
            "models": [model_dict(model) for model in tasks_service.list_models(ctx) if "text_generation" in model.capabilities],
        },
    )


@router.get("/conversations/{conversation_id}")
def chat_page(conversation_id: str, request: Request):
    ctx = request.app.state.ctx
    conversation = conversations_service.get_conversation(ctx, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="对话不存在")
    model = repository.get_model(ctx.db, conversation.model_id)
    models = {
        item.id: item.name
        for item in tasks_service.list_models(ctx)
        if "text_generation" in item.capabilities
    }
    conversations = [
        conversation_dict(item, models.get(item.model_id))
        for item in conversations_service.list_conversations(ctx)
    ]
    return templates.TemplateResponse(
        request,
        "chat.html",
        {
            "conversation": conversation_dict(conversation, model.name if model else None),
            "conversations": conversations,
            "messages": conversations_service.get_messages(ctx, conversation_id),
        },
    )


@router.get("/gallery")
def gallery_page(request: Request, page: int = 1, tag: str | None = None):
    ctx = request.app.state.ctx
    result = tasks_service.list_task_summaries(
        ctx,
        page=max(1, page),
        page_size=24,
        favorite_only=True,
        tag=tag,
        order_by="favorited_at",
    )
    total_pages = max(1, math.ceil(result.total / result.page_size))
    tag_counts = repository.count_tags_in_favorites(ctx.db)
    tags = [
        {**tag_dict(item), "count": tag_counts.get(item.name, 0)}
        for item in tasks_service.list_tags(ctx)
        if tag_counts.get(item.name, 0) > 0
    ]
    return templates.TemplateResponse(
        request,
        "gallery.html",
        {
            "result": result,
            "tags": tags,
            "total_favorites": repository.count_favorite_results(ctx.db),
            "active_tag": tag,
            "capability_labels": CAPABILITY_LABELS,
            "prev_url": (
                f"/gallery?page={result.page - 1}{f'&tag={tag}' if tag else ''}"
                if result.page > 1
                else None
            ),
            "next_url": (
                f"/gallery?page={result.page + 1}{f'&tag={tag}' if tag else ''}"
                if result.page < total_pages
                else None
            ),
            "total_pages": total_pages,
        },
    )
