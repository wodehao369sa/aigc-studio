"""Sync remote OpenAI-compatible model catalogs into the local model table."""

from __future__ import annotations

from .. import repository
from ..entities import ModelConfig
from ..providers.base import FieldSchema
from ..services import tasks as tasks_service


class OpenAICompatibleError(ValueError):
    pass


CHAT_SCHEMA = [
    FieldSchema(key="max_tokens", label="最大输出 Token", type="number", default=1024, min=1, max=65536).to_dict(),
    FieldSchema(key="temperature", label="温度", type="number", default=0.7, min=0, max=2).to_dict(),
]

IMAGE_SCHEMA = [
    FieldSchema(key="size", label="尺寸", type="text", default="1024x1024").to_dict(),
    FieldSchema(key="n", label="生成数量", type="number", default=1, min=1, max=4).to_dict(),
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
    adapter = ctx.registry.build_adapter(provider_id, runtime)
    if not hasattr(adapter, "list_remote_models"):
        raise OpenAICompatibleError("该服务商不支持远程模型列表。")

    remote_ids = await adapter.list_remote_models(runtime)
    existing = {
        model.external_model_id
        for model in repository.list_models(ctx.db, [provider_id], None, True)
    }
    created = 0
    for index, model_id in enumerate(remote_ids):
        if model_id in existing:
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
                parameter_schema=[*CHAT_SCHEMA, *IMAGE_SCHEMA],
                input_constraints={},
                enabled=True,
                sort_order=100 + index,
            ),
        )
        created += 1
    return {"fetched": len(remote_ids), "created": created, "total": len(remote_ids)}
