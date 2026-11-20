"""OpenAI-compatible provider registration entry point.

The model catalog is discovered from the remote ``/v1/models`` endpoint, so this
provider ships no hard-coded presets.
"""

from __future__ import annotations

from ..base import ProviderDefinition
from .adapter import OpenAICompatibleAdapter

PROVIDER_DEFINITION = ProviderDefinition(
    provider_id="openai_compatible",
    label="OpenAI Compatible",
    default_base_url="",
    capabilities=("text_generation", "text_to_image", "image_to_image"),
    models=(),
    public_url_capabilities=(),
    create_adapter=lambda runtime: OpenAICompatibleAdapter(),
)
