"""Provider connections and model catalog management."""

from __future__ import annotations

import re
from typing import Any

from .. import repository
from ..entities import ModelConfig, Provider
from ..providers.base import ModelPreset

FIELD_KEY_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{0,63}$")
RESERVED_FIELD_KEYS = {"prompt", "model", "input", "mode", "constructor"}
FIELD_TYPES = {"text", "textarea", "number", "select"}


class SettingsError(ValueError):
    pass


# --- providers ---------------------------------------------------------------


def list_providers(ctx) -> list[dict[str, Any]]:
    registered = set(ctx.registry.ids())
    result: list[dict[str, Any]] = []
    for provider in repository.list_providers(ctx.db):
        if provider.provider_type not in registered:
            continue
        config = ctx.provider_configs.get(provider.id)
        result.append(
            {
                "id": provider.id,
                "providerType": provider.provider_type,
                "name": provider.name,
                "baseUrl": provider.base_url,
                "enabled": provider.enabled,
                "maxConcurrency": provider.max_concurrency,
                "configured": bool(config and config.configured),
            }
        )
    return result


def update_provider(ctx, provider_id: str, enabled: bool, max_concurrency: int) -> None:
    if not repository.get_provider(ctx.db, provider_id):
        raise SettingsError("服务不存在。")
    if max_concurrency < 1 or max_concurrency > 16:
        raise SettingsError("最大并发必须在 1 到 16 之间。")
    repository.update_provider(ctx.db, provider_id, enabled, max_concurrency)


def reload_providers(ctx) -> list[dict[str, Any]]:
    """Re-scan provider modules and refresh credentials.

    This is what makes providers hot-pluggable: drop a module directory into
    ``app/providers`` and call this endpoint, no core code changes required.
    """
    from ..provider_config import load_provider_configs
    from ..providers import reload_registry

    ctx.registry = reload_registry()
    ctx.provider_configs = load_provider_configs(ctx.registry)
    sync_provider_rows(ctx)
    return list_providers(ctx)


def sync_provider_rows(ctx) -> None:
    """Create/update ``providers`` rows for every registered provider."""
    from ..provider_config import load_provider_configs

    ctx.provider_configs = load_provider_configs(ctx.registry)
    registered = list(ctx.provider_configs.keys())
    for provider_id in registered:
        config = ctx.provider_configs[provider_id]
        definition = ctx.registry.get(config.provider_type)
        repository.upsert_provider(
            ctx.db,
            provider_id=provider_id,
            provider_type=config.provider_type,
            name=config.name or (definition.label if definition else provider_id),
            base_url=config.base_url or (definition.default_base_url if definition else ""),
            enabled=True,
            max_concurrency=1,
        )
    repository.delete_providers_except(ctx.db, registered)


def list_presets(ctx) -> list[dict[str, Any]]:
    return [definition.to_dict() for definition in ctx.registry.list()]


# --- models ------------------------------------------------------------------


def _validate_parameter_schema(schema: Any) -> list[dict[str, Any]]:
    if not isinstance(schema, list):
        raise SettingsError("参数定义必须是数组。")
    if len(schema) > 32:
        raise SettingsError("参数定义最多 32 项。")
    seen: set[str] = set()
    cleaned: list[dict[str, Any]] = []
    for item in schema:
        if not isinstance(item, dict):
            raise SettingsError("参数定义每一项必须是对象。")
        key = str(item.get("key", "")).strip()
        label = str(item.get("label", "")).strip()
        field_type = str(item.get("type", "")).strip()
        if not FIELD_KEY_PATTERN.match(key) or key in RESERVED_FIELD_KEYS:
            raise SettingsError(f"参数 key 非法：{key}")
        if key in seen:
            raise SettingsError(f"参数 key 重复：{key}")
        seen.add(key)
        if not label or len(label) > 80:
            raise SettingsError(f"参数标签非法：{key}")
        if field_type not in FIELD_TYPES:
            raise SettingsError(f"参数类型非法：{key}")
        field: dict[str, Any] = {"key": key, "label": label, "type": field_type}
        if item.get("required"):
            field["required"] = True
        if item.get("default") is not None:
            field["default"] = item["default"]
        if field_type == "select":
            options = item.get("options")
            if not isinstance(options, list) or not options or len(options) > 50:
                raise SettingsError(f"select 参数必须提供 1-50 个选项：{key}")
            field["options"] = [str(option) for option in options]
        if item.get("min") is not None:
            field["min"] = item["min"]
        if item.get("max") is not None:
            field["max"] = item["max"]
        cleaned.append(field)
    return cleaned


