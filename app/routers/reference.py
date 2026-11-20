"""Public, tokenized reference media for upstream providers.

Nginx bypasses Basic Auth for ``/api/reference/`` so Agnes can fetch reference
images.  Access requires an unguessable token that expires after 24 hours and
is invalidated as soon as the task finishes.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from .. import repository
from ..services.media import MediaError

router = APIRouter()


@router.get("/api/reference/{token}")
def read_reference(token: str, request: Request):
    ctx = request.app.state.ctx
    asset = repository.get_reference_asset(ctx.db, token, int(time.time() * 1000))
    if not asset:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        path = ctx.media.path(asset.storage_key)
    except MediaError:
        raise HTTPException(status_code=404, detail="Not found")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(
        path,
        media_type=asset.mime_type,
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )
