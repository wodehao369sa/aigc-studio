"""ModelScope API-Inference adapter.

Async AIGC API:
- submit:  POST {base_url}/v1/images/generations  (X-ModelScope-Async-Mode: true)
- status:  GET  {base_url}/v1/tasks/{task_id}     (X-ModelScope-Task-Type: image_generation)
"""

from __future__ import annotations

import base64

import httpx

from ...entities import ModelConfig
from ..base import (
    ProviderAdapter,
    ProviderError,
    ProviderRuntime,
    ProviderStatus,
    ProviderTaskRef,
    ProviderTransientError,
    TaskInput,
)

_REFERENCE_ROLES = ("source_image", "reference_image")


class ModelScopeAdapter(ProviderAdapter):
    provider_id = "modelscope"

    def validate(self, task_input: TaskInput, model: ModelConfig) -> list[str]:
        errors: list[str] = []
        if not task_input.prompt.strip():
            errors.append("请输入提示词。")
        has_reference = any(asset.role in _REFERENCE_ROLES for asset in task_input.assets)
        if task_input.capability == "image_to_image" and not has_reference:
            errors.append("图生图需要上传源图片。")
        if task_input.capability == "text_to_image" and has_reference:
            errors.append("文生图不能携带参考图片。")
        return errors

    async def submit(
        self, task_input: TaskInput, model: ModelConfig, runtime: ProviderRuntime
    ) -> ProviderTaskRef:
        payload: dict = {"model": model.external_model_id, "prompt": task_input.prompt}
        for key in ("negative_prompt", "size"):
            value = task_input.parameters.get(key)
            if value not in (None, ""):
                payload[key] = str(value)
        for key in ("seed", "steps"):
            value = task_input.parameters.get(key)
            if value not in (None, ""):
                try:
                    payload[key] = int(value)
                except (TypeError, ValueError):
                    raise ProviderError(f"{key} 必须是整数。")
        guidance = task_input.parameters.get("guidance")
        if guidance not in (None, ""):
            try:
                payload["guidance"] = float(guidance)
            except (TypeError, ValueError):
                raise ProviderError("guidance 必须是数字。")

        references = [asset for asset in task_input.assets if asset.role in _REFERENCE_ROLES]
        if references:
            payload["image_url"] = [self._data_uri(asset, runtime) for asset in references]

        url = f"{runtime.base_url}/v1/images/generations"
        async with httpx.AsyncClient(timeout=runtime.timeout) as client:
            response = await client.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {runtime.api_key}",
                    "Content-Type": "application/json",
                    "X-ModelScope-Async-Mode": "true",
                },
            )
        if not response.is_success:
            raise ProviderError(f"ModelScope 创建失败: {response.status_code} {response.text[:300]}")
        data = response.json()
        task_id = data.get("task_id")
        if not task_id:
            raise ProviderError("ModelScope 未返回 task_id。")
        return ProviderTaskRef(external_task_id=str(task_id))

    async def get_status(
        self, ref: ProviderTaskRef, model: ModelConfig, runtime: ProviderRuntime
    ) -> ProviderStatus:
        if not ref.external_task_id:
            raise ProviderError("ModelScope 任务缺少 task_id。")
        url = f"{runtime.base_url}/v1/tasks/{ref.external_task_id}"
        async with httpx.AsyncClient(timeout=runtime.timeout) as client:
            try:
                response = await client.get(
                    url,
                    headers={
                        "Authorization": f"Bearer {runtime.api_key}",
                        "X-ModelScope-Task-Type": "image_generation",
                    },
                )
            except httpx.TransportError as error:
                raise ProviderTransientError(f"ModelScope 查询网络异常: {error}") from error
        if not response.is_success:
            # ModelScope reports task-level failures (e.g. content moderation) as
            # HTTP 400 with a JSON body that still contains task_status.  Parse it
            # before deciding whether the error is transient.
            data = self._safe_json(response)
            if isinstance(data, dict) and data.get("task_status"):
                return self._map_status(data)
            if response.status_code in (400, 404, 408, 425, 429) or response.status_code >= 500:
                # Intermittent 4xx/5xx while a task is scheduled or torn down.
                raise ProviderTransientError(
                    f"ModelScope 查询暂时失败: {response.status_code} {response.text[:200]}"
                )
            raise ProviderError(f"ModelScope 查询失败: {response.status_code}")
        data = response.json()
        return self._map_status(data)

    @staticmethod
    def _safe_json(response) -> dict | None:
        try:
            data = response.json()
        except ValueError:
            return None
        return data if isinstance(data, dict) else None

    @staticmethod
    def _map_status(data: dict) -> ProviderStatus:
        task_status = str(data.get("task_status", "")).upper()
        if task_status == "SUCCEED":
            return ProviderStatus(
                status="succeeded", progress=100, result_urls=data.get("output_images") or []
            )
        if task_status == "FAILED":
            message = data.get("message") or data.get("errors") or "ModelScope 图片生成失败。"
            if isinstance(message, dict):
                message = message.get("message") or str(message)
            return ProviderStatus(status="failed", progress=100, error=str(message))
        return ProviderStatus(status="running", progress=0)

    def _data_uri(self, asset, runtime: ProviderRuntime) -> str:
        data = runtime.media.read_bytes(asset.storage_key)
        return f"data:{asset.mime_type};base64,{base64.b64encode(data).decode('ascii')}"
