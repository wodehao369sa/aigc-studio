"""FastAPI application factory."""

from __future__ import annotations

import hashlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import (
    BASE_DIR,
    DATABASE_URL,
    POLL_BATCH_SIZE,
    POLL_INTERVAL_SECONDS,
    PUBLIC_BASE_URL,
)
from .context import AppContext
from .db import Database, initialize_database
from .provider_config import load_provider_configs
from .providers import discover_registry
from .routers import register_routers
from .routers.pages import templates
from .services.media import MediaService
from .services.scheduler import Scheduler
from .services.settings import sync_provider_rows

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("aigc-studio")


def compute_asset_version() -> str:
    """Hash the browser assets so deploys always bust client caches."""
    digest = hashlib.sha256()
    static_dir = BASE_DIR / "static"
    for name in ("app.css", "app.js"):
        path = static_dir / name
        if path.is_file():
            digest.update(name.encode("utf-8"))
            digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = Database(DATABASE_URL)
    initialize_database(db)

    media = MediaService()
    media.ensure_root()

    registry = discover_registry()
    ctx = AppContext(
        db=db,
        media=media,
        registry=registry,
        provider_configs=load_provider_configs(registry),
        public_base_url=PUBLIC_BASE_URL,
    )
    sync_provider_rows(ctx)

    app.state.ctx = ctx
    asset_version = compute_asset_version()
    app.state.asset_version = asset_version
    templates.env.globals["asset_version"] = asset_version
    scheduler = Scheduler(ctx, interval=POLL_INTERVAL_SECONDS, batch_size=POLL_BATCH_SIZE)
    app.state.scheduler = scheduler
    scheduler.start()

    logger.info("AIGC Studio %s ready; providers: %s", __version__, registry.ids())
    try:
        yield
    finally:
        await scheduler.stop()
        db.close()


def create_app() -> FastAPI:
    app = FastAPI(title="AIGC Studio", version=__version__, lifespan=lifespan)
    register_routers(app)
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

    @app.middleware("http")
    async def cache_headers(request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        # Reference tokens must never be stored by a shared cache.
        if path.startswith("/api/reference/"):
            return response
        if path.startswith("/static/") or path.startswith("/api/thumbnail/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-cache"
        elif response.headers.get("content-type", "").startswith("text/html"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    return app


app = create_app()
