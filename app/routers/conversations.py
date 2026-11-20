"""Conversation API for multi-turn text generation."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .. import repository
from ..serializers import conversation_dict, task_dict
from ..services import conversations as conversations_service
from ..services.conversations import ConversationError
from ..services.tasks import TaskError

router = APIRouter()


class CreateConversationRequest(BaseModel):
    modelId: str = Field(min_length=1, max_length=64)
    title: str | None = Field(default=None, max_length=100)
    systemPrompt: str | None = Field(default=None, max_length=20000)


class UpdateConversationRequest(BaseModel):
    title: str | None = Field(default=None, max_length=100)
    systemPrompt: str | None = Field(default=None, max_length=20000)


class SendMessageRequest(BaseModel):
    prompt: str = Field(min_length=1)
    parameters: dict = Field(default_factory=dict)


def _model_name(ctx, model_id: str) -> str | None:
    model = repository.get_model(ctx.db, model_id)
    return model.name if model else None


@router.get("/api/conversations")
def list_conversations(request: Request):
    ctx = request.app.state.ctx
    return [
        conversation_dict(conversation, _model_name(ctx, conversation.model_id))
        for conversation in conversations_service.list_conversations(ctx)
    ]


@router.post("/api/conversations", status_code=201)
def create_conversation(request: Request, body: CreateConversationRequest):
    ctx = request.app.state.ctx
    try:
        conversation = conversations_service.create_conversation(
            ctx,
            model_id=body.modelId,
            title=body.title,
            system_prompt=body.systemPrompt,
        )
    except ConversationError as error:
        raise HTTPException(status_code=400, detail=str(error))
    return conversation_dict(conversation, _model_name(ctx, conversation.model_id))


@router.get("/api/conversations/{conversation_id}")
def get_conversation(conversation_id: str, request: Request):
    ctx = request.app.state.ctx
    conversation = conversations_service.get_conversation(ctx, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="对话不存在")
    return {
        **conversation_dict(conversation, _model_name(ctx, conversation.model_id)),
        "messages": conversations_service.get_messages(ctx, conversation_id),
    }


@router.post("/api/conversations/{conversation_id}/messages", status_code=202)
async def send_message(conversation_id: str, request: Request, body: SendMessageRequest):
    ctx = request.app.state.ctx
    try:
        task = await conversations_service.send_message(
            ctx,
            conversation_id,
            body.prompt,
            parameters=body.parameters,
        )
    except ConversationError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except TaskError as error:
        raise HTTPException(status_code=400, detail=str(error))
    return task_dict(task)


@router.patch("/api/conversations/{conversation_id}")
def update_conversation(conversation_id: str, request: Request, body: UpdateConversationRequest):
    ctx = request.app.state.ctx
    try:
        conversation = conversations_service.update_conversation(
            ctx,
            conversation_id,
            title=body.title,
            system_prompt=body.systemPrompt,
        )
    except ConversationError as error:
        raise HTTPException(status_code=400, detail=str(error))
    return conversation_dict(conversation, _model_name(ctx, conversation.model_id))


@router.delete("/api/conversations/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: str, request: Request):
    ctx = request.app.state.ctx
    try:
        conversations_service.delete_conversation(ctx, conversation_id)
    except ConversationError as error:
        raise HTTPException(status_code=404, detail=str(error))
    return None
