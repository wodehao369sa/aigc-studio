"""ModelScope API-Inference model presets.

All models use the async AIGC interface:
POST /v1/images/generations (X-ModelScope-Async-Mode: true) then poll /v1/tasks/{id}.
"""

from __future__ import annotations

from ..base import FieldSchema, ModelPreset

SIZES = ("512x512", "768x768", "1024x1024", "1024x768", "768x1024", "1280x720", "720x1280")

_TEXT_PARAMS = (
    FieldSchema(key="negative_prompt", label="负向提示词", type="textarea"),
    FieldSchema(key="size", label="尺寸", type="select", default="1024x1024", options=SIZES),
    FieldSchema(key="seed", label="随机种子", type="number", min=0, max=2147483647),
    FieldSchema(key="steps", label="采样步数", type="number", default=30, min=1, max=100),
    FieldSchema(key="guidance", label="引导系数", type="number", default=3.5, min=1.5, max=20),
)

MODEL_PRESETS: tuple[ModelPreset, ...] = (
    ModelPreset(
        external_model_id="Qwen/Qwen-Image-2.1-Turbo",
        name="Qwen Image 2.1 Turbo",
        version=None,
        description="通义千问 Qwen-Image 2.1 加速版：文生图与图像编辑，8 步快速出图。",
        capabilities=("text_to_image", "image_to_image"),
        parameter_schema=_TEXT_PARAMS,
        input_constraints={"max_reference_images": 10},
    ),
    ModelPreset(
        external_model_id="openmoss/MOSS-Image-SFT",
        name="MOSS Image SFT",
        version=None,
        description="OpenMOSS MOSS-Image 监督微调模型：文本渲染、布局生成与长提示词文生图。",
        capabilities=("text_to_image",),
        parameter_schema=_TEXT_PARAMS,
        input_constraints={},
    ),
    ModelPreset(
        external_model_id="Qwen/Qwen-Image-2.1",
        name="Qwen Image 2.1",
        version=None,
        description="通义千问 Qwen-Image 2.1：统一文生图与图像编辑，支持 RGBA 透明通道。",
        capabilities=("text_to_image", "image_to_image"),
        parameter_schema=_TEXT_PARAMS,
        input_constraints={"max_reference_images": 10},
    ),
    ModelPreset(
        external_model_id="Tongyi-MAI/Z-Image-Turbo",
        name="Z-Image Turbo",
        version=None,
        description="通义 Z-Image Turbo：6B 蒸馏模型，擅长风格多样性、负向提示与构图。",
        capabilities=("text_to_image",),
        parameter_schema=_TEXT_PARAMS,
        input_constraints={},
    ),
)
