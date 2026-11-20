"""ModelScope provider registration entry point."""

from __future__ import annotations

from ..base import ProviderDefinition
from .adapter import ModelScopeAdapter
from .models import MODEL_PRESETS

PROVIDER_DEFINITION = ProviderDefinition(
    provider_id="modelscope",
    label="ModelScope",
    default_base_url="https://api-inference.modelscope.cn",
    capabilities=("text_to_image", "image_to_image"),
    models=MODEL_PRESETS,
    public_url_capabilities=(),
    create_adapter=lambda runtime: ModelScopeAdapter(),
)
