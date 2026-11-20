"""Provider registry and plugin discovery.

Provider modules live in ``app/providers/<provider_id>/`` and expose
``PROVIDER_DEFINITION`` plus ``create_adapter`` from their ``definition.py``.
Adding a directory is enough to register a provider; removing it removes the
provider from the running application after a reload.
"""

from __future__ import annotations

import importlib
import logging
from pathlib import Path

from .base import ProviderAdapter, ProviderDefinition, ProviderRuntime

logger = logging.getLogger(__name__)


class ProviderRegistry:
    def __init__(self) -> None:
        self._definitions: dict[str, ProviderDefinition] = {}

    def register(self, definition: ProviderDefinition) -> None:
        if definition.provider_id in self._definitions:
            raise ValueError(f"provider already registered: {definition.provider_id}")
        if definition.create_adapter is None:
            raise ValueError(f"provider {definition.provider_id} has no adapter factory")
        self._definitions[definition.provider_id] = definition
        logger.info("registered provider %s (%s)", definition.provider_id, definition.label)

    def get(self, provider_id: str) -> ProviderDefinition | None:
        return self._definitions.get(provider_id)

    def list(self) -> list[ProviderDefinition]:
        return [self._definitions[key] for key in sorted(self._definitions)]

    def ids(self) -> list[str]:
        return sorted(self._definitions)

    def build_adapter(self, provider_id: str, runtime: ProviderRuntime) -> ProviderAdapter:
        definition = self._definitions.get(provider_id)
        if definition is None or definition.create_adapter is None:
            raise KeyError(f"unknown provider: {provider_id}")
        return definition.create_adapter(runtime)


def discover_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    root = Path(__file__).resolve().parent
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name.startswith(("_", ".")):
            continue
        definition_module = child / "definition.py"
        if not definition_module.exists():
            continue
        module = importlib.import_module(f"{__package__}.{child.name}.definition")
        definition: ProviderDefinition = module.PROVIDER_DEFINITION
        if definition.provider_id != child.name:
            logger.warning(
                "provider directory %s declares id %s; using directory name",
                child.name,
                definition.provider_id,
            )
        registry.register(definition)
    return registry


_registry: ProviderRegistry | None = None


def get_registry() -> ProviderRegistry:
    global _registry
    if _registry is None:
        _registry = discover_registry()
    return _registry


def reload_registry() -> ProviderRegistry:
    global _registry
    _registry = discover_registry()
    return _registry
