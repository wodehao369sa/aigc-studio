"""Agnes provider registration entry point.

The registry imports this module automatically because it lives in
``app/providers/agnes/``.
"""

from __future__ import annotations

from ..base import ProviderDefinition
from .adapter import AgnesAdapter
from .models import MODEL_PRESETS

PROVIDER_DEFINITION = ProviderDefinition(
    provider_id="agnes",
    label="Agnes AI",
    default_base_url="https://apihub.agnes-ai.com/v1",
    capabilities=(
        "text_generation",
        "text_to_image",
        "image_to_image",
        "text_to_video",
        "image_to_video",
        "keyframe_video",
        "reference_video",
    ),
    models=MODEL_PRESETS,
    public_url_capabilities=(
        "text_to_video",
        "image_to_video",
        "keyframe_video",
        "reference_video",
    ),
    create_adapter=lambda runtime: AgnesAdapter(runtime),
)
