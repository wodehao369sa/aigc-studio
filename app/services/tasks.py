"""Task state machine, provider dispatch, result persistence and polling.

This module owns the only place where task status transitions happen.  Pages
and API routers never mutate task state directly.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import secrets
import threading
import time
from typing import Any

import httpx

from .. import repository
from ..config import MAX_RESULT_BYTES, PROVIDER_TIMEOUT_SECONDS
from ..entities import Asset, ModelConfig, Provider, Task, TaskDetail, TaskListResult
from ..providers.base import AssetInput, ProviderRuntime, ProviderStatus, ProviderTaskRef, TaskInput
from ..provider_config import get_provider_config
from .assets import create_result_asset, delete_task_assets
from .media import extension_for_mime

logger = logging.getLogger(__name__)

REFERENCE_TOKEN_TTL_MS = 24 * 60 * 60 * 1000

# Serialize submission per task so the in-process poller can never dispatch the
# same pending task while create_task() is still submitting it (which would
# download the result twice and create duplicate media).
_DISPATCH_LOCKS: dict[str, asyncio.Lock] = {}
_DISPATCH_LOCKS_GUARD = threading.Lock()


def _dispatch_lock(task_id: str) -> asyncio.Lock:
    with _DISPATCH_LOCKS_GUARD:
        lock = _DISPATCH_LOCKS.get(task_id)
        if lock is None:
            lock = asyncio.Lock()
            _DISPATCH_LOCKS[task_id] = lock
        return lock


class TaskError(ValueError):
    pass


def _now() -> int:
    return int(time.time() * 1000)


def _safe_error(error: Exception) -> str:
    message = str(error).strip()
    return message or error.__class__.__name__


# --- reads -------------------------------------------------------------------


def list_models(
    ctx,
    capability: str | None = None,
    include_disabled: bool = False,
) -> list[ModelConfig]:
    return repository.list_models(ctx.db, ctx.registry.ids(), capability, include_disabled)


def get_model(ctx, model_id: str) -> ModelConfig | None:
    return repository.get_model(ctx.db, model_id)


def get_provider(ctx, provider_id: str) -> Provider | None:
    return repository.get_provider(ctx.db, provider_id)


def get_asset(ctx, asset_id: str) -> Asset | None:
    return repository.get_asset(ctx.db, asset_id)


def get_task(ctx, task_id: str) -> Task | None:
    return repository.get_task(ctx.db, task_id)


def get_task_detail(ctx, task_id: str) -> TaskDetail | None:
    return repository.get_task_detail(ctx.db, task_id)


def list_task_summaries(
    ctx,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    capability: str | None = None,
) -> TaskListResult:
    return repository.list_task_summaries(ctx.db, page, page_size, status, capability)


# --- provider runtime --------------------------------------------------------


def build_runtime(ctx, provider: Provider) -> ProviderRuntime:
    config = get_provider_config(ctx.provider_configs, provider.provider_type)
    return ProviderRuntime(
        provider_id=provider.provider_type,
        base_url=config.base_url,
        api_key=config.api_key,
        timeout=PROVIDER_TIMEOUT_SECONDS,
        public_base_url=ctx.public_base_url,
        media=ctx.media,
    )


def _adapter(ctx, provider: Provider, runtime: ProviderRuntime):
    return ctx.registry.build_adapter(provider.provider_type, runtime)


# --- reference tokens --------------------------------------------------------


def _reference_url(ctx, task_id: str, asset_id: str) -> str | None:
    if not ctx.public_base_url:
        return None
    now = _now()
    token = repository.get_reference_token(ctx.db, task_id, asset_id, now)
    if token is None:
        token = secrets.token_urlsafe(32)
        repository.create_reference_token(ctx.db, token, task_id, asset_id, now + REFERENCE_TOKEN_TTL_MS)
    return f"{ctx.public_base_url}/api/reference/{token}"


def _build_asset_inputs(
    ctx,
    task_id: str,
    assets: list[Asset],
    with_public_url: bool = True,
) -> list[AssetInput]:
    return [
        AssetInput(
            role=role,
            asset_id=asset.id,
            storage_key=asset.storage_key,
            mime_type=asset.mime_type,
            public_url=_reference_url(ctx, task_id, asset.id) if with_public_url else None,
        )
        for role, asset in assets
    ]


def _rebuild_input(ctx, task: Task, with_public_url: bool = True) -> TaskInput:
    paired: list[tuple[str, Asset]] = [
        (link.role, link.asset)
        for link in repository.list_task_assets(ctx.db, task.id)
        if link.role != "output"
    ]
    return TaskInput(
        prompt=str(task.parameters.get("prompt", "")),
        parameters=dict(task.parameters),
        assets=_build_asset_inputs(ctx, task.id, paired, with_public_url=with_public_url),
        capability=task.capability,
        mode=task.mode,
    )


# --- creation ----------------------------------------------------------------


async def create_task(
    ctx,
    *,
    model_id: str,
    capability: str,
    prompt: str,
    parameters: dict[str, Any] | None = None,
    assets: list[dict[str, str]] | None = None,
    mode: str | None = None,
    parent_task_id: str | None = None,
    conversation_id: str | None = None,
    messages: list[dict[str, str]] | None = None,
) -> Task:
    model = repository.get_model(ctx.db, model_id)
    if not model or not model.enabled:
        raise TaskError("模型不存在或已禁用。")
    if capability not in model.capabilities:
        raise TaskError("所选模型不支持该创作方式。")
    provider = repository.get_provider(ctx.db, model.provider_id)
    if not provider or not provider.enabled:
        raise TaskError("服务不可用。")

    asset_map: list[tuple[str, Asset]] = []
    for item in assets or []:
        asset = repository.get_asset(ctx.db, item["assetId"])
        if not asset:
            raise TaskError("参考素材不存在。")
        asset_map.append((item["role"], asset))

    definition = ctx.registry.get(provider.provider_type)
    needs_public_url = bool(
        definition and capability in definition.public_url_capabilities
    )
    if needs_public_url and asset_map and not ctx.public_base_url:
        raise TaskError("该能力需要公网可访问的参考图，请在环境变量中配置 PUBLIC_BASE_URL。")
    config = ctx.provider_configs.get(provider.provider_type)
    if config is None or not config.configured:
        raise TaskError(f"{provider.provider_type} 服务尚未在 providers.yaml 中配置 API Key。")

    merged_parameters = {**(parameters or {}), "prompt": prompt}
    if mode is not None:
        merged_parameters.setdefault("mode", mode)

    validation_input = TaskInput(
        prompt=prompt,
        parameters=merged_parameters,
        assets=[
            AssetInput(role=role, asset_id=asset.id, storage_key=asset.storage_key, mime_type=asset.mime_type)
            for role, asset in asset_map
        ],
        capability=capability,
        mode=mode,
    )
    runtime = build_runtime(ctx, provider)
    errors = _adapter(ctx, provider, runtime).validate(validation_input, model)
    if errors:
        raise TaskError(" ".join(errors))

    task = Task(
        id=repository.new_id(),
        provider_id=provider.id,
        model_id=model.id,
        capability=capability,
        mode=mode,
        parameters=merged_parameters,
        status="pending",
        progress=0,
        external_task_id=None,
        external_video_id=None,
        error=None,
        result_text=None,
        created_at=_now(),
        started_at=None,
        completed_at=None,
        parent_task_id=parent_task_id,
        result_asset_id=None,
        conversation_id=conversation_id,
    )
    repository.insert_task(ctx.db, task)
    for role, asset in asset_map:
        repository.insert_task_asset(ctx.db, task.id, asset.id, role)

    task_input = TaskInput(
        prompt=prompt,
        parameters=merged_parameters,
        assets=_build_asset_inputs(ctx, task.id, asset_map, with_public_url=needs_public_url),
        capability=capability,
        mode=mode,
        messages=messages,
    )
    await _dispatch(ctx, task, task_input, model, provider)
    return repository.get_task(ctx.db, task.id)  # type: ignore[return-value]


async def _dispatch(
    ctx,
    task: Task,
    task_input: TaskInput,
    model: ModelConfig,
    provider: Provider,
) -> None:
    async with _dispatch_lock(task.id):
        # Another path may have completed/submitted this task while we waited.
        current = repository.get_task(ctx.db, task.id)
        if current is None or current.status != "pending":
            logger.info("task %s is no longer pending, skipping dispatch", task.id)
            return
        await _dispatch_locked(ctx, task, task_input, model, provider)


async def _dispatch_locked(
    ctx,
    task: Task,
    task_input: TaskInput,
    model: ModelConfig,
    provider: Provider,
) -> None:
    """Submit a pending task, or persist a synchronous result immediately."""
    if repository.count_running(ctx.db, provider.id) >= max(1, provider.max_concurrency):
        logger.info("provider %s at capacity, task %s remains pending", provider.id, task.id)
        return

    try:
        runtime = build_runtime(ctx, provider)
        ref = await _adapter(ctx, provider, runtime).submit(task_input, model, runtime)
    except Exception as error:  # noqa: BLE001 - record any upstream failure on the task
        logger.warning("task %s submit failed: %s", task.id, error)
        repository.update_task_fields(
            ctx.db,
            task.id,
            status="failed",
            error=_safe_error(error),
            completed_at=_now(),
        )
        repository.invalidate_task_tokens(ctx.db, task.id, _now())
        return

    if ref.result_text is not None:
        repository.update_task_fields(
            ctx.db,
            task.id,
            status="succeeded",
            progress=100,
            result_text=ref.result_text,
            started_at=_now(),
            completed_at=_now(),
        )
        repository.invalidate_task_tokens(ctx.db, task.id, _now())
        return

    if ref.result_urls:
        await _complete_with_urls(ctx, task, ref.result_urls)
        return

    repository.update_task_fields(
        ctx.db,
        task.id,
        status="running",
        progress=0,
        external_task_id=ref.external_task_id,
        external_video_id=ref.external_video_id,
        started_at=_now(),
    )


# --- result persistence ------------------------------------------------------


def _decode_data_uri(url: str) -> tuple[bytes, str] | None:
    if not url.startswith("data:"):
        return None
    header, _, payload = url.partition(",")
    mime_type = header[5:].split(";", 1)[0] or "application/octet-stream"
    try:
        return base64.b64decode(payload), mime_type
    except (ValueError, base64.binascii.Error):
        return None


async def _download_result(ctx, url: str) -> tuple[bytes, str | None]:
    decoded = _decode_data_uri(url)
    if decoded is not None:
        data, mime_type = decoded
        if len(data) > MAX_RESULT_BYTES:
            raise TaskError("生成结果超过 500 MB 限制。")
        return data, mime_type

    timeout = httpx.Timeout(PROVIDER_TIMEOUT_SECONDS)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
        data = response.content
    if len(data) > MAX_RESULT_BYTES:
        raise TaskError("生成结果超过 500 MB 限制。")
    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip()
    return data, content_type or None


async def _complete_with_urls(ctx, task: Task, urls: list[str]) -> None:
    if not urls:
        raise TaskError("任务完成但未提供结果。")
    # Idempotency guard: a task may be completed only once.
    current = repository.get_task(ctx.db, task.id)
    if current is not None and current.status == "succeeded":
        logger.info("task %s already succeeded, skipping duplicate completion", task.id)
        return
    data, mime_type = await _download_result(ctx, urls[0])
    if not mime_type:
        mime_type = _fallback_mime(task.capability)
    suffix = extension_for_mime(mime_type)
    asset = create_result_asset(
        ctx.db,
        ctx.media,
        data,
        mime_type,
        f"result{suffix}",
        metadata={"source": "provider", "task_id": task.id},
    )
    repository.insert_task_asset(ctx.db, task.id, asset.id, "output")
    repository.update_task_fields(
        ctx.db,
        task.id,
        status="succeeded",
        progress=100,
        result_asset_id=asset.id,
        completed_at=_now(),
    )
    repository.invalidate_task_tokens(ctx.db, task.id, _now())


def _fallback_mime(capability: str) -> str:
    if "image" in capability:
        return "image/png"
    if "video" in capability:
        return "video/mp4"
    if "speech" in capability or "audio" in capability:
        return "audio/mpeg"
    return "text/plain"


# --- polling -----------------------------------------------------------------


async def poll_one_task(ctx) -> Task | None:
    task = repository.find_pollable_task(ctx.db)
    if task is None:
        return None
    model = repository.get_model(ctx.db, task.model_id)
    provider = repository.get_provider(ctx.db, task.provider_id)
    if not model or not provider:
        repository.update_task_fields(
            ctx.db,
            task.id,
            status="failed",
            error="任务配置不存在。",
            completed_at=_now(),
        )
        return repository.get_task(ctx.db, task.id)

    try:
        if task.status == "pending":
            definition = ctx.registry.get(provider.provider_type)
            needs_public_url = bool(
                definition and task.capability in definition.public_url_capabilities
            )
            task_input = _rebuild_input(ctx, task, with_public_url=needs_public_url)
            await _dispatch(ctx, task, task_input, model, provider)
            return repository.get_task(ctx.db, task.id)

        runtime = build_runtime(ctx, provider)
        ref = ProviderTaskRef(
            external_task_id=task.external_task_id,
            external_video_id=task.external_video_id,
        )
        status = await _adapter(ctx, provider, runtime).get_status(ref, model, runtime)
        await _apply_status(ctx, task, status)
    except Exception as error:  # noqa: BLE001 - network/upstream errors fail the task
        logger.warning("task %s poll failed: %s", task.id, error)
        repository.update_task_fields(
            ctx.db,
            task.id,
            status="failed",
            error=_safe_error(error),
            completed_at=_now(),
        )
        repository.invalidate_task_tokens(ctx.db, task.id, _now())
    return repository.get_task(ctx.db, task.id)


async def _apply_status(ctx, task: Task, status: ProviderStatus) -> None:
    if status.status == "running":
        repository.update_task_fields(ctx.db, task.id, status="running", progress=status.progress)
        return
    if status.status == "failed":
        repository.update_task_fields(
            ctx.db,
            task.id,
            status="failed",
            progress=100,
            error=status.error or "生成失败",
            completed_at=_now(),
        )
        repository.invalidate_task_tokens(ctx.db, task.id, _now())
        return
    if status.result_text is not None:
        repository.update_task_fields(
            ctx.db,
            task.id,
            status="succeeded",
            progress=100,
            result_text=status.result_text,
            completed_at=_now(),
        )
        repository.invalidate_task_tokens(ctx.db, task.id, _now())
        return
    if status.result_urls:
        await _complete_with_urls(ctx, task, status.result_urls)
        return
    raise TaskError("任务完成但未提供结果。")


# --- retry / delete ----------------------------------------------------------


async def retry_task(ctx, task_id: str) -> Task:
    task = repository.get_task(ctx.db, task_id)
    if not task or task.status != "failed":
        raise TaskError("仅失败任务可重试。")
    assets = [
        {"role": link.role, "assetId": link.asset.id}
        for link in repository.list_task_assets(ctx.db, task.id)
        if link.role != "output"
    ]
    return await create_task(
        ctx,
        model_id=task.model_id,
        capability=task.capability,
        prompt=str(task.parameters.get("prompt", "")),
        parameters={k: v for k, v in task.parameters.items() if k != "prompt"},
        assets=assets,
        mode=task.mode,
        parent_task_id=task.id,
    )


def delete_task(ctx, task_id: str) -> None:
    delete_task_assets(ctx.db, ctx.media, task_id)


def delete_tasks(ctx, task_ids: list[str]) -> int:
    for task_id in task_ids:
        delete_task(ctx, task_id)
    return len(task_ids)
