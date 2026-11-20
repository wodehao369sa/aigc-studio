"""Shared application context passed to services and routers."""

from __future__ import annotations

from dataclasses import dataclass, field

from .db import Database
from .provider_config import ProviderConfig
from .providers import ProviderRegistry
from .services.media import MediaService


@dataclass
class AppContext:
    db: Database
    media: MediaService
    registry: ProviderRegistry
    provider_configs: dict[str, ProviderConfig] = field(default_factory=dict)
    public_base_url: str = ""
