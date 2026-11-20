"""Capability taxonomy shared by API validation and the UI."""

from __future__ import annotations

CAPABILITIES = [
    "text_generation",
    "text_to_image",
    "image_to_image",
    "text_to_video",
    "image_to_video",
    "keyframe_video",
    "reference_video",
]

CAPABILITY_LABELS = {
    "text_generation": "文本生成",
    "text_to_image": "文生图",
    "image_to_image": "图生图",
    "text_to_video": "文生视频",
    "image_to_video": "图生视频",
    "keyframe_video": "首尾帧视频",
    "reference_video": "图片参考视频",
}

# Ordered groups used by the create page workspace switch.
WORKSPACES = [
    {"label": "文本", "modes": ["text_generation"]},
    {"label": "图片", "modes": ["text_to_image", "image_to_image"]},
    {"label": "视频", "modes": ["text_to_video", "image_to_video", "keyframe_video", "reference_video"]},
]

TASK_STATUSES = ["pending", "running", "succeeded", "failed"]
