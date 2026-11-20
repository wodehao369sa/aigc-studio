"""ModelScope API-Inference adapter tests."""

from __future__ import annotations

import asyncio
import base64

from helpers import FakeAsyncClient, FakeResponse

from app.entities import ModelConfig
from app.providers.base import AssetInput, ProviderRuntime, ProviderTaskRef, TaskInput
from app.providers.modelscope import adapter as modelscope_adapter
from app.providers.modelscope.adapter import ModelScopeAdapter
from app.services.media import MediaService

BASE_URL = "https://api-inference.modelscope.cn"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _model(external_model_id: str = "Qwen/Qwen-Image-2.1") -> ModelConfig:
    return ModelConfig(
        id="m",
        provider_id="modelscope",
        external_model_id=external_model_id,
        name="ModelScope",
        version=None,
        description=None,
        capabilities=["text_to_image", "image_to_image"],
        parameter_schema=[],
        input_constraints={},
        enabled=True,
        sort_order=0,
    )


def _runtime(media: MediaService) -> ProviderRuntime:
    return ProviderRuntime(
        provider_id="modelscope",
        base_url=BASE_URL,
        api_key="test-key",
        timeout=5,
        public_base_url=None,
        media=media,
    )


def test_validate_rules():
    adapter = ModelScopeAdapter()
    model = _model()
    assert adapter.validate(
        TaskInput(prompt="", parameters={}, assets=[], capability="text_to_image"), model
    )
    assert adapter.validate(
        TaskInput(prompt="hi", parameters={}, assets=[], capability="image_to_image"), model
    )
    assert adapter.validate(
        TaskInput(
            prompt="hi",
            parameters={},
            assets=[AssetInput("source_image", "a", "k", "image/png")],
            capability="text_to_image",
        ),
        model,
    )


def test_submit_uses_async_header(monkeypatch):
    captured: dict = {}

    async def handle(payload):
        captured.update(payload)
        return FakeResponse({"task_id": "task-1"})

    FakeAsyncClient.routes = {("POST", f"{BASE_URL}/v1/images/generations"): handle}
    monkeypatch.setattr(modelscope_adapter.httpx, "AsyncClient", FakeAsyncClient)

    adapter = ModelScopeAdapter()
    task_input = TaskInput(
        prompt="一只猫",
        parameters={"size": "1024x1024", "seed": 42, "steps": 30, "guidance": 4.0},
        assets=[],
        capability="text_to_image",
    )
    ref = asyncio.run(adapter.submit(task_input, _model(), _runtime(MediaService("/tmp/unused"))))
    assert ref.external_task_id == "task-1"
    assert captured["model"] == "Qwen/Qwen-Image-2.1"
    assert captured["size"] == "1024x1024"
    assert captured["seed"] == 42
    assert captured["guidance"] == 4.0


def test_image_to_image_sends_base64(monkeypatch, tmp_path):
    media = MediaService(tmp_path / "media")
    media.ensure_root()
    key = media.write_bytes(PNG, ".png")

    captured: dict = {}

    async def handle(payload):
        captured.update(payload)
        return FakeResponse({"task_id": "task-2"})

    FakeAsyncClient.routes = {("POST", f"{BASE_URL}/v1/images/generations"): handle}
    monkeypatch.setattr(modelscope_adapter.httpx, "AsyncClient", FakeAsyncClient)

    adapter = ModelScopeAdapter()
    task_input = TaskInput(
        prompt="改成赛博朋克",
        parameters={},
        assets=[AssetInput("source_image", "a", key, "image/png")],
        capability="image_to_image",
    )
    asyncio.run(adapter.submit(task_input, _model(), _runtime(media)))
    assert captured["image_url"] == [f"data:image/png;base64,{base64.b64encode(PNG).decode()}"]


def test_status_mapping(monkeypatch):
    state = {"task_status": "RUNNING"}

    async def handle(params):
        return FakeResponse(state)

    FakeAsyncClient.routes = {("GET", f"{BASE_URL}/v1/tasks/task-1"): handle}
    monkeypatch.setattr(modelscope_adapter.httpx, "AsyncClient", FakeAsyncClient)

    adapter = ModelScopeAdapter()
    ref = ProviderTaskRef(external_task_id="task-1")
    runtime = _runtime(MediaService("/tmp/unused"))

    result = asyncio.run(adapter.get_status(ref, _model(), runtime))
    assert result.status == "running"

    state.update({"task_status": "SUCCEED", "output_images": ["https://x/out.png"]})
    result = asyncio.run(adapter.get_status(ref, _model(), runtime))
    assert result.status == "succeeded"
    assert result.result_urls == ["https://x/out.png"]

    state.update({"task_status": "FAILED", "message": "boom"})
    result = asyncio.run(adapter.get_status(ref, _model(), runtime))
    assert result.status == "failed"
    assert "boom" in (result.error or "")


def test_transient_poll_errors_are_retried(client, monkeypatch):
    import asyncio

    from app.services import tasks as tasks_service

    created = client.post(
        "/api/settings/models",
        json={
            "providerId": "modelscope",
            "preset": "Qwen/Qwen-Image-2.1-Turbo",
            "name": "Qwen Image 2.1 Turbo",
        },
    )
    assert created.status_code == 201, created.text
    model_id = created.json()["id"]
    data_uri = "data:image/png;base64," + base64.b64encode(PNG).decode()

    state = {"polls": 0}

    async def submit(payload):
        return FakeResponse({"task_id": "task-transient"})

    async def status(params):
        state["polls"] += 1
        if state["polls"] <= 2:
            return FakeResponse({"errors": {"message": "temporary"}}, status_code=400)
        return FakeResponse({"task_status": "SUCCEED", "output_images": [data_uri]})

    FakeAsyncClient.routes = {
        ("POST", f"{BASE_URL}/v1/images/generations"): submit,
        ("GET", f"{BASE_URL}/v1/tasks/task-transient"): status,
    }
    monkeypatch.setattr(modelscope_adapter.httpx, "AsyncClient", FakeAsyncClient)

    ctx = client.app.state.ctx

    async def run():
        task = await tasks_service.create_task(
            ctx, model_id=model_id, capability="text_to_image", prompt="hi"
        )
        first = await tasks_service.poll_one_task(ctx)
        second = await tasks_service.poll_one_task(ctx)
        third = await tasks_service.poll_one_task(ctx)
        return task, first, second, third

    task, first, second, third = asyncio.run(run())
    assert task.status == "running"
    assert first.status == "running"
    assert second.status == "running"
    assert third.status == "succeeded"
    assert third.result_asset_id


def test_content_moderation_failure_is_reported(monkeypatch):
    async def handle(params):
        return FakeResponse(
            {
                "task_status": "FAILED",
                "errors": {"code": 400, "message": "Output data may contain inappropriate content."},
            },
            status_code=400,
        )

    FakeAsyncClient.routes = {("GET", f"{BASE_URL}/v1/tasks/task-1"): handle}
    monkeypatch.setattr(modelscope_adapter.httpx, "AsyncClient", FakeAsyncClient)

    adapter = ModelScopeAdapter()
    result = asyncio.run(
        adapter.get_status(
            ProviderTaskRef(external_task_id="task-1"),
            _model(),
            _runtime(MediaService("/tmp/unused")),
        )
    )
    assert result.status == "failed"
    assert "inappropriate content" in (result.error or "")
