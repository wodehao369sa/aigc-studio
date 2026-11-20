"""Breeze provider registration entry point."""

from __future__ import annotations

from ..base import ProviderDefinition
from .adapter import BreezeAdapter
from .models import MODEL_PRESETS

PROVIDER_DEFINITION = ProviderDefinition(
    provider_id="breeze",
    label="Breeze",
    default_base_url="https://api.breeze.blue/v1",
    capabilities=("text_to_speech",),
    models=MODEL_PRESETS,
    public_url_capabilities=(),
    create_adapter=lambda runtime: BreezeAdapter(),
)
