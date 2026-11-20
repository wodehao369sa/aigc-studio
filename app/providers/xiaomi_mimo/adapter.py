"""Xiaomi MiMo TTS adapter.

MiMo exposes an OpenAI-compatible chat completions endpoint that returns the
generated audio inline as Base64 in ``choices[0].message.audio.data``.
"""

from __future__ import annotations

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

PRESET_MODEL = "mimo-v2.5-tts"
VOICE_DESIGN_MODEL = "mimo-v2.5-tts-voicedesign"


class XiaomiMiMoAdapter(ProviderAdapter):
    provider_id = "xiaomi_mimo"

    def validate(self, task_input: TaskInput, model: ModelConfig) -> list[str]:
        errors: list[str] = []
        if not task_input.prompt.strip():
            errors.append("请输入需要合成的文本。")
        if (
            model.external_model_id == VOICE_DESIGN_MODEL
            and not str(task_input.parameters.get("voice_description", "")).strip()
        ):
            errors.append("音色设计模型需要填写音色与风格描述。")
        return errors

    async def submit(
        self, task_input: TaskInput, model: ModelConfig, runtime: ProviderRuntime
    ) -> ProviderTaskRef:
        voice_description = str(task_input.parameters.get("voice_description", "")).strip()
        messages: list[dict[str, str]] = []
        if model.external_model_id == VOICE_DESIGN_MODEL:
            messages.append({"role": "user", "content": voice_description})
        messages.append({"role": "assistant", "content": task_input.prompt})

        audio_format = "wav" if task_input.parameters.get("format") == "wav" else "mp3"
        audio: dict[str, str] = {"format": audio_format}
        if model.external_model_id == PRESET_MODEL:
            audio["voice"] = str(task_input.parameters.get("voice") or "mimo_default")

        url = f"{runtime.base_url}/chat/completions"
        async with httpx.AsyncClient(timeout=runtime.timeout) as client:
            response = await client.post(
                url,
                json={"model": model.external_model_id, "messages": messages, "audio": audio},
                headers={"api-key": runtime.api_key, "Content-Type": "application/json"},
            )
        if not response.is_success:
            raise ProviderError(f"Xiaomi MiMo 请求失败: {response.status_code} {response.text[:300]}")
        try:
            data = response.json()
        except ValueError as error:
            raise ProviderError("Xiaomi MiMo 返回了无效的 JSON。") from error

        choices = data.get("choices") or []
        encoded = None
        if choices:
            encoded = ((choices[0].get("message") or {}).get("audio") or {}).get("data")
        if not encoded:
            raise ProviderError("Xiaomi MiMo 未返回音频数据。")

        content_type = "audio/wav" if audio_format == "wav" else "audio/mpeg"
        return ProviderTaskRef(result_urls=[f"data:{content_type};base64,{encoded}"])

    async def get_status(
        self, ref: ProviderTaskRef, model: ModelConfig, runtime: ProviderRuntime
    ) -> ProviderStatus:
        raise ProviderError("MiMo TTS 使用同步生成，不支持异步状态查询。")
