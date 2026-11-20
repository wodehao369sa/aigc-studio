"""Favorites, tags and gallery tests."""

from __future__ import annotations

import base64

from helpers import FakeAsyncClient, FakeResponse

from app.providers.agnes import adapter as agnes_adapter

BASE_URL = "https://apihub.agnes-ai.com/v1"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _succeeded_image_task(client, monkeypatch):
    client.post(
        "/api/settings/models",
        json={"providerId": "agnes", "preset": "agnes-image-2.5-flash", "name": "Agnes Image 2.5 Flash"},
    )
    model = next(
        item
        for item in client.get("/api/models").json()
        if item["externalModelId"] == "agnes-image-2.5-flash"
    )
    data_uri = "data:image/png;base64," + base64.b64encode(PNG).decode()

    async def handle(payload):
        return FakeResponse({"data": [{"url": data_uri}]})

    FakeAsyncClient.routes = {("POST", f"{BASE_URL}/images/generations"): handle}
    monkeypatch.setattr(agnes_adapter.httpx, "AsyncClient", FakeAsyncClient)
    task = client.post(
        "/api/tasks",
        json={"modelId": model["id"], "capability": "text_to_image", "prompt": "一只猫"},
    ).json()
    assert task["status"] == "succeeded", task
    return task


def test_favorite_toggle_and_tags(client, monkeypatch):
    task = _succeeded_image_task(client, monkeypatch)
    task_id = task["id"]

    favorited = client.patch(f"/api/tasks/{task_id}", json={"favorite": True})
    assert favorited.status_code == 200
    assert favorited.json()["isFavorite"] is True
    assert favorited.json()["favoritedAt"] is not None

    tagged = client.patch(f"/api/tasks/{task_id}", json={"tags": ["猫", "测试", "猫"]})
    assert tagged.status_code == 200
    assert tagged.json()["tags"] == ["测试", "猫"]

    listed = client.get("/api/tasks", params={"favorite": "true"}).json()
    assert any(item["id"] == task_id for item in listed["items"])
    assert all(item["isFavorite"] for item in listed["items"])

    by_tag = client.get("/api/tasks", params={"favorite": "true", "tag": "猫"}).json()
    assert [item["id"] for item in by_tag["items"]] == [task_id]
    assert by_tag["items"][0]["tags"] == ["测试", "猫"]

    tags = client.get("/api/tags").json()
    assert {item["name"]: item["count"] for item in tags} == {"测试": 1, "猫": 1}

    unfavorited = client.patch(f"/api/tasks/{task_id}", json={"favorite": False})
    assert unfavorited.json()["isFavorite"] is False
    assert client.get("/api/tasks", params={"favorite": "true"}).json()["total"] == 0


def test_gallery_page(client, monkeypatch):
    task = _succeeded_image_task(client, monkeypatch)
    client.patch(f"/api/tasks/{task['id']}", json={"favorite": True, "tags": ["画廊"]})
    page = client.get("/gallery")
    assert page.status_code == 200
    assert "一只猫" in page.text
    assert "画廊" in page.text
    filtered = client.get("/gallery", params={"tag": "画廊"})
    assert filtered.status_code == 200
    assert "一只猫" in filtered.text


def test_gallery_tag_counts_are_favorite_scoped(client, monkeypatch):
    first = _succeeded_image_task(client, monkeypatch)
    second = _succeeded_image_task(client, monkeypatch)
    client.patch(f"/api/tasks/{first['id']}", json={"favorite": True, "tags": ["X"]})
    client.patch(f"/api/tasks/{second['id']}", json={"tags": ["Y"]})

    html = client.get("/gallery").text
    assert "全部（1）" in html
    assert "X（1）" in html
    assert "Y（" not in html