def _resolve_preset(ctx, provider: Provider, preset_id: str | None) -> ModelPreset | None:
    if not preset_id:
        return None
    definition = ctx.registry.get(provider.provider_type)
    if definition is None:
        raise SettingsError("服务未注册。")
    for preset in definition.models:
        if preset.external_model_id == preset_id:
            return preset
    raise SettingsError("预设模型不存在。")


def _model_from_payload(ctx, payload: dict[str, Any], model_id: str | None) -> ModelConfig:
    provider = repository.get_provider(ctx.db, str(payload.get("providerId", "")))
    if not provider:
        raise SettingsError("服务不存在。")
    preset = _resolve_preset(ctx, provider, payload.get("preset"))
    name = str(payload.get("name", "")).strip()
    if not name or len(name) > 100:
        raise SettingsError("显示名称必填且不超过 100 字。")

    if preset:
        external_model_id = preset.external_model_id
        capabilities = list(preset.capabilities)
        parameter_schema = [field.to_dict() for field in preset.parameter_schema]
        input_constraints = dict(preset.input_constraints)
        version = preset.version
        description = str(payload.get("description") or preset.description or "") or None
    else:
        external_model_id = str(payload.get("externalModelId", "")).strip()
        if not external_model_id or len(external_model_id) > 200:
            raise SettingsError("服务商模型 ID 必填且不超过 200 字。")
        capabilities = payload.get("capabilities") or []
        if not isinstance(capabilities, list) or not capabilities:
            raise SettingsError("至少选择一个创作能力。")
        parameter_schema = _validate_parameter_schema(payload.get("parameterSchema") or [])
        input_constraints = payload.get("inputConstraints") or {}
        if not isinstance(input_constraints, dict):
            raise SettingsError("输入约束必须是对象。")
        version = str(payload.get("version") or "") or None
        description = str(payload.get("description") or "") or None

    definition = ctx.registry.get(provider.provider_type)
    allowed = set(definition.capabilities) if definition else set()
    for capability in capabilities:
        if capability not in allowed:
            raise SettingsError("所选服务不支持这些能力。")

    enabled = bool(payload.get("enabled", True))
    sort_order = int(payload.get("sortOrder", 0))
    if sort_order < 0 or sort_order > 99999:
        raise SettingsError("排序值必须在 0 到 99999 之间。")

    return ModelConfig(
        id=model_id or repository.new_id(),
        provider_id=provider.id,
        external_model_id=external_model_id,
        name=name,
        version=version,
        description=description,
        capabilities=capabilities,
        parameter_schema=parameter_schema,
        input_constraints=input_constraints,
        enabled=enabled,
        sort_order=sort_order,
    )


def list_models(ctx, capability: str | None = None, include_disabled: bool = False) -> list[ModelConfig]:
    provider_ids = [provider.id for provider in repository.list_providers(ctx.db)]
    return repository.list_models(ctx.db, provider_ids, capability, include_disabled)


def create_model(ctx, payload: dict[str, Any]) -> ModelConfig:
    model = _model_from_payload(ctx, payload, None)
    repository.create_model(ctx.db, model)
    return model


def update_model(ctx, model_id: str, payload: dict[str, Any]) -> ModelConfig:
    existing = repository.get_model(ctx.db, model_id)
    if not existing:
        raise SettingsError("模型不存在。")
    payload = {**payload, "providerId": existing.provider_id}
    model = _model_from_payload(ctx, payload, model_id)
    repository.update_model(ctx.db, model)
    return model


def delete_model(ctx, model_id: str) -> None:
    if not repository.delete_model(ctx.db, model_id):
        raise SettingsError("模型不存在。")
