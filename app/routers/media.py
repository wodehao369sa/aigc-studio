"""Protected media streaming."""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from .. import repository
from ..services.media import MediaError

router = APIRouter()

ALLOWED_MIME = re.compile(r"^(image/(png|jpeg|webp|gif|avif)|video/(mp4|webm)|audio/[a-z0-9.+-]+|text/(plain|markdown))$")


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]", "_", name)
    return cleaned or "file"


@router.get("/api/thumbnail/{asset_id}")
def read_thumbnail(asset_id: str, request: Request):
    """Serve a cached thumbnail; fall back to the original when unusable."""
    ctx = request.app.state.ctx
    asset = repository.get_asset(ctx.db, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        path = ctx.media.ensure_thumbnail(asset.storage_key)
    except MediaError:
        raise HTTPException(status_code=404, detail="Not found")

    if path is not None:
        return FileResponse(
            path,
            media_type="image/jpeg",
            headers={
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "public, max-age=31536000, immutable",
            },
        )

    try:
        original = ctx.media.path(asset.storage_key)
    except MediaError:
        raise HTTPException(status_code=404, detail="Not found")
    if not original.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    mime_type = asset.mime_type if ALLOWED_MIME.match(asset.mime_type) else "application/octet-stream"
    return FileResponse(original, media_type=mime_type, headers={"X-Content-Type-Options": "nosniff"})


@router.get("/api/media/{asset_id}")
def read_media(asset_id: str, request: Request):
    ctx = request.app.state.ctx
    asset = repository.get_asset(ctx.db, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        path = ctx.media.path(asset.storage_key)
    except MediaError:
        raise HTTPException(status_code=404, detail="Not found")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    mime_type = asset.mime_type if ALLOWED_MIME.match(asset.mime_type) else "application/octet-stream"
    filename = _safe_filename(asset.original_filename)
    return FileResponse(
        path,
        media_type=mime_type,
        filename=filename,
        content_disposition_type="inline",
        headers={"X-Content-Type-Options": "nosniff"},
    )
