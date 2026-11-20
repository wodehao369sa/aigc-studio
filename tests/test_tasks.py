"""Task state machine and API tests with a mocked Agnes upstream."""

from __future__ import annotations

import asyncio
import base64
import time

import pytest

from helpers import FakeAsyncClient, FakeResponse

from app.providers.agnes import adapter as agnes_adapter
from app import repository
from app.services import tasks as tasks_service

BASE_URL = "https://apihub.agnes-ai.com/v1"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _upload(client, name="pixel.png"):
    response = client.post("/api/assets", files={"file": (name, PNG, "image/png")})
    assert response.status_code == 201, response.text
    return response.json()


def _register_image_model(client):
    response = client.post(
        "/api/settings/models",
        json={"providerId": "agnes", "preset": "agnes-image-2.5-flash", "name": "Agnes Image 2.5 Flash"},
    )
    assert response.status_code == 201, response.text
    return next(
        model
        for model in client.get("/api/models").json()
        if model["externalModelId"] == "agnes-image-2.5-flash"
    )


def _mock_video_create(monkeypatch, video_id="vid-1", task_id="task-1"):
    FakeAsyncClient.routes = {
        ("POST", f"{BASE_URL}/videos"): lambda payload: FakeResponse({"video_id": video_id, "task_id": task_id})
    }
    monkeypatch.setattr(agnes_adapter.httpx, "AsyncClient", FakeAsyncClient)


def _mock_video_status(monkeypatch, status="running", progress=10, url=None, error=None):
    payload = {"status": status, "progress": progress}
    if url:
        payload["url"] = url
    if error:
        payload["error"] = error
    FakeAsyncClient.routes = {
        ("GET", "https://apihub.agnes-ai.com/agnesapi"): lambda params: FakeResponse(payload)
    }
    monkeypatch.setattr(agnes_adapter.httpx, "AsyncClient", FakeAsyncClient)


def test_upload_rejects_fake_image(client):
    response = client.post("/api/assets", files={"file": ("evil.png", b"MZ-not-an-image", "image/png")})
    assert response.status_code == 400
    assert "PNG" in response.json()["detail"]


def test_create_task_validation(client, registered_model):
    response = client.post(
        "/api/tasks",
        json={"modelId": registered_model["id"], "capability": "text_to_speech", "prompt": "hi"},
    )
    assert response.status_code == 400


def test_video_task_lifecycle(client, monkeypatch, registered_model):
    asset = _upload(client)
    _mock_video_create(monkeypatch)

    response = client.post(
        "/api/tasks",
        json={
            "modelId": registered_model["id"],
            "capability": "image_to_video",
            "prompt": "角色在花田奔跑",
            "assets": [{"role": "source_image", "assetId": asset["id"]}],
        },
    )
    assert response.status_code == 202, response.text
    task = response.json()
    assert task["status"] == "running"
    assert task["externalTaskId"] == "task-1"
    task_id = task["id"]

    ctx = client.app.state.ctx
    token = repository.get_reference_token(ctx.db, task_id, asset["id"], int(time.time() * 1000))
    assert token
    reference = client.get(f"/api/reference/{token}")
    assert reference.status_code == 200
    assert reference.content == PNG

    data_uri = "data:image/png;base64," + base64.b64encode(PNG).decode()
    _mock_video_status(monkeypatch, status="completed", url=data_uri)
    polled = client.post("/api/internal/poll")
    assert polled.status_code == 200

    task = client.get(f"/api/tasks/{task_id}").json()
    assert task["status"] == "succeeded"
    assert task["resultAssetId"]
    assert any(
        item["role"] == "output" and item["asset"]["id"] == task["resultAssetId"]
        for item in task["assets"]
    ), task["assets"]
    assert client.get(f"/api/media/{task['resultAssetId']}").status_code == 200
    assert client.get(f"/api/reference/{token}").status_code == 404

    # The detail page must render the result, not the "waiting" placeholder.
    detail_html = client.get(f"/tasks/{task_id}").text
    assert "等待结果" not in detail_html
    assert f"/api/media/{task['resultAssetId']}" in detail_html
    # Parameters must keep the original text, not \uXXXX escapes.
    import re

    params_block = re.search(r"<pre>(.*?)</pre>", detail_html, re.S).group(1)
    assert "角色在花田奔跑" in params_block
    assert "\\u89d2" not in params_block


def test_failed_upstream_marks_task_failed(client, monkeypatch, registered_model):
    FakeAsyncClient.routes = {}
    monkeypatch.setattr(agnes_adapter.httpx, "AsyncClient", FakeAsyncClient)
    response = client.post(
        "/api/tasks",
        json={"modelId": registered_model["id"], "capability": "text_to_video", "prompt": "hi"},
    )
    assert response.status_code == 202
    task = response.json()
    assert task["status"] == "failed"
    assert task["error"]


