"""OpenAI-compatible provider tests."""

from __future__ import annotations

import asyncio
import base64

from helpers import FakeAsyncClient, FakeResponse

from app.entities import ModelConfig
from app.providers.base import ProviderRuntime, TaskInput
from app.providers.openai_compatible import adapter as openai_adapter
from app.providers.openai_compatible.adapter import OpenAICompatibleAdapter

BASE = "https://compatible.example.com/v1"
PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
PNG = base64.b64decode(PNG_B64)


def _runtime() -> ProviderRuntime:
    return ProviderRuntime(
        provider_id="openai_compatible",
        base_url=BASE,
        api_key="test-key",
        timeout=5,
        public_base_url=None,
        media=None,
    )


def _model(model_id: str = "gpt-x") -> ModelConfig:
    return ModelConfig(
        id="m",
        provider_id="openai_compatible",
        external_model_id=model_id,
        name=model_id,
        version=None,
        description=None,
        capabilities=["text_generation"],
        parameter_schema=[],
        input_constraints={},
        enabled=True,
        sort_order=0,
    )


def test_reasoning_model_falls_back_to_reasoning_content(monkeypatch):
    async def handle(payload):
        return FakeResponse(
            {"choices": [{"message": {"content": None, "reasoning_content": "推理得到的答案"}}]}
        )

    FakeAsyncClient.routes = {("POST", f"{BASE}/chat/completions"): handle}
    monkeypatch.setattr(openai_adapter.httpx, "AsyncClient", FakeAsyncClient)

    ref = asyncio.run(
        OpenAICompatibleAdapter().submit(
            TaskInput(prompt="hi", parameters={}, assets=[], capability="text_generation"),
            _model(),
            _runtime(),
        )
    )
    assert ref.result_text == "推理得到的答案"


def test_list_remote_models(monkeypatch):
    async def handle(params=None):
        return FakeResponse({"data": [{"id": "gpt-x"}, {"id": "gpt-y"}, {"id": "z"}]})

    FakeAsyncClient.routes = {("GET", f"{BASE}/models"): handle}
    monkeypatch.setattr(openai_adapter.httpx, "AsyncClient", FakeAsyncClient)
    ids = asyncio.run(OpenAICompatibleAdapter().list_remote_models(_runtime()))
    assert ids == ["gpt-x", "gpt-y", "z"]


def test_submit_uses_messages_and_returns_text(monkeypatch):
    captured: dict = {}

    async def handle(payload):
        captured.update(payload)
        return FakeResponse({"choices": [{"message": {"content": "你好"}}]})

    FakeAsyncClient.routes = {("POST", f"{BASE}/chat/completions"): handle}
    monkeypatch.setattr(openai_adapter.httpx, "AsyncClient", FakeAsyncClient)

    task_input = TaskInput(
        prompt="hi",
        parameters={"temperature": 0.2, "max_tokens": 64},
        assets=[],
        capability="text_generation",
        messages=[
            {"role": "system", "content": "you are helpful"},
            {"role": "user", "content": "hi"},
        ],
    )
    ref = asyncio.run(OpenAICompatibleAdapter().submit(task_input, _model(), _runtime()))
    assert ref.result_text == "你好"
    assert captured["model"] == "gpt-x"
    assert captured["temperature"] == 0.2
    assert captured["messages"][0]["role"] == "system"


def test_sync_openai_models(client, monkeypatch):
    async def handle(params=None):
        return FakeResponse({"data": [{"id": "gpt-x"}, {"id": "gpt-y"}]})

    FakeAsyncClient.routes = {("GET", f"{BASE}/models"): handle}
    monkeypatch.setattr(openai_adapter.httpx, "AsyncClient", FakeAsyncClient)

    response = client.post("/api/settings/openai-compatible/sync")
    assert response.status_code == 200, response.text
    assert response.json()["created"] == 2

    models = [
        item
        for item in client.get("/api/models").json()
        if item["providerId"] == "openai_compatible"
    ]
    assert {item["externalModelId"] for item in models} == {"gpt-x", "gpt-y"}
    assert all("text_generation" in item["capabilities"] for item in models)

    # idempotent: no duplicates on a second sync
    again = client.post("/api/settings/openai-compatible/sync")
    assert again.json()["created"] == 0


def test_text_to_image(client, monkeypatch):
    async def handle_models(params=None):
        return FakeResponse({"data": [{"id": "image-model"}]})

    async def handle_image(payload):
        assert payload["prompt"] == "a cat"
        assert payload["size"] == "1024x1024"
        return FakeResponse({"data": [{"url": "data:image/png;base64," + PNG_B64}]})

    FakeAsyncClient.routes = {
        ("GET", f"{BASE}/models"): handle_models,
        ("POST", f"{BASE}/images/generations"): handle_image,
    }
    monkeypatch.setattr(openai_adapter.httpx, "AsyncClient", FakeAsyncClient)
    client.post("/api/settings/openai-compatible/sync")
    model_id = next(
        item["id"]
        for item in client.get("/api/models").json()
        if item["externalModelId"] == "image-model"
    )

    task = client.post(
        "/api/tasks",
        json={
            "modelId": model_id,
            "capability": "text_to_image",
            "prompt": "a cat",
            "parameters": {"size": "1024x1024"},
        },
    ).json()
    assert task["status"] == "succeeded", task
    assert task["resultAssetId"]


