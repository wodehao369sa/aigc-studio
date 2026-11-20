"""Fish Audio TTS adapter.

Endpoint: POST {base_url}/tts
Headers: Authorization: Bearer <key>, Content-Type: application/json, model: <id>
Body: {text, format?, reference_id?, seed?, latency?}
Response: audio bytes (content-type carries the format).
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

FORMATS = ("mp3", "wav", "opus", "pcm", "flac", "aac")
LATENCY_MODES = ("normal", "balanced", "low")


class FishAudioAdapter(ProviderAdapter):
    provider_id = "fish_audio"

    def validate(self, task_input: TaskInput, model: ModelConfig) -> list[str]:
        if not task_input.prompt.strip():
            return ["请输入需要合成的文本。"]
        return []

    async def submit(
        self, task_input: TaskInput, model: ModelConfig, runtime: ProviderRuntime
    ) -> ProviderTaskRef:
        body: dict[str, object] = {"text": task_input.prompt}
        audio_format = task_input.parameters.get("format")
        if audio_format in FORMATS:
            body["format"] = audio_format
        reference_id = task_input.parameters.get("reference_id")
        if reference_id:
            body["reference_id"] = str(reference_id).strip()
        seed = task_input.parameters.get("seed")
        if seed not in (None, ""):
            try:
                body["seed"] = int(seed)
            except (TypeError, ValueError):
                raise ProviderError("seed 必须是整数。")
        latency = task_input.parameters.get("latency")
        if latency in LATENCY_MODES:
            body["latency"] = latency

        url = f"{runtime.base_url}/tts"
        async with httpx.AsyncClient(timeout=runtime.timeout) as client:
            try:
                response = await client.post(
                    url,
                    json=body,
                    headers={
                        "Authorization": f"Bearer {runtime.api_key}",
                        "Content-Type": "application/json",
                        "model": model.external_model_id,
                    },
                )
            except httpx.TransportError as error:
                raise ProviderError(f"Fish Audio 网络异常: {error}") from error
        if not response.is_success:
            raise ProviderError(
                f"Fish Audio 请求失败: {response.status_code} {response.text[:300]}"
            )
        content_type = response.headers.get("content-type", "").split(";", 1)[0].strip()
        if not content_type.startswith("audio/"):
            content_type = "audio/mpeg"
        data = response.content
        if not data:
            raise ProviderError("Fish Audio 未返回音频数据。")
        encoded = base64.b64encode(data).decode("ascii")
        return ProviderTaskRef(result_urls=[f"data:{content_type};base64,{encoded}"])

    async def get_status(
        self, ref: ProviderTaskRef, model: ModelConfig, runtime: ProviderRuntime
    ) -> ProviderStatus:
        raise ProviderError("Fish Audio TTS 使用同步生成，不支持异步状态查询。")
