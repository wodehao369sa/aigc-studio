"""Multi-turn conversations for text generation models.

A conversation owns a sequence of text tasks.  Each user turn is a normal task,
so generation history, retry and billing stay in the existing task model.  The
provider receives the full message history for context.
"""

from __future__ import annotations

import time
from typing import Any

from .. import repository
from ..entities import Conversation, Task
from . import tasks as tasks_service


class ConversationError(ValueError):
    pass


def _now() -> int:
    return int(time.time() * 1000)


def create_conversation(
    ctx,
    *,
    model_id: str,
    title: str | None = None,
    system_prompt: str | None = None,
) -> Conversation:
    model = repository.get_model(ctx.db, model_id)
    if not model or not model.enabled:
        raise ConversationError("模型不存在或已禁用。")
    if "text_generation" not in model.capabilities:
        raise ConversationError("所选模型不支持文本生成。")
    provider = repository.get_provider(ctx.db, model.provider_id)
    if not provider or not provider.enabled:
        raise ConversationError("服务不可用。")
    now = _now()
    conversation = Conversation(
        id=repository.new_id(),
        provider_id=model.provider_id,
        model_id=model.id,
        title=(title or "").strip() or "新对话",
        system_prompt=(system_prompt or "").strip() or None,
        created_at=now,
        updated_at=now,
    )
    repository.create_conversation(ctx.db, conversation)
    return conversation


def list_conversations(ctx) -> list[Conversation]:
    return repository.list_conversations(ctx.db)


def get_conversation(ctx, conversation_id: str) -> Conversation | None:
    return repository.get_conversation(ctx.db, conversation_id)


def _conversation_turns(db, conversation_id: str) -> list[Task]:
    return repository.list_conversation_tasks(db, conversation_id)


def get_messages(ctx, conversation_id: str) -> list[dict[str, str]]:
    """Return the chat transcript, including in-flight/failed turns."""
    messages: list[dict[str, str]] = []
    conversation = repository.get_conversation(ctx.db, conversation_id)
    if conversation and conversation.system_prompt:
        messages.append({"role": "system", "content": conversation.system_prompt})
    for task in _conversation_turns(ctx.db, conversation_id):
        prompt = str(task.parameters.get("prompt", ""))
        if prompt:
            messages.append(
                {"role": "user", "content": prompt, "taskId": task.id, "createdAt": task.created_at}
            )
        if task.status == "succeeded" and task.result_text:
            messages.append(
                {
                    "role": "assistant",
                    "content": task.result_text,
                    "taskId": task.id,
                    "createdAt": task.created_at,
                }
            )
        elif task.status in ("pending", "running"):
            messages.append(
                {
                    "role": "assistant",
                    "content": "生成中…",
                    "taskId": task.id,
                    "createdAt": task.created_at,
                    "status": "pending",
                }
            )
        elif task.status == "failed":
            messages.append(
                {
                    "role": "assistant",
                    "content": f"生成失败：{task.error or '未知错误'}",
                    "taskId": task.id,
                    "createdAt": task.created_at,
                    "status": "failed",
                }
            )
    return messages


def build_history(ctx, conversation_id: str, new_prompt: str) -> list[dict[str, str]]:
    """Only succeeded turns are sent to the model as context."""
    history: list[dict[str, str]] = []
    conversation = repository.get_conversation(ctx.db, conversation_id)
    if conversation and conversation.system_prompt:
        history.append({"role": "system", "content": conversation.system_prompt})
    for task in _conversation_turns(ctx.db, conversation_id):
        if task.status != "succeeded":
            continue
        prompt = str(task.parameters.get("prompt", ""))
        if prompt:
            history.append({"role": "user", "content": prompt})
        if task.result_text:
            history.append({"role": "assistant", "content": task.result_text})
    history.append({"role": "user", "content": new_prompt})
    return history


async def send_message(
    ctx,
    conversation_id: str,
    prompt: str,
    parameters: dict[str, Any] | None = None,
) -> Task:
    conversation = repository.get_conversation(ctx.db, conversation_id)
    if not conversation:
        raise ConversationError("对话不存在。")
    model = repository.get_model(ctx.db, conversation.model_id)
    provider = repository.get_provider(ctx.db, conversation.provider_id)
    if not model or not model.enabled:
        raise ConversationError("模型不可用。")
    if not provider or not provider.enabled:
        raise ConversationError("服务不可用。")

    is_first_turn = not repository.list_conversation_tasks(ctx.db, conversation_id)
    messages = build_history(ctx, conversation_id, prompt)
    task = await tasks_service.create_task(
        ctx,
        model_id=conversation.model_id,
        capability="text_generation",
        prompt=prompt,
        parameters=parameters,
        conversation_id=conversation.id,
        messages=messages,
    )
    fields: dict[str, Any] = {"updated_at": _now()}
    if is_first_turn:
        fields["title"] = prompt[:20]
    repository.update_conversation_fields(ctx.db, conversation.id, **fields)
    return task


def update_conversation(
    ctx,
    conversation_id: str,
    *,
    title: str | None = None,
    system_prompt: str | None = None,
) -> Conversation:
    conversation = repository.get_conversation(ctx.db, conversation_id)
    if not conversation:
        raise ConversationError("对话不存在。")
    fields: dict[str, Any] = {}
    if title is not None:
        fields["title"] = title.strip() or "新对话"
    if system_prompt is not None:
        fields["system_prompt"] = system_prompt.strip() or None
    if fields:
        repository.update_conversation_fields(ctx.db, conversation_id, **fields)
    return repository.get_conversation(ctx.db, conversation_id)  # type: ignore[return-value]


def delete_conversation(ctx, conversation_id: str) -> None:
    conversation = repository.get_conversation(ctx.db, conversation_id)
    if not conversation:
        raise ConversationError("对话不存在。")
    for task in repository.list_conversation_tasks(ctx.db, conversation_id):
        tasks_service.delete_task(ctx, task.id)
    repository.delete_conversation(ctx.db, conversation_id)
