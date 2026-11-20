"""Shared test fixtures.

Environment variables are set before importing ``app`` so the application uses
a throwaway SQLite database and media directory.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_TMP = Path(tempfile.mkdtemp(prefix="aigc-studio-test-"))
os.environ["DATABASE_URL"] = str(_TMP / "test.db")
os.environ["MEDIA_ROOT"] = str(_TMP / "media")
os.environ["PROVIDERS_CONFIG_PATH"] = str(_TMP / "providers.yaml")
os.environ["PUBLIC_BASE_URL"] = "https://public.example.com"
os.environ["POLL_INTERVAL_SECONDS"] = "3600"
(_TMP / "providers.yaml").write_text(
    "providers:\n"
    "  - type: agnes\n"
    "    name: Agnes AI\n"
    "    baseUrl: https://apihub.agnes-ai.com/v1\n"
    "    apiKey: test-key\n"
    "  - type: xiaomi_mimo\n"
    "    name: Xiaomi MiMo\n"
    "    baseUrl: https://api.xiaomimimo.com/v1\n"
    "    apiKey: test-key\n"
    "  - type: modelscope\n"
    "    name: ModelScope\n"
    "    baseUrl: https://api-inference.modelscope.cn\n"
    "    apiKey: test-key\n"
    "  - type: fish_audio\n"
    "    name: Fish Audio\n"
    "    baseUrl: https://api.fish.audio/v1\n"
    "    apiKey: test-key\n"
    "  - type: breeze\n"
    "    name: Breeze\n"
    "    baseUrl: https://api.breeze.blue/v1\n"
    "    apiKey: test-key\n",
    encoding="utf-8",
)

from app.main import create_app  # noqa: E402


@pytest.fixture()
def client():
    app = create_app()
    with TestClient(app) as test_client:
        ctx = app.state.ctx
        for table in ("task_assets", "reference_tokens", "tasks", "assets", "models", "providers"):
            ctx.db.execute(f"DELETE FROM {table}")
        from app.services.settings import sync_provider_rows

        sync_provider_rows(ctx)
        yield test_client


@pytest.fixture()
def registered_model(client):
    """Register the Agnes video preset and return the model record."""
    response = client.post(
        "/api/settings/models",
        json={"providerId": "agnes", "preset": "agnes-video-2.5-flash", "name": "Agnes Video 2.5 Flash"},
    )
    assert response.status_code == 201, response.text
    return client.get("/api/models").json()[0]
