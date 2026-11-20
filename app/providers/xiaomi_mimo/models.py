"""Xiaomi MiMo TTS model presets."""

from __future__ import annotations

from ..base import FieldSchema, ModelPreset

VOICES = ("mimo_default", "冰糖", "茉莉", "苏打", "白桦", "Mia", "Chloe", "Milo", "Dean")
FORMATS = ("mp3", "wav")

MODEL_PRESETS: tuple[ModelPreset, ...] = (
    ModelPreset(
        external_model_id="mimo-v2.5-tts",
        name="MiMo TTS · 预置音色",
        version=None,
        description="MiMo-V2.5 预置音色语音合成。",
        capabilities=("text_to_speech",),
        parameter_schema=(
            FieldSchema(key="voice", label="音色", type="select", default="mimo_default", options=VOICES),
            FieldSchema(key="format", label="音频格式", type="select", default="mp3", options=FORMATS),
        ),
        input_constraints={"max_text_chars": 5000},
    ),
    ModelPreset(
        external_model_id="mimo-v2.5-tts-voicedesign",
        name="MiMo TTS · 音色设计",
        version=None,
        description="通过文字描述设计音色，请在「音色与风格描述」中填写声音特征和说话风格。",
        capabilities=("text_to_speech",),
        parameter_schema=(
            FieldSchema(key="voice_description", label="音色与风格描述", type="textarea", required=True),
            FieldSchema(key="format", label="音频格式", type="select", default="mp3", options=FORMATS),
        ),
        input_constraints={"max_text_chars": 5000},
    ),
)
