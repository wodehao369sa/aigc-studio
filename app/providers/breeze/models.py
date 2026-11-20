"""Breeze TTS model presets.

The API is POST /v1/text-to-speech/{voice_id}; the voice is chosen per request,
so ``voice_id`` is exposed as a required parameter.
"""

from __future__ import annotations

from ..base import FieldSchema, ModelPreset

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


def _schema() -> tuple[FieldSchema, ...]:
    return (
        FieldSchema(key="voice_id", label="音色 ID（voice_id）", type="text", required=True),
        FieldSchema(key="language_code", label="语言代码（可选，如 en / zh）", type="text"),
        FieldSchema(key="instructions", label="表演指令（可选）", type="textarea"),
        FieldSchema(
            key="output_format", label="输出格式", type="select", default="mp3", options=OUTPUT_FORMATS
        ),
        FieldSchema(key="guidance_scale", label="引导强度", type="number", default=1, min=1, max=10),
        FieldSchema(key="speed", label="语速", type="number", default=1, min=0.5, max=2),
        FieldSchema(key="volume", label="音量", type="number", default=1, min=0.01, max=2),
    )


MODEL_PRESETS: tuple[ModelPreset, ...] = (
    ModelPreset(
        external_model_id="breeze-tts-2",
        name="Breeze TTS 2",
        version=None,
        description="Breeze TTS 2：支持中文/英文的语音合成，可附带表演指令与声音设置。",
        capabilities=("text_to_speech",),
        parameter_schema=_schema(),
        input_constraints={"max_text_chars": 2000},
    ),
    ModelPreset(
        external_model_id="breeze-tts-2-multilingual",
        name="Breeze TTS 2 Multilingual",
        version=None,
        description="Breeze TTS 2 多语言版：覆盖 51 种语言与 34 种音频动作标签。",
        capabilities=("text_to_speech",),
        parameter_schema=_schema(),
        input_constraints={"max_text_chars": 2000},
    ),
)
