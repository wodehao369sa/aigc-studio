"""Provider voice catalog API."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..services import voices as voices_service
from ..services.voices import VoiceError

router = APIRouter()


@router.get("/api/voices")
async def list_voices(
    request: Request,
    provider: str,
    search: str | None = None,
    language_code: str | None = None,
    page: int = 1,
    page_size: int = 50,
):
    try:
        return await voices_service.list_voices(
            request.app.state.ctx,
            provider,
            search=search,
            language_code=language_code,
            page=page,
            page_size=page_size,
        )
    except VoiceError as error:
        raise HTTPException(status_code=400, detail=str(error))
