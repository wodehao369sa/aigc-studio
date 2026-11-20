"""Convert internal entities to the public JSON shapes."""

from __future__ import annotations

from typing import Any

from .entities import Asset, Conversation, ModelConfig, Provider, Task, TaskDetail, TaskListResult, TaskSummary


def asset_dict(asset: Asset) -> dict[str, Any]:
    return {
        "id": asset.id,
        "storageKey": asset.storage_key,
        "originalFilename": asset.original_filename,
        "mimeType": asset.mime_type,
        "sizeBytes": asset.size_bytes,
        "metadata": asset.metadata,
        "createdAt": asset.created_at,
    }


def provider_dict(provider: Provider, configured: bool | None = None) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": provider.id,
        "providerType": provider.provider_type,
        "name": provider.name,
        "baseUrl": provider.base_url,
        "enabled": provider.enabled,
        "maxConcurrency": provider.max_concurrency,
    }
    if configured is not None:
        data["configured"] = configured
    return data


def model_dict(model: ModelConfig) -> dict[str, Any]:
    return {
        "id": model.id,
        "providerId": model.provider_id,
        "externalModelId": model.external_model_id,
        "name": model.name,
        "version": model.version,
        "description": model.description,
        "capabilities": model.capabilities,
        "parameterSchema": model.parameter_schema,
        "inputConstraints": model.input_constraints,
        "enabled": model.enabled,
        "sortOrder": model.sort_order,
    }


def task_dict(task: Task) -> dict[str, Any]:
    return {
        "id": task.id,
        "providerId": task.provider_id,
        "modelId": task.model_id,
        "capability": task.capability,
        "mode": task.mode,
        "parameters": task.parameters,
        "status": task.status,
        "progress": task.progress,
        "externalTaskId": task.external_task_id,
        "externalVideoId": task.external_video_id,
        "error": task.error,
        "resultText": task.result_text,
        "createdAt": task.created_at,
        "startedAt": task.started_at,
        "completedAt": task.completed_at,
        "parentTaskId": task.parent_task_id,
        "resultAssetId": task.result_asset_id,
        "conversationId": task.conversation_id,
    }


def task_detail_dict(task: TaskDetail) -> dict[str, Any]:
    data = task_dict(task)
    data["modelName"] = task.model_name
    data["assets"] = [{"role": link.role, "asset": asset_dict(link.asset)} for link in task.assets]
    return data


def task_summary_dict(summary: TaskSummary) -> dict[str, Any]:
    return {
        "id": summary.id,
        "status": summary.status,
        "capability": summary.capability,
        "mode": summary.mode,
        "prompt": summary.prompt,
        "modelName": summary.model_name,
        "createdAt": summary.created_at,
        "completedAt": summary.completed_at,
        "progress": summary.progress,
        "error": summary.error,
        "resultAssetId": summary.result_asset_id,
        "resultMimeType": summary.result_mime_type,
        "resultText": summary.result_text,
    }


def task_list_dict(result: TaskListResult) -> dict[str, Any]:
    return {
        "items": [task_summary_dict(item) for item in result.items],
        "page": result.page,
        "pageSize": result.page_size,
        "total": result.total,
    }


def conversation_dict(conversation: Conversation, model_name: str | None = None) -> dict[str, Any]:
    return {
        "id": conversation.id,
        "providerId": conversation.provider_id,
        "modelId": conversation.model_id,
        "modelName": model_name,
        "title": conversation.title,
        "systemPrompt": conversation.system_prompt,
        "createdAt": conversation.created_at,
        "updatedAt": conversation.updated_at,
    }
