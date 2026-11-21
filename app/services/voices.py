"""Provider voice catalogs (where the provider exposes a voice list)."""

from __future__ import annotations

from .. import repository
from .tasks import build_runtime


class VoiceError(ValueError):
    pass


async def list_voices(
    ctx,
    provider_type: str,
    *,
    search: str | None = None,
    language_code: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    provider = repository.get_provider(ctx.db, provider_type)
    if not provider or not provider.enabled:
        raise VoiceError("服务不存在或已停用。")
    try:
        runtime = build_runtime(ctx, provider)
    except RuntimeError as error:
        raise VoiceError(str(error))
    adapter = ctx.registry.build_adapter(provider.provider_type, runtime)
    if not hasattr(adapter, "list_voices"):
        raise VoiceError("该服务商不支持音色列表。")
    return await adapter.list_voices(
        runtime,
        search=search,
        language_code=language_code,
        page=page,
        page_size=page_size,
    )
