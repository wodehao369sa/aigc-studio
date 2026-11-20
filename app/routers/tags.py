"""Tag API."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..serializers import tag_dict
from ..services import tasks as tasks_service

router = APIRouter()


@router.get("/api/tags")
def list_tags(request: Request):
    return [tag_dict(tag) for tag in tasks_service.list_tags(request.app.state.ctx)]
