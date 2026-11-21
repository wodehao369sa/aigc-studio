"""Provider plugin contract.

A provider is a self-contained submodule under ``app/providers/<name>/`` that
exposes ``PROVIDER_DEFINITION`` and ``create_adapter`` in ``definition.py``.
The registry discovers those modules at startup, so adding or removing a
provider never touches the task, asset or API layers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from ..entities import ModelConfig


@dataclass(frozen=True)
class FieldSchema:
    key: str
    label: str
    type: str  # text | textarea | number | select
    required: bool = False
    default: str | int | float | None = None
    options: tuple[str, ...] | None = None
    min: float | None = None
    max: float | None = None
    capabilities: tuple[str, ...] | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"key": self.key, "label": self.label, "type": self.type}
        if self.required:
            data["required"] = True
        if self.default is not None:
            data["default"] = self.default
        if self.options is not None:
            data["options"] = list(self.options)
        if self.min is not None:
            data["min"] = self.min
        if self.max is not None:
            data["max"] = self.max
        if self.capabilities is not None:
            data["capabilities"] = list(self.capabilities)
        return data


@dataclass(frozen=True)
class ModelPreset:
    external_model_id: str
    name: str
    version: str | None
    description: str
    capabilities: tuple[str, ...]
    parameter_schema: tuple[FieldSchema, ...]
    input_constraints: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "externalModelId": self.external_model_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "capabilities": list(self.capabilities),
            "parameterSchema": [field.to_dict() for field in self.parameter_schema],
            "inputConstraints": self.input_constraints,
        }


@dataclass(frozen=True)
class ProviderDefinition:
    provider_id: str
    label: str
    default_base_url: str
    capabilities: tuple[str, ...]
    models: tuple[ModelPreset, ...]
    # Capabilities whose reference media must be a publicly reachable URL.
    # Others may use provider-native alternatives (e.g. Base64 data URIs).
    public_url_capabilities: tuple[str, ...] = ()
    create_adapter: Callable[["ProviderRuntime"], "ProviderAdapter"] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "providerId": self.provider_id,
            "label": self.label,
            "defaultBaseUrl": self.default_base_url,
            "capabilities": list(self.capabilities),
            "publicUrlCapabilities": list(self.public_url_capabilities),
            "models": [model.to_dict() for model in self.models],
        }


# --- runtime input -----------------------------------------------------------


@dataclass
class AssetInput:
    role: str
    asset_id: str
    storage_key: str
    mime_type: str
    public_url: str | None = None


@dataclass
class TaskInput:
    prompt: str
    parameters: dict[str, Any]
    assets: list[AssetInput]
    capability: str
    mode: str | None = None
    # Optional full chat history (system/user/assistant) for multi-turn models.
    messages: list[dict[str, str]] | None = None


@dataclass
class ProviderTaskRef:
    external_task_id: str | None = None
    external_video_id: str | None = None
    result_urls: list[str] = field(default_factory=list)
    result_text: str | None = None


@dataclass
class ProviderStatus:
    status: str  # running | succeeded | failed
    progress: int = 0
    result_urls: list[str] = field(default_factory=list)
    result_text: str | None = None
    error: str | None = None


class ProviderError(RuntimeError):
    """An upstream provider call failed."""


class ProviderTransientError(ProviderError):
    """A transient upstream failure (throttling / 5xx / temporary 4xx).

    The poller retries these for a bounded time instead of failing the task.
    """


class MediaReader(Protocol):
    def read_bytes(self, storage_key: str) -> bytes: ...


@dataclass
class ProviderRuntime:
    """Everything an adapter needs to talk to its upstream service."""

    provider_id: str
    base_url: str
    api_key: str
    timeout: float
    public_base_url: str | None
    media: MediaReader


class ProviderAdapter(ABC):
    """Upstream-specific request mapping, validation and status normalization."""

    provider_id: str

    @abstractmethod
    def validate(self, task_input: TaskInput, model: ModelConfig) -> list[str]:
        """Return a list of human-readable validation errors (empty when valid)."""

    @abstractmethod
    async def submit(self, task_input: TaskInput, model: ModelConfig, runtime: ProviderRuntime) -> ProviderTaskRef:
        """Create the upstream task.

        For synchronous providers, return the finished result in
        ``ProviderTaskRef.result_urls`` / ``result_text`` so the task service can
        persist it immediately.
        """

    @abstractmethod
    async def get_status(self, ref: ProviderTaskRef, model: ModelConfig, runtime: ProviderRuntime) -> ProviderStatus:
        """Normalize the upstream task state."""
