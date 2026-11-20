"""Fish Audio provider registration entry point."""

from __future__ import annotations

from ..base import ProviderDefinition
from .adapter import FishAudioAdapter
from .models import MODEL_PRESETS

PROVIDER_DEFINITION = ProviderDefinition(
    provider_id="fish_audio",
    label="Fish Audio",
    default_base_url="https://api.fish.audio/v1",
    capabilities=("text_to_speech",),
    models=MODEL_PRESETS,
    public_url_capabilities=(),
    create_adapter=lambda runtime: FishAudioAdapter(),
)
