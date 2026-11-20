"""Local filesystem media storage.

Every path is validated against ``MEDIA_ROOT`` before use.  Files are stored
under ``YYYY-MM-DD/<uuid><ext>`` so the directory stays browsable and backup is
a plain file copy.
"""

from __future__ import annotations

import hashlib
import shutil
import uuid
from datetime import date
from pathlib import Path

from ..config import MEDIA_ROOT
from .thumbnails import generate_image_thumbnail

ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}
ALLOWED_RESULT_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/avif": ".avif",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "audio/ogg": ".ogg",
    "text/markdown": ".md",
    "text/plain": ".txt",
}
ALLOWED_EXTENSIONS = set(ALLOWED_RESULT_TYPES.values()) | {".bin"}


class MediaError(ValueError):
    pass


class MediaService:
    def __init__(self, root: Path = MEDIA_ROOT) -> None:
        self.root = Path(root)

    def ensure_root(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def safe_key(self, key: str) -> str:
        if not key or "\x00" in key:
            raise MediaError("非法媒体路径。")
        candidate = Path(key)
        if candidate.is_absolute():
            raise MediaError("非法媒体路径。")
        normalized = candidate.as_posix().lstrip("/")
        parts = [part for part in normalized.split("/") if part not in ("", ".")]
        if not parts or any(part == ".." for part in parts):
            raise MediaError("非法媒体路径。")
        resolved = (self.root / Path(*parts)).resolve()
        root = self.root.resolve()
        if resolved != root and root not in resolved.parents:
            raise MediaError("非法媒体路径。")
        return "/".join(parts)

    def path(self, key: str) -> Path:
        return self.root / Path(*self.safe_key(key).split("/"))

    def read_bytes(self, key: str) -> bytes:
        return self.path(key).read_bytes()

    def write_bytes(self, data: bytes, extension: str) -> str:
        ext = extension.lower() if extension.startswith(".") else f".{extension.lower()}"
        if ext not in ALLOWED_EXTENSIONS:
            ext = ".bin"
        self.ensure_root()
        key = f"{date.today().isoformat()}/{uuid.uuid4().hex}{ext}"
        target = self.path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return key

    def remove(self, key: str) -> None:
        try:
            self.path(key).unlink()
        except FileNotFoundError:
            pass

    def usage(self) -> int:
        total = 0
        if not self.root.exists():
            return 0
        for path in self.root.rglob("*"):
            if path.is_file():
                try:
                    total += path.stat().st_size
                except OSError:
                    continue
        return total

    def free_bytes(self) -> int:
        try:
            return shutil.disk_usage(self.root).free
        except OSError:
            return 0

    # --- thumbnails ----------------------------------------------------------

    def thumbnail_key(self, storage_key: str) -> str:
        digest = hashlib.sha1(storage_key.encode("utf-8")).hexdigest()
        return f"thumbs/{digest}.jpg"

    def thumbnail_path(self, storage_key: str) -> Path:
        return self.path(self.thumbnail_key(storage_key))

    def ensure_thumbnail(self, storage_key: str) -> Path | None:
        """Generate (once) and return the cached thumbnail path, or None."""
        path = self.thumbnail_path(storage_key)
        if path.is_file():
            return path
        source = self.path(storage_key)
        if not source.is_file():
            return None
        thumbnail = generate_image_thumbnail(source.read_bytes())
        if thumbnail is None:
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
        temp.write_bytes(thumbnail)
        temp.replace(path)
        return path


def sniff_image_type(data: bytes) -> str | None:
    """Validate the real file header instead of trusting the upload MIME type."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def extension_for_mime(mime_type: str) -> str:
    return ALLOWED_RESULT_TYPES.get(mime_type, ".bin")
