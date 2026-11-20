"""Breeze TTS adapter.

Endpoint: POST {base_url}/text-to-speech/{voice_id}?output_format=...&delivery=sync
Header:  xi-api-key: <API key>
Body:    {text, model_id?, language_code?, instructions?, voice_settings?}
Response: binary audio (content-type matches the requested format).
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

OUTPUT_FORMATS = (
    "mp3",
    "wav",
    "flac",
    "pcm",
    "aac",
    "opus",
    "mp3_24000_64",
    "mp3_24000_96",
    "mp3_24000_128",
    "mp3_24000_160",
    "wav_24000",
    "pcm_24000",
    "flac_24000",
    "aac_24000_128",
)


class BreezeAdapter(ProviderAdapter):
    provider_id = "breeze"

    def validate(self, task_input: TaskInput, model: ModelConfig) -> list[str]:
        errors: list[str] = []
        if not task_input.prompt.strip():
            errors.append("请输入需要合成的文本。")
        if not str(task_input.parameters.get("voice_id", "")).strip():
            errors.append("请填写 Breeze 音色 ID（voice_id）。")
        output_format = str(task_input.parameters.get("output_format") or "mp3")
        if output_format not in OUTPUT_FORMATS:
            errors.append("不支持的输出格式。")
        errors.extend(_number_errors(task_input.parameters, "guidance_scale", 1, 10))
        errors.extend(_number_errors(task_input.parameters, "speed", 0.5, 2))
        errors.extend(_number_errors(task_input.parameters, "volume", 0.01, 2))
        return errors

    async def submit(
        self, task_input: TaskInput, model: ModelConfig, runtime: ProviderRuntime
    ) -> ProviderTaskRef:
        voice_id = str(task_input.parameters.get("voice_id", "")).strip()
        if not voice_id:
            raise ProviderError("缺少 voice_id。")

        body: dict[str, object] = {
            "text": task_input.prompt,
            "model_id": model.external_model_id,
        }
        language_code = task_input.parameters.get("language_code")
        if language_code:
            body["language_code"] = str(language_code).strip()
        instructions = task_input.parameters.get("instructions")
        if instructions and str(instructions).strip():
            body["instructions"] = str(instructions).strip()

        settings: dict[str, float] = {}
        for key in ("guidance_scale", "speed", "volume"):
            value = task_input.parameters.get(key)
            if value in (None, ""):
                continue
            try:
                settings[key] = float(value)
            except (TypeError, ValueError):
                raise ProviderError(f"{key} 必须是数字。")
        if settings:
            body["voice_settings"] = settings

        output_format = str(task_input.parameters.get("output_format") or "mp3")
        url = f"{runtime.base_url}/text-to-speech/{voice_id}"
        async with httpx.AsyncClient(timeout=runtime.timeout) as client:
            try:
                response = await client.post(
                    url,
                    params={"output_format": output_format, "delivery": "sync"},
                    json=body,
                    headers={
                        "xi-api-key": runtime.api_key,
                        "Content-Type": "application/json",
                    },
                )
            except httpx.TransportError as error:
                raise ProviderError(f"Breeze 网络异常: {error}") from error
        if not response.is_success:
            raise ProviderError(
                f"Breeze 请求失败: {response.status_code} {response.text[:300]}"
            )
        content_type = response.headers.get("content-type", "").split(";", 1)[0].strip()
        if not content_type.startswith("audio/"):
            content_type = "audio/mpeg"
        data = response.content
        if not data:
            raise ProviderError("Breeze 未返回音频数据。")
        encoded = base64.b64encode(data).decode("ascii")
        return ProviderTaskRef(result_urls=[f"data:{content_type};base64,{encoded}"])

    async def get_status(
        self, ref: ProviderTaskRef, model: ModelConfig, runtime: ProviderRuntime
    ) -> ProviderStatus:
        raise ProviderError("Breeze TTS 使用同步生成，不支持异步状态查询。")

    async def list_voices(
        self,
        runtime: ProviderRuntime,
        *,
        search: str | None = None,
        language_code: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        params: dict[str, object] = {
            "page": max(1, page),
            "page_size": min(100, max(1, page_size)),
        }
        if search:
            params["search"] = search
        if language_code:
            params["language_code"] = language_code
        url = f"{runtime.base_url}/voices"
        async with httpx.AsyncClient(timeout=runtime.timeout) as client:
            try:
                response = await client.get(
                    url, params=params, headers={"xi-api-key": runtime.api_key}
                )
            except httpx.TransportError as error:
                raise ProviderError(f"Breeze 网络异常: {error}") from error
        if not response.is_success:
            raise ProviderError(
                f"Breeze 音色列表失败: {response.status_code} {response.text[:300]}"
            )
        data = response.json()
        voices = []
        for item in data.get("voices") or []:
            voices.append(
                {
                    "voiceId": item.get("voice_id"),
                    "name": item.get("name"),
                    "languageCode": item.get("language_code"),
                    "gender": item.get("gender"),
                    "age": item.get("age"),
                    "accent": item.get("accent"),
                    "description": item.get("description"),
                    "previewUrl": item.get("preview_url"),
                }
            )
        return {
            "voices": voices,
            "total": data.get("total", len(voices)),
            "page": data.get("page", page),
            "pageSize": data.get("page_size", page_size),
            "hasMore": bool(data.get("has_more")),
        }


def _number_errors(parameters: dict, key: str, minimum: float, maximum: float) -> list[str]:
    value = parameters.get(key)
    if value in (None, ""):
        return []
    try:
        number = float(value)
    except (TypeError, ValueError):
        return [f"{key} 必须是数字。"]
    if number < minimum or number > maximum:
        return [f"{key} 必须在 {minimum} 到 {maximum} 之间。"]
    return []
