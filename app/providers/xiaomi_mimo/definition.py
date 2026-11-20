"""Xiaomi MiMo provider registration entry point."""

from __future__ import annotations

from ..base import ProviderDefinition
from .adapter import XiaomiMiMoAdapter
from .models import MODEL_PRESETS

PROVIDER_DEFINITION = ProviderDefinition(
    provider_id="xiaomi_mimo",
    label="Xiaomi MiMo",
    default_base_url="https://api.xiaomimimo.com/v1",
    capabilities=("text_to_speech",),
    models=MODEL_PRESETS,
    public_url_capabilities=(),
    create_adapter=lambda runtime: XiaomiMiMoAdapter(),
)