def test_max_concurrency_defers_pending_task(client, monkeypatch, registered_model):
    client.patch("/api/settings/providers", json={"id": "agnes", "enabled": True, "maxConcurrency": 1})
    _mock_video_create(monkeypatch)

    first = client.post(
        "/api/tasks",
        json={"modelId": registered_model["id"], "capability": "text_to_video", "prompt": "one"},
    ).json()
    second = client.post(
        "/api/tasks",
        json={"modelId": registered_model["id"], "capability": "text_to_video", "prompt": "two"},
    ).json()
    assert first["status"] == "running"
    assert second["status"] == "pending"

    # First poll fails the running task (no status route); second submits the pending one.
    _mock_video_status(monkeypatch, status="failed", error={"message": "upstream down"})
    client.post("/api/internal/poll")
    _mock_video_create(monkeypatch, video_id="v3", task_id="t3")
    client.post("/api/internal/poll")
    second = client.get(f"/api/tasks/{second['id']}").json()
    assert second["status"] == "running"


def test_delete_task_removes_media(client, monkeypatch, registered_model):
    asset = _upload(client)
    _mock_video_create(monkeypatch)
    task = client.post(
        "/api/tasks",
        json={
            "modelId": registered_model["id"],
            "capability": "image_to_video",
            "prompt": "hi",
            "assets": [{"role": "source_image", "assetId": asset["id"]}],
        },
    ).json()
    assert task["status"] == "running"

    storage_key = repository.get_asset(client.app.state.ctx.db, asset["id"]).storage_key
    assert client.delete(f"/api/tasks/{task['id']}").status_code == 204
    assert not (client.app.state.ctx.media.path(storage_key)).exists()
    assert client.get(f"/api/media/{asset['id']}").status_code == 404


def test_retry_runs_same_task_in_place(client, monkeypatch, registered_model):
    FakeAsyncClient.routes = {}
    monkeypatch.setattr(agnes_adapter.httpx, "AsyncClient", FakeAsyncClient)
    original = client.post(
        "/api/tasks",
        json={"modelId": registered_model["id"], "capability": "text_to_video", "prompt": "hi"},
    ).json()
    assert original["status"] == "failed"
    task_id = original["id"]

    _mock_video_create(monkeypatch, video_id="v2", task_id="t2")
    response = client.post(f"/api/tasks/{task_id}/retry")
    assert response.status_code == 202, response.text
    retried = response.json()
    assert retried["id"] == task_id
    assert retried["status"] == "running"
    assert retried["externalTaskId"] == "t2"
    # 不新增任务记录
    assert client.get("/api/tasks").json()["total"] == 1
    assert client.get(f"/api/tasks/{task_id}").json()["parentTaskId"] is None


def test_image_to_image_uses_base64_without_reference_token(client, monkeypatch):
    model = _register_image_model(client)
    asset = _upload(client)
    captured: dict = {}

    async def handle(payload):
        captured["image"] = payload["extra_body"]["image"]
        data_uri = "data:image/png;base64," + base64.b64encode(PNG).decode()
        return FakeResponse({"data": [{"url": data_uri}]})

    FakeAsyncClient.routes = {("POST", f"{BASE_URL}/images/generations"): handle}
    monkeypatch.setattr(agnes_adapter.httpx, "AsyncClient", FakeAsyncClient)

    task = client.post(
        "/api/tasks",
        json={
            "modelId": model["id"],
            "capability": "image_to_image",
            "prompt": "编辑",
            "assets": [{"role": "source_image", "assetId": asset["id"]}],
        },
    ).json()
    assert task["status"] == "succeeded", task
    assert captured["image"][0].startswith("data:image/png;base64,")
    # 图片任务不需要公网参考图 token
    row = client.app.state.ctx.db.query_one(
        "SELECT COUNT(*) AS count FROM reference_tokens WHERE task_id = ?", (task["id"],)
    )
    assert row["count"] == 0


def test_concurrent_dispatch_creates_single_result(client, monkeypatch):
    model = _register_image_model(client)
    asset = _upload(client)
    data_uri = "data:image/png;base64," + base64.b64encode(PNG).decode()

    async def slow_handle(payload):
        await asyncio.sleep(0.3)
        return FakeResponse({"data": [{"url": data_uri}]})

    FakeAsyncClient.routes = {("POST", f"{BASE_URL}/images/generations"): slow_handle}
    monkeypatch.setattr(agnes_adapter.httpx, "AsyncClient", FakeAsyncClient)
    ctx = client.app.state.ctx

    async def run():
        creator = asyncio.create_task(
            tasks_service.create_task(
                ctx,
                model_id=model["id"],
                capability="image_to_image",
                prompt="编辑",
                assets=[{"role": "source_image", "assetId": asset["id"]}],
            )
        )
        await asyncio.sleep(0.05)
        await tasks_service.poll_one_task(ctx)
        return await creator

    task = asyncio.run(run())
    assert task.status == "succeeded"
    outputs = [
        link for link in repository.list_task_assets(ctx.db, task.id) if link.role == "output"
    ]
    assert len(outputs) == 1
    assert repository.count_asset_references(ctx.db, outputs[0].asset.id) == 1
