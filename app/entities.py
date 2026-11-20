"""Internal domain records.

These dataclasses mirror the SQLite rows and are what services return.  API
routers convert them to JSON; provider adapters consume ``ModelConfig`` and
``TaskInput`` from ``app.providers.base``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Provider:
    id: str
    provider_type: str
    name: str
    base_url: str
    enabled: bool
    max_concurrency: int


@dataclass
class ModelConfig:
    id: str
    provider_id: str
    external_model_id: str
    name: str
    version: str | None
    description: str | None
    capabilities: list[str]
    parameter_schema: list[dict[str, Any]]
    input_constraints: dict[str, Any]
    enabled: bool
    sort_order: int


@dataclass
class Asset:
    id: str
    storage_key: str
    original_filename: str
    mime_type: str
    size_bytes: int
    metadata: dict[str, Any]
    created_at: int


@dataclass
class Task:
    id: str
    provider_id: str
    model_id: str
    capability: str
    mode: str | None
    parameters: dict[str, Any]
    status: str
    progress: int
    external_task_id: str | None
    external_video_id: str | None
    error: str | None
    result_text: str | None
    created_at: int
    started_at: int | None
    completed_at: int | None
    parent_task_id: str | None
    result_asset_id: str | None
    conversation_id: str | None = None
    is_favorite: bool = False
    favorited_at: int | None = None


@dataclass
class Tag:
    id: str
    name: str
    created_at: int
    count: int = 0


@dataclass
class Conversation:
    id: str
    provider_id: str
    model_id: str
    title: str | None
    system_prompt: str | None
    created_at: int
    updated_at: int


@dataclass
class TaskAssetLink:
    role: str
    asset: Asset


@dataclass
class TaskDetail(Task):
    model_name: str = ""
    assets: list[TaskAssetLink] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


@dataclass
class TaskSummary:
    id: str
    status: str
    capability: str
    mode: str | None
    prompt: str | None
    model_name: str
    created_at: int
    completed_at: int | None
    progress: int
    error: str | None
    result_asset_id: str | None
    result_mime_type: str | None
    result_text: str | None
    is_favorite: bool
    favorited_at: int | None
    tags: list[str] = field(default_factory=list)


@dataclass
class TaskListResult:
    items: list[TaskSummary]
    page: int
    page_size: int
    total: int
