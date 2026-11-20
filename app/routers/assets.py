"""Asset upload API."""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from ..serializers import asset_dict
from ..services.assets import AssetError, create_upload_asset

router = APIRouter()


@router.post("/api/assets", status_code=201)
async def upload_asset(request: Request, file: UploadFile = File(...)):
    ctx = request.app.state.ctx
    data = await file.read()
    try:
        asset = create_upload_asset(
            ctx.db,
            ctx.media,
            file.filename or "upload",
            file.content_type or "",
            data,
        )
    except AssetError as error:
        raise HTTPException(status_code=400, detail=str(error))
    return asset_dict(asset)