def test_image_to_image_uses_edits_endpoint(client, monkeypatch):
    upload = client.post("/api/assets", files={"file": ("ref.png", PNG, "image/png")})
    assert upload.status_code == 201, upload.text
    asset_id = upload.json()["id"]
    captured: dict = {}

    async def handle_models(params=None):
        return FakeResponse({"data": [{"id": "image-model"}]})

    async def handle_edit(payload, data=None, files=None):
        captured["data"] = data
        captured["files"] = files
        return FakeResponse({"data": [{"url": "data:image/png;base64," + PNG_B64}]})

    FakeAsyncClient.routes = {
        ("GET", f"{BASE}/models"): handle_models,
        ("POST", f"{BASE}/images/edits"): handle_edit,
    }
    monkeypatch.setattr(openai_adapter.httpx, "AsyncClient", FakeAsyncClient)
    client.post("/api/settings/openai-compatible/sync")
    model_id = next(
        item["id"]
        for item in client.get("/api/models").json()
        if item["externalModelId"] == "image-model"
    )

    task = client.post(
        "/api/tasks",
        json={
            "modelId": model_id,
            "capability": "image_to_image",
            "prompt": "make it cyberpunk",
            "assets": [{"role": "source_image", "assetId": asset_id}],
        },
    ).json()
    assert task["status"] == "succeeded", task
    assert captured["data"]["model"] == "image-model"
    assert captured["files"][0][0] == "image"
    assert captured["files"][0][1][1] == PNG


def test_image_edit_falls_back_to_generations(client, monkeypatch):
    upload = client.post("/api/assets", files={"file": ("ref.png", PNG, "image/png")})
    asset_id = upload.json()["id"]
    captured: dict = {}

    async def handle_models(params=None):
        return FakeResponse({"data": [{"id": "image-model"}]})

    async def handle_edit(payload, data=None, files=None):
        return FakeResponse({"detail": "not found"}, status_code=404)

    async def handle_generate(payload):
        captured.update(payload)
        return FakeResponse({"data": [{"b64_json": base64.b64encode(PNG).decode()}]})

    FakeAsyncClient.routes = {
        ("GET", f"{BASE}/models"): handle_models,
        ("POST", f"{BASE}/images/edits"): handle_edit,
        ("POST", f"{BASE}/images/generations"): handle_generate,
    }
    monkeypatch.setattr(openai_adapter.httpx, "AsyncClient", FakeAsyncClient)
    client.post("/api/settings/openai-compatible/sync")
    model_id = next(
        item["id"]
        for item in client.get("/api/models").json()
        if item["externalModelId"] == "image-model"
    )

    task = client.post(
        "/api/tasks",
        json={
            "modelId": model_id,
            "capability": "image_to_image",
            "prompt": "edit",
            "assets": [{"role": "source_image", "assetId": asset_id}],
        },
    ).json()
    assert task["status"] == "succeeded", task
    assert captured["image"].startswith("data:image/png;base64,")


def test_multiple_openai_compatible_instances(client, monkeypatch, tmp_path):
    from app import provider_config, repository
    from app.services.settings import sync_provider_rows

    path = tmp_path / "providers.yaml"
    path.write_text(
        "providers:\n"
        "  - type: openai_compatible\n"
        "    id: site-a\n"
        "    name: 站点A\n"
        "    baseUrl: https://a.example.com/v1\n"
        "    apiKey: key-a\n"
        "  - type: openai_compatible\n"
        "    id: site-b\n"
        "    name: 站点B\n"
        "    baseUrl: https://b.example.com/v1\n"
        "    apiKey: key-b\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(provider_config, "PROVIDERS_CONFIG_PATH", path)

    ctx = client.app.state.ctx
    sync_provider_rows(ctx)
    rows = repository.list_providers(ctx.db)
    assert {row.id for row in rows} >= {"site-a", "site-b"}
    assert all(row.provider_type == "openai_compatible" for row in rows if row.id.startswith("site-"))

    runtime_a = __import__("app.services.tasks", fromlist=["build_runtime"]).build_runtime(
        ctx, repository.get_provider(ctx.db, "site-a")
    )
    assert runtime_a.base_url == "https://a.example.com/v1"
    assert runtime_a.api_key == "key-a"


def test_synced_model_can_generate_text(client, monkeypatch):
    async def handle_models(params=None):
        return FakeResponse({"data": [{"id": "gpt-x"}]})

    async def handle_chat(payload):
        return FakeResponse({"choices": [{"message": {"content": "生成的文本"}}]})

    FakeAsyncClient.routes = {
        ("GET", f"{BASE}/models"): handle_models,
        ("POST", f"{BASE}/chat/completions"): handle_chat,
    }
    monkeypatch.setattr(openai_adapter.httpx, "AsyncClient", FakeAsyncClient)
    client.post("/api/settings/openai-compatible/sync")
    model_id = next(
        item["id"]
        for item in client.get("/api/models").json()
        if item["externalModelId"] == "gpt-x"
    )

    task = client.post(
        "/api/tasks",
        json={"modelId": model_id, "capability": "text_generation", "prompt": "写一句话"},
    ).json()
    assert task["status"] == "succeeded", task
    assert task["resultText"] == "生成的文本"
