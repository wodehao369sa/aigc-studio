"""Provider credential/config loading from ``providers.yaml``.

API keys are read only on the server and never returned to the browser.  The
registry supplies display defaults; the YAML file overrides name/base URL and
provides the secret.
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
    overrides: dict[str, dict[str, Any]] = {}
    if isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, dict) and entry.get("type"):
                overrides[str(entry["type"])] = entry

    configs: dict[str, ProviderConfig] = {}
    for definition in registry.list():
        override = overrides.get(definition.provider_id, {})
        base_url = str(override.get("baseUrl") or definition.default_base_url).rstrip("/")
        name = str(override.get("name") or definition.label)
        api_key = str(override.get("apiKey") or "")
        configs[definition.provider_id] = ProviderConfig(
            provider_id=definition.provider_id,
            name=name,
            base_url=base_url,
            api_key=api_key,
        )
    return configs


def get_provider_config(configs: dict[str, ProviderConfig], provider_id: str) -> ProviderConfig:
    config = configs.get(provider_id)
    if config is None:
        raise KeyError(f"provider is not registered: {provider_id}")
    if not config.configured:
        raise RuntimeError(f"{provider_id} API Key is not configured in providers.yaml")
    return config
