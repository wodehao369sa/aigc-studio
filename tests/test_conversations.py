"""Multi-turn conversation tests."""

from __future__ import annotations

from helpers import FakeAsyncClient, FakeResponse

from app.providers.agnes import adapter as agnes_adapter

BASE_URL = "https://apihub.agnes-ai.com/v1"


def _register_text_model(client):
    client.post(
        "/api/settings/models",
        json={"providerId": "agnes", "preset": "agnes-3.0-flash", "name": "Agnes 3.0 Flash"},
    )
    return next(
        model
        for model in client.get("/api/models").json()
        if model["externalModelId"] == "agnes-3.0-flash"
    )


def test_conversation_multi_turn(client, monkeypatch):
    model = _register_text_model(client)
    captured: list[list[str]] = []

    def handle(payload):
        captured.append([message["role"] for message in payload["messages"]])
        return FakeResponse({"choices": [{"message": {"content": "回复内容"}}]})

    FakeAsyncClient.routes = {("POST", f"{BASE_URL}/chat/completions"): handle}
    monkeypatch.setattr(agnes_adapter.httpx, "AsyncClient", FakeAsyncClient)

    conversation = client.post(
        "/api/conversations",
        json={"modelId": model["id"], "systemPrompt": "你是助手"},
    ).json()
    assert conversation["title"]
    assert client.get(f"/conversations/{conversation['id']}").status_code == 200

    first = client.post(
        f"/api/conversations/{conversation['id']}/messages", json={"prompt": "你好"}
    )
    assert first.status_code == 202, first.text
    assert first.json()["status"] == "succeeded"
    assert captured[-1] == ["system", "user"]

    second = client.post(
        f"/api/conversations/{conversation['id']}/messages", json={"prompt": "再说一句"}
    )
    assert second.status_code == 202, second.text
    assert captured[-1] == ["system", "user", "assistant", "user"]

    detail = client.get(f"/api/conversations/{conversation['id']}").json()
    assert [message["role"] for message in detail["messages"]] == [
        "system",
        "user",
        "assistant",
        "user",
        "assistant",
    ]

    listed = client.get("/api/conversations").json()
    assert any(item["id"] == conversation["id"] for item in listed)

    assert client.delete(f"/api/conversations/{conversation['id']}").status_code == 204
    assert client.get(f"/api/conversations/{conversation['id']}").status_code == 404


def test_conversation_requires_text_model(client):
    response = client.post(
        "/api/conversations",
        json={"modelId": "missing", "title": "x"},
    )
    assert response.status_code == 400


def test_conversation_tasks_excluded_from_task_list(client, monkeypatch):
    model = _register_text_model(client)
    captured = []

    def handle(payload):
        captured.append(payload)
        return FakeResponse({"choices": [{"message": {"content": "好的"}}]})

    FakeAsyncClient.routes = {("POST", f"{BASE_URL}/chat/completions"): handle}
    monkeypatch.setattr(agnes_adapter.httpx, "AsyncClient", FakeAsyncClient)

    conversation = client.post("/api/conversations", json={"modelId": model["id"]}).json()
    task = client.post(
        f"/api/conversations/{conversation['id']}/messages", json={"prompt": "你好"}
    ).json()
    assert task["conversationId"] == conversation["id"]

    listed = client.get("/api/tasks").json()
    assert all(item["id"] != task["id"] for item in listed["items"])
    # 任务详情仍可访问
    assert client.get(f"/api/tasks/{task['id']}").status_code == 200
