"""API router registration."""

from __future__ import annotations

from fastapi import FastAPI

from . import assets, conversations, health, internal, media, models, pages, reference, settings, tasks, voices


def register_routers(app: FastAPI) -> None:
    app.include_router(health.router)
    app.include_router(pages.router)
    app.include_router(conversations.router)
    app.include_router(assets.router)
    app.include_router(tasks.router)
    app.include_router(models.router)
    app.include_router(settings.router)
    app.include_router(media.router)
    app.include_router(reference.router)
    app.include_router(voices.router)
    app.include_router(internal.router)
