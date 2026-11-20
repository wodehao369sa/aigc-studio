"""Asset lifecycle: uploads, generated results, reference counting and cleanup."""

from __future__ import annotations

import time
from typing import Any

from .. import repository
from ..config import MAX_UPLOAD_BYTES
from ..db import Database
from ..entities import Asset
from .media import MediaService, extension_for_mime, sniff_image_type


class AssetError(ValueError):
    pass


def create_upload_asset(
    db: Database,
    media: MediaService,
    filename: str,
    declared_mime: str,
    data: bytes,
) -> Asset:
    if len(data) > MAX_UPLOAD_BYTES:
        raise AssetError("单个文件不得超过 20 MB。")
    detected = sniff_image_type(data)
    if detected is None:
        raise AssetError("仅支持 PNG、JPEG、WebP 图片。")
    # Prefer the sniffed type; the declared type is only a hint from the browser.
    mime_type = detected
    safe_name = filename.replace("\\", "/").split("/")[-1][:120] or "upload"
    storage_key = media.write_bytes(data, extension_for_mime(mime_type))
    asset = Asset(
        id=repository.new_id(),
        storage_key=storage_key,
        original_filename=safe_name,
        mime_type=mime_type,
        size_bytes=len(data),
        metadata={"source": "upload", "declared_mime": declared_mime},
        created_at=int(time.time() * 1000),
    )
    repository.insert_asset(db, asset)
    return asset


def create_result_asset(
    db: Database,
    media: MediaService,
    data: bytes,
    mime_type: str,
    original_filename: str,
    metadata: dict[str, Any] | None = None,
) -> Asset:
    storage_key = media.write_bytes(data, extension_for_mime(mime_type))
    asset = Asset(
        id=repository.new_id(),
        storage_key=storage_key,
        original_filename=original_filename,
        mime_type=mime_type,
        size_bytes=len(data),
        metadata=metadata or {},
        created_at=int(time.time() * 1000),
    )
    repository.insert_asset(db, asset)
    return asset


def delete_task_assets(db: Database, media: MediaService, task_id: str) -> None:
    """Delete a task, its asset links, and any media no longer referenced."""
    links = repository.list_task_assets(db, task_id)
    repository.invalidate_task_tokens(db, task_id, int(time.time() * 1000))
    repository.delete_task(db, task_id)
    for link in links:
        if repository.count_asset_references(db, link.asset.id) == 0:
            media.remove(link.asset.storage_key)
            repository.delete_asset(db, link.asset.id)
