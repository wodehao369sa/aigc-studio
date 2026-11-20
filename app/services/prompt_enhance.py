"""Prompt enhancement: template library, model bindings and rendering.

A template is just a prompt.  Binding a template to an image model also selects
which text model performs the enhancement, and marks one binding as default.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from .. import repository
from ..catalog import CAPABILITY_LABELS
from ..entities import ModelConfig, ModelPromptBinding, PromptTemplate
from ..providers.base import TaskInput
from . import tasks as tasks_service

import logging

logger = logging.getLogger(__name__)


class PromptEnhanceError(ValueError):
    pass


def _now() -> int:
    return int(time.time() * 1000)


# --- template library -------------------------------------------------------


def list_templates(ctx) -> list[PromptTemplate]:
    return repository.list_prompt_templates(ctx.db)


def create_template(
    ctx, name: str, content: str, as_system: bool = False
) -> PromptTemplate:
    name = (name or "").strip()
    content = (content or "").strip()
    if not name:
        raise PromptEnhanceError("模板名称必填。")
    if not content:
        raise PromptEnhanceError("模板内容必填。")
    now = _now()
    template = PromptTemplate(
        id=repository.new_id(),
        name=name[:60],
        content=content,
        created_at=now,
        updated_at=now,
        as_system=bool(as_system),
    )
    repository.create_prompt_template(ctx.db, template)
    return template


def update_template(
    ctx, template_id: str, name: str, content: str, as_system: bool = False
) -> PromptTemplate:
    existing = repository.get_prompt_template(ctx.db, template_id)
    if not existing:
        raise PromptEnhanceError("模板不存在。")
    name = (name or "").strip()
    content = (content or "").strip()
    if not name or not content:
        raise PromptEnhanceError("模板名称和内容必填。")
    template = PromptTemplate(
        id=existing.id,
        name=name[:60],
        content=content,
        created_at=existing.created_at,
        updated_at=_now(),
        as_system=bool(as_system),
    )
    repository.update_prompt_template(ctx.db, template)
    return template


def delete_template(ctx, template_id: str) -> None:
    repository.delete_prompt_template(ctx.db, template_id)


# --- model bindings ---------------------------------------------------------


def list_bindings(ctx, model_id: str) -> list[ModelPromptBinding]:
    return repository.list_bindings(ctx.db, model_id)


def get_default_binding(ctx, model_id: str) -> ModelPromptBinding | None:
    return repository.get_default_binding(ctx.db, model_id)


# --- global default ---------------------------------------------------------


def get_global_config(ctx) -> dict[str, Any]:
    config = repository.get_enhance_config(ctx.db)
    if not config:
        return {"enabled": False, "templateId": None, "enhancerModelId": None}
    return {
        "enabled": bool(config["enabled"]),
        "templateId": config["template_id"],
        "enhancerModelId": config["enhancer_model_id"],
    }


def save_global_config(
    ctx, enabled: bool, template_id: str | None, enhancer_model_id: str | None
) -> dict[str, Any]:
    templates = {item.id: item for item in repository.list_prompt_templates(ctx.db)}
    text_models = {
        model.id for model in repository.list_models(ctx.db, None, "text_generation", True)
    }
    if enabled:
        if not template_id or template_id not in templates:
            raise PromptEnhanceError("请选择全局默认模板。")
        if not enhancer_model_id or enhancer_model_id not in text_models:
            raise PromptEnhanceError("请选择全局增强模型。")
    repository.set_enhance_config(
        ctx.db,
        enabled,
        template_id if enabled else None,
        enhancer_model_id if enabled else None,
        _now(),
    )
    return get_global_config(ctx)


def available_bindings(ctx, model_id: str, capability: str) -> list[dict[str, Any]]:
    """Templates usable for a model + capability: model bindings plus the global fallback."""
    names = {item.id: item.name for item in repository.list_prompt_templates(ctx.db)}
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for binding in repository.list_bindings(ctx.db, model_id):
        if binding.capability and binding.capability != capability:
            continue
        items.append(
            {
                "templateId": binding.template_id,
                "enhancerModelId": binding.enhancer_model_id,
                "capability": binding.capability,
                "isDefault": binding.is_default,
                "templateName": names.get(binding.template_id),
                "source": "model",
            }
        )
        seen.add(binding.template_id)
    config = repository.get_enhance_config(ctx.db)
    if config and config["enabled"] and config["template_id"] and config["template_id"] not in seen:
        items.append(
            {
                "templateId": config["template_id"],
                "enhancerModelId": config["enhancer_model_id"],
                "capability": None,
                "isDefault": False,
                "templateName": names.get(config["template_id"]),
                "source": "global",
            }
        )
    return items


def resolve_template_and_enhancer(ctx, model_id: str, template_id: str):
    template = repository.get_prompt_template(ctx.db, template_id)
    if not template:
        raise PromptEnhanceError("模板不存在。")
    for binding in repository.list_bindings(ctx.db, model_id):
        if binding.template_id == template_id:
            enhancer = repository.get_model(ctx.db, binding.enhancer_model_id)
            if enhancer:
                return template, enhancer
    config = repository.get_enhance_config(ctx.db)
    if config and config["enabled"] and config["template_id"] == template_id:
        enhancer = repository.get_model(ctx.db, config["enhancer_model_id"])
        if enhancer:
            return template, enhancer
    raise PromptEnhanceError("该模板未绑定增强模型。")


def set_bindings(
    ctx,
    model_id: str,
    bindings: list[dict[str, Any]],
) -> list[ModelPromptBinding]:
    """Replace the binding set for an image model.

    Each binding: {templateId, enhancerModelId, capability?, isDefault, sortOrder}.
    """
    if not repository.get_model(ctx.db, model_id):
        raise PromptEnhanceError("图片模型不存在。")
    templates = {template.id: template for template in repository.list_prompt_templates(ctx.db)}
    text_models = {
        model.id
        for model in repository.list_models(ctx.db, None, "text_generation", True)
    }
    parsed: list[ModelPromptBinding] = []
    seen: set[tuple[str, str | None]] = set()
    for index, item in enumerate(bindings):
        template_id = str(item.get("templateId", "")).strip()
        enhancer_model_id = str(item.get("enhancerModelId", "")).strip()
        capability_value = item.get("capability")
        capability = str(capability_value) if capability_value else None
        if template_id not in templates:
            raise PromptEnhanceError("模板不存在。")
        if enhancer_model_id not in text_models:
            raise PromptEnhanceError("增强模型不支持文本生成。")
        key = (template_id, capability)
        if key in seen:
            continue
        seen.add(key)
        parsed.append(
            ModelPromptBinding(
                model_id=model_id,
                template_id=template_id,
                enhancer_model_id=enhancer_model_id,
                is_default=bool(item.get("isDefault")),
                sort_order=int(item.get("sortOrder", index)),
                capability=capability,
            )
        )
    defaults = [binding for binding in parsed if binding.is_default]
    if len({binding.capability for binding in defaults}) < len(defaults):
        raise PromptEnhanceError("每个能力只能有一个默认模板。")
    if parsed and not defaults:
        parsed[0].is_default = True
    repository.set_bindings(ctx.db, model_id, parsed)
    return repository.list_bindings(ctx.db, model_id)


# --- rendering / enhancement ------------------------------------------------


def render_template(
    content: str,
    prompt: str,
    model: ModelConfig,
    capability: str,
    has_reference: bool,
) -> str:
    return (
        content.replace("{{prompt}}", prompt)
        .replace("{{capability}}", CAPABILITY_LABELS.get(capability, capability))
        .replace("{{model}}", model.name)
        .replace("{{has_reference}}", "true" if has_reference else "false")
    )


async def enhance(
    ctx,
    *,
    template: PromptTemplate,
    enhancer_model: ModelConfig,
    prompt: str,
    image_model: ModelConfig,
    capability: str,
    has_reference: bool,
) -> str:
    rendered = render_template(template.content, prompt, image_model, capability, has_reference)
    if template.as_system:
        messages = [
            {"role": "system", "content": rendered},
            {"role": "user", "content": prompt},
        ]
    else:
        messages = [{"role": "user", "content": rendered}]
    provider = repository.get_provider(ctx.db, enhancer_model.provider_id)
    if not provider:
        raise PromptEnhanceError("增强模型的服务不存在。")
    runtime = tasks_service.build_runtime(ctx, provider)
    adapter = ctx.registry.build_adapter(provider.provider_type, runtime)
    task_input = TaskInput(
        prompt=prompt, parameters={}, assets=[], capability="text_generation", messages=messages
    )
    ref = await adapter.submit(task_input, enhancer_model, runtime)
    if not ref.result_text:
        raise PromptEnhanceError("增强模型未返回内容。")
    return _extract_rewritten(ref.result_text)


def _extract_rewritten(text: str) -> str:
    """The official Qwen rewriters answer with JSON; keep the prompt field."""
    stripped = (text or "").strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    if stripped.startswith("{"):
        try:
            data = json.loads(stripped)
        except ValueError:
            data = None
        if isinstance(data, dict) and data.get("rewritten_prompt"):
            return str(data["rewritten_prompt"]).strip()
    return stripped


async def preview(
    ctx,
    *,
    template_id: str,
    enhancer_model_id: str,
    prompt: str,
    model_id: str,
    capability: str,
    has_reference: bool = False,
) -> dict:
    template = repository.get_prompt_template(ctx.db, template_id)
    if not template:
        raise PromptEnhanceError("模板不存在。")
    enhancer_model = repository.get_model(ctx.db, enhancer_model_id)
    image_model = repository.get_model(ctx.db, model_id)
    if not enhancer_model or not image_model:
        raise PromptEnhanceError("模型不存在。")
    enhanced = await enhance(
        ctx,
        template=template,
        enhancer_model=enhancer_model,
        prompt=prompt,
        image_model=image_model,
        capability=capability,
        has_reference=has_reference,
    )
    return {"enhancedPrompt": enhanced, "templateId": template.id}


# --- bundled defaults ---------------------------------------------------------

from ..config import BASE_DIR  # noqa: E402

QWEN_MODEL_ID = "Qwen/Qwen-Image-2.1"
PRESET_T2I_NAME = "Qwen-Image-2.1 文生图增强（官方）"
PRESET_EDIT_NAME = "Qwen-Image-2.1 图像编辑增强（官方）"
GENERAL_NAME = "通用提示词增强"
PRESET_DIR = BASE_DIR / "app" / "prompt_presets"


def _seed_template(ctx, name: str, filename: str) -> PromptTemplate:
    existing = next(
        (item for item in repository.list_prompt_templates(ctx.db) if item.name == name), None
    )
    if existing:
        return existing
    content = (PRESET_DIR / filename).read_text(encoding="utf-8").strip()
    return create_template(ctx, name, content, as_system=True)


def ensure_defaults(ctx) -> None:
    """Seed the official Qwen-Image-2.1 rewriters and bind them to the model."""
    try:
        t2i = _seed_template(ctx, PRESET_T2I_NAME, "qwen-image-2.1-t2i.txt")
        edit = _seed_template(ctx, PRESET_EDIT_NAME, "qwen-image-2.1-edit.txt")
    except OSError:
        logger.warning("bundled prompt presets are unavailable at %s", PRESET_DIR)
        return
    enhancers = repository.list_models(ctx.db, None, "text_generation", False)
    if not enhancers:
        return
    enhancer = enhancers[0]
    general = _seed_template(ctx, GENERAL_NAME, "general.txt")
    if repository.get_enhance_config(ctx.db) is None:
        repository.set_enhance_config(ctx.db, True, general.id, enhancer.id, _now())
    for model in repository.list_models(ctx.db):
        if model.external_model_id != QWEN_MODEL_ID or not model.enabled:
            continue
        existing = repository.list_bindings(ctx.db, model.id)
        if any(binding.template_id in (t2i.id, edit.id) for binding in existing):
            continue
        repository.set_bindings(
            ctx.db,
            model.id,
            [
                ModelPromptBinding(model.id, t2i.id, enhancer.id, True, 0, "text_to_image"),
                ModelPromptBinding(model.id, edit.id, enhancer.id, True, 1, "image_to_image"),
            ],
        )
