"""OpenAI-compatible adapter.

Supported capabilities (all optional, depending on the upstream):
- text generation / chat:  POST {base_url}/chat/completions
- text-to-image:          POST {base_url}/images/generations
- image-to-image:         POST {base_url}/images/edits (multipart), with a
                           fallback to /images/generations using a base64 image
- model discovery:        GET  {base_url}/models
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
    TaskInput,
)

_REFERENCE_ROLES = ("source_image", "reference_image")
_IMAGE_PARAMS = ("size", "n", "quality", "response_format", "style", "background")


class OpenAICompatibleAdapter(ProviderAdapter):
    provider_id = "openai_compatible"

    def validate(self, task_input: TaskInput, model: ModelConfig) -> list[str]:
        if task_input.capability in ("text_to_image", "image_to_image"):
            if not task_input.prompt.strip():
                return ["请输入提示词。"]
            has_reference = any(asset.role in _REFERENCE_ROLES for asset in task_input.assets)
            if task_input.capability == "image_to_image" and not has_reference:
                return ["图生图需要上传参考图片。"]
            if task_input.capability == "text_to_image" and has_reference:
                return ["文生图不能携带参考图片。"]
            return []
        if not task_input.prompt.strip() and not task_input.messages:
            return ["请输入内容。"]
        return []

    async def submit(
        self, task_input: TaskInput, model: ModelConfig, runtime: ProviderRuntime
    ) -> ProviderTaskRef:
        if task_input.capability in ("text_to_image", "image_to_image"):
            return await self._submit_image(task_input, model, runtime)
        return await self._submit_text(task_input, model, runtime)

    # --- text -----------------------------------------------------------------

    async def _submit_text(
        self, task_input: TaskInput, model: ModelConfig, runtime: ProviderRuntime
    ) -> ProviderTaskRef:
        messages = task_input.messages or [{"role": "user", "content": task_input.prompt}]
        payload: dict[str, object] = {"model": model.external_model_id, "messages": messages}
        for key in ("temperature", "top_p", "max_tokens", "stream"):
            value = task_input.parameters.get(key)
            if value not in (None, ""):
                payload[key] = value

        data = await self._post_json(runtime, "chat/completions", payload)
        choices = data.get("choices") or []
        message = (choices[0].get("message") or {}) if choices else {}
        content = message.get("content")
        if not content:
            # 推理模型在 max_tokens 被思考占满时 content 可能为空，回退到 reasoning_content。
            content = message.get("reasoning_content")
        if not content:
            raise ProviderError("OpenAI 兼容接口未返回内容。")
        return ProviderTaskRef(result_text=str(content).strip())

    # --- images ---------------------------------------------------------------

    async def _submit_image(
        self, task_input: TaskInput, model: ModelConfig, runtime: ProviderRuntime
    ) -> ProviderTaskRef:
        references = [asset for asset in task_input.assets if asset.role in _REFERENCE_ROLES]
        if references:
            try:
                return await self._submit_image_edit(task_input, model, runtime, references)
            except ProviderError as error:
                message = str(error)
                if "404" not in message and "405" not in message:
                    raise
        return await self._submit_image_generate(task_input, model, runtime)

    async def _submit_image_generate(
        self, task_input: TaskInput, model: ModelConfig, runtime: ProviderRuntime
    ) -> ProviderTaskRef:
        payload: dict[str, object] = {"model": model.external_model_id, "prompt": task_input.prompt}
        for key in _IMAGE_PARAMS:
            value = task_input.parameters.get(key)
            if value not in (None, ""):
                payload[key] = value
        # Some providers accept an inline base64 image on the generations endpoint.
        references = [asset for asset in task_input.assets if asset.role in _REFERENCE_ROLES]
        if references:
            payload["image"] = self._data_uri(references[0], runtime)

        data = await self._post_json(runtime, "images/generations", payload)
        urls = self._extract_image_urls(data)
        if not urls:
            raise ProviderError("OpenAI 兼容接口未返回图片。")
        return ProviderTaskRef(result_urls=urls)

    async def _submit_image_edit(
        self,
        task_input: TaskInput,
        model: ModelConfig,
        runtime: ProviderRuntime,
        references: list,
    ) -> ProviderTaskRef:
        data: dict[str, object] = {"model": model.external_model_id, "prompt": task_input.prompt}
        for key in _IMAGE_PARAMS:
            value = task_input.parameters.get(key)
            if value not in (None, ""):
                data[key] = value
        files = []
        for index, asset in enumerate(references):
            field = "image" if len(references) == 1 else "image[]"
            files.append(
                (
                    field,
                    (
                        f"image{index}.png",
                        runtime.media.read_bytes(asset.storage_key),
                        asset.mime_type,
                    ),
                )
            )
        url = f"{runtime.base_url}/images/edits"
        async with httpx.AsyncClient(timeout=runtime.timeout) as client:
            try:
                response = await client.post(
                    url,
                    data=data,
                    files=files,
                    headers={"Authorization": f"Bearer {runtime.api_key}"},
                )
            except httpx.TransportError as error:
                raise ProviderError(f"OpenAI 兼容接口网络异常: {error}") from error
        if response.status_code in (404, 405):
            raise ProviderError(f"图片编辑接口不可用: {response.status_code}")
        if not response.is_success:
            raise ProviderError(
                f"OpenAI 兼容接口请求失败: {response.status_code} {response.text[:300]}"
            )
        urls = self._extract_image_urls(response.json())
        if not urls:
            raise ProviderError("OpenAI 兼容接口未返回图片。")
        return ProviderTaskRef(result_urls=urls)

    # --- helpers --------------------------------------------------------------

    async def _post_json(self, runtime: ProviderRuntime, path: str, payload: dict) -> dict:
        url = f"{runtime.base_url}/{path}"
        async with httpx.AsyncClient(timeout=runtime.timeout) as client:
            try:
                response = await client.post(
                    url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {runtime.api_key}",
                        "Content-Type": "application/json",
                    },
                )
            except httpx.TransportError as error:
                raise ProviderError(f"OpenAI 兼容接口网络异常: {error}") from error
        if not response.is_success:
            raise ProviderError(
                f"OpenAI 兼容接口请求失败: {response.status_code} {response.text[:300]}"
            )
        data = response.json()
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _extract_image_urls(data: dict) -> list[str]:
        urls: list[str] = []
        for item in data.get("data") or []:
            if not isinstance(item, dict):
                continue
            if item.get("url"):
                urls.append(str(item["url"]))
            elif item.get("b64_json"):
                urls.append(f"data:image/png;base64,{item['b64_json']}")
        return urls

    @staticmethod
    def _data_uri(asset, runtime: ProviderRuntime) -> str:
        data = runtime.media.read_bytes(asset.storage_key)
        return f"data:{asset.mime_type};base64,{base64.b64encode(data).decode('ascii')}"

    async def get_status(
        self, ref: ProviderTaskRef, model: ModelConfig, runtime: ProviderRuntime
    ) -> ProviderStatus:
        raise ProviderError("OpenAI 兼容接口为同步生成，不支持异步状态查询。")

    async def list_remote_models(self, runtime: ProviderRuntime) -> list[str]:
        url = f"{runtime.base_url}/models"
        async with httpx.AsyncClient(timeout=runtime.timeout) as client:
            try:
                response = await client.get(
                    url, headers={"Authorization": f"Bearer {runtime.api_key}"}
                )
            except httpx.TransportError as error:
                raise ProviderError(f"OpenAI 兼容接口网络异常: {error}") from error
        if not response.is_success:
            raise ProviderError(f"获取模型列表失败: {response.status_code} {response.text[:300]}")
        data = response.json()
        return [
            str(item["id"])
            for item in data.get("data", [])
            if isinstance(item, dict) and item.get("id")
        ]
