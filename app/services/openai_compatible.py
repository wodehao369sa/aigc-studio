"""Sync remote OpenAI-compatible model catalogs into the local model table."""

from __future__ import annotations

import json

from .. import repository
from ..entities import ModelConfig
from ..providers.base import FieldSchema
from ..services import tasks as tasks_service


class OpenAICompatibleError(ValueError):
    pass


TEXT_SCHEMA = [
    FieldSchema(
        key="max_tokens", label="最大输出 Token", type="number", default=4096, min=1, max=65536,
        capabilities=("text_generation",),
    ).to_dict(),
    FieldSchema(
        key="temperature", label="温度", type="number", default=0.7, min=0, max=2,
        capabilities=("text_generation",),
    ).to_dict(),
]

IMAGE_SCHEMA = [
    FieldSchema(
        key="size", label="尺寸", type="text", default="1024x1024",
        capabilities=("text_to_image", "image_to_image"),
    ).to_dict(),
    FieldSchema(
        key="n", label="生成数量", type="number", default=1, min=1, max=4,
        capabilities=("text_to_image", "image_to_image"),
    ).to_dict(),
]

SYNC_CAPABILITIES = ["text_generation", "text_to_image", "image_to_image"]


async def sync_models(ctx, provider_id: str = "openai_compatible") -> dict:
    provider = repository.get_provider(ctx.db, provider_id)
    if not provider or not provider.enabled:
        raise OpenAICompatibleError("服务不存在或已停用。")
    config = ctx.provider_configs.get(provider_id)
    if not config or not config.configured:
        raise OpenAICompatibleError(f"{provider_id} 未配置 API Key。")
    runtime = tasks_service.build_runtime(ctx, provider)
    adapter = ctx.registry.build_adapter(provider.provider_type, runtime)
    if not hasattr(adapter, "list_remote_models"):
        raise OpenAICompatibleError("该服务商不支持远程模型列表。")

    remote_ids = await adapter.list_remote_models(runtime)
    existing = {
        model.external_model_id: model
        for model in repository.list_models(ctx.db, [provider_id], None, True)
    }

    def needs_schema_upgrade(model: ModelConfig) -> bool:
        if '"capabilities"' not in json.dumps(model.parameter_schema, ensure_ascii=False):
            return True
        # 旧默认 1024 对推理模型不够用，升级到当前默认 4096。
        return any(
            field.get("key") == "max_tokens" and field.get("default") == 1024
            for field in model.parameter_schema
        )

    created = 0
    upgraded = 0
    for index, model_id in enumerate(remote_ids):
        if model_id in existing:
            model = existing[model_id]
            if needs_schema_upgrade(model):
                model.parameter_schema = [*TEXT_SCHEMA, *IMAGE_SCHEMA]
                repository.update_model(ctx.db, model)
                upgraded += 1
            continue
        repository.create_model(
            ctx.db,
            ModelConfig(
                id=repository.new_id(),
                provider_id=provider.id,
                external_model_id=model_id,
                name=model_id,
                version=None,
                description=None,
                capabilities=list(SYNC_CAPABILITIES),
                parameter_schema=[*TEXT_SCHEMA, *IMAGE_SCHEMA],
                input_constraints={},
                enabled=True,
                sort_order=100 + index,
            ),
        )
        created += 1
    return {
        "fetched": len(remote_ids),
        "created": created,
        "upgraded": upgraded,
        "total": len(remote_ids),
    }
