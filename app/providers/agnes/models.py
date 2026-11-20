"""Agnes AI model presets.

These are the models this provider can configure from the settings page.  The
external model IDs and parameter schemas mirror the official Agnes API docs.
"""

from __future__ import annotations

from ..base import FieldSchema, ModelPreset

IMAGE_RATIOS = ("1:1", "3:4", "4:3", "16:9", "9:16", "2:3", "3:2", "21:9")
VIDEO_RATIOS = ("21:9", "16:9", "4:3", "1:1", "3:4", "9:16")
VIDEO_SECONDS = tuple(str(value) for value in range(4, 13))

MODEL_PRESETS: tuple[ModelPreset, ...] = (
    ModelPreset(
        external_model_id="agnes-3.0-flash",
        name="Agnes 3.0 Flash",
        version=None,
        description="Agnes 新一代文本模型，面向 Agent 编程、工具调用与复杂任务交付。",
        capabilities=("text_generation",),
        parameter_schema=(
            FieldSchema(key="system_prompt", label="系统提示词", type="textarea"),
            FieldSchema(key="max_tokens", label="最大输出 Token", type="number", default=1024, min=1, max=65536),
            FieldSchema(key="temperature", label="温度", type="number", default=0.7, min=0, max=2),
        ),
        input_constraints={"max_prompt_chars": 500000},
    ),
    ModelPreset(
        external_model_id="agnes-image-2.5-flash",
        name="Agnes Image 2.5 Flash",
        version=None,
        description="文生图、图生图与多图合成，支持 1K-4K 尺寸档位和多种宽高比。",
        capabilities=("text_to_image", "image_to_image"),
        parameter_schema=(
            FieldSchema(key="size", label="尺寸档位", type="select", default="1K", options=("1K", "2K", "3K", "4K")),
            FieldSchema(key="ratio", label="宽高比", type="select", default="1:1", options=IMAGE_RATIOS),
        ),
        input_constraints={"max_reference_images": 8},
    ),
    ModelPreset(
        external_model_id="agnes-video-2.5-flash",
        name="Agnes Video 2.5 Flash",
        version=None,
        description="文生视频、图生视频、首尾帧与图片参考视频，720P 异步生成。",
        capabilities=("text_to_video", "image_to_video", "keyframe_video", "reference_video"),
        parameter_schema=(
            FieldSchema(key="seconds", label="时长（秒）", type="select", default="5", options=VIDEO_SECONDS),
            FieldSchema(key="aspect_ratio", label="画幅", type="select", default="16:9", options=VIDEO_RATIOS),
            FieldSchema(key="seed", label="随机种子", type="number"),
        ),
        input_constraints={"max_reference_images": 5, "size": "720P"},
    ),
)
