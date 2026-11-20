"""Fish Audio TTS model presets."""

from __future__ import annotations

from ..base import FieldSchema, ModelPreset

FORMATS = ("mp3", "wav", "opus", "pcm")
LATENCY = ("normal", "balanced", "low")

MODEL_PRESETS: tuple[ModelPreset, ...] = (
    ModelPreset(
        external_model_id="s2.1-pro-free",
        name="Fish Audio S2.1 Pro (Free)",
        version=None,
        description="Fish Audio S2.1 Pro 免费模型，支持 83 种语言与多说话人对话合成。",
        capabilities=("text_to_speech",),
        parameter_schema=(
            FieldSchema(key="format", label="音频格式", type="select", default="mp3", options=FORMATS),
            FieldSchema(key="reference_id", label="音色 ID（可选）", type="text"),
            FieldSchema(key="seed", label="随机种子", type="number", min=0),
            FieldSchema(key="latency", label="延迟模式", type="select", default="normal", options=LATENCY),
        ),
        input_constraints={"max_text_chars": 5000},
    ),
)
