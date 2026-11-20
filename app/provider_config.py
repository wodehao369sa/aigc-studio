"""Provider credential/config loading from ``providers.yaml``.

API keys are read only on the server and never returned to the browser.  The
registry supplies display defaults; the YAML file overrides name/base URL and
provides the secret.

Each entry may carry an ``id`` so a single provider type (e.g.
``openai_compatible``) can be configured as several independent sites.  Without
``id`` the provider type itself is used as the instance id.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import yaml

from .config import PROVIDERS_CONFIG_PATH
from .providers import ProviderRegistry

logger = logging.getLogger(__name__)


@dataclass
class ProviderConfig:
    provider_id: str
    provider_type: str
    name: str
    base_url: str
    api_key: str

    @property
    def configured(self) -> bool:
        return bool(self.api_key) and not self.api_key.startswith("REPLACE_WITH")


def _read_yaml(path) -> dict[str, Any]:
    try:
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, yaml.YAMLError) as error:
        logger.warning("unable to read provider config %s: %s", path, error)
        return {}


def load_provider_configs(registry: ProviderRegistry) -> dict[str, ProviderConfig]:
    raw = _read_yaml(PROVIDERS_CONFIG_PATH)
    entries = raw.get("providers") or []
    configs: dict[str, ProviderConfig] = {}
    covered_types: set[str] = set()

    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, dict) or not entry.get("type"):
                continue
            provider_type = str(entry["type"])
            definition = registry.get(provider_type)
            if definition is None:
                continue
            provider_id = str(entry.get("id") or provider_type)
            base_url = str(entry.get("baseUrl") or definition.default_base_url).rstrip("/")
            configs[provider_id] = ProviderConfig(
                provider_id=provider_id,
                provider_type=provider_type,
                name=str(entry.get("name") or definition.label),
                base_url=base_url,
                api_key=str(entry.get("apiKey") or ""),
            )
            covered_types.add(provider_type)

    # Registered providers missing from the YAML still get a default row.
    for definition in registry.list():
        if definition.provider_id in covered_types:
            continue
        configs[definition.provider_id] = ProviderConfig(
            provider_id=definition.provider_id,
            provider_type=definition.provider_id,
            name=definition.label,
            base_url=definition.default_base_url,
            api_key="",
        )
    return configs


def get_provider_config(configs: dict[str, ProviderConfig], provider_id: str) -> ProviderConfig:
    config = configs.get(provider_id)
    if config is None:
        raise KeyError(f"provider is not registered: {provider_id}")
    if not config.configured:
        raise RuntimeError(f"{provider_id} API Key is not configured in providers.yaml")
    return config
