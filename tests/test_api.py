"""Settings and read API tests."""

from __future__ import annotations

import base64

import pytest


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["database"] == "ok"


def test_presets_expose_three_agnes_models(client):
    presets = client.get("/api/settings/presets").json()
    agnes = next(item for item in presets if item["providerId"] == "agnes")
    assert [model["externalModelId"] for model in agnes["models"]] == [
        "agnes-3.0-flash",
        "agnes-image-2.5-flash",
        "agnes-video-2.5-flash",
    ]


def test_model_crud_from_preset(client):
    created = client.post(
        "/api/settings/models",
        json={"providerId": "agnes", "preset": "agnes-3.0-flash", "name": "Agnes 3.0 Flash"},
    )
    assert created.status_code == 201, created.text
    model_id = created.json()["id"]
    models = client.get("/api/settings/models").json()
    model = next(item for item in models if item["id"] == model_id)
    assert model["externalModelId"] == "agnes-3.0-flash"
    assert model["capabilities"] == ["text_generation"]
    assert model["parameterSchema"]

    disabled = client.patch(
        "/api/settings/models",
        json={
            "id": model_id,
            "providerId": "agnes",
            "name": "Agnes 3.0 Flash",
            "capabilities": ["text_generation"],
            "parameterSchema": model["parameterSchema"],
            "enabled": False,
            "sortOrder": 3,
        },
    )
    assert disabled.status_code == 200
    assert client.get("/api/models").json() == [] or all(
        item["id"] != model_id for item in client.get("/api/models").json()
    )

    assert client.delete(f"/api/settings/models?id={model_id}").status_code == 200
    assert all(item["id"] != model_id for item in client.get("/api/settings/models").json())


def test_model_capability_validation(client):
    response = client.post(
        "/api/settings/models",
        json={
            "providerId": "agnes",
            "name": "Bad",
            "externalModelId": "x",
            "capabilities": ["text_to_speech"],
        },
    )
    assert response.status_code == 400
    assert "不支持" in response.json()["detail"]


def test_provider_reload(client):
    providers = client.get("/api/settings/providers").json()
    assert [item["id"] for item in providers] == [
        "agnes",
        "breeze",
        "fish_audio",
        "modelscope",
        "openai_compatible",
        "xiaomi_mimo",
    ]
    assert all(item["configured"] for item in providers)
    reloaded = client.post("/api/settings/providers/reload")
    assert reloaded.status_code == 200


def test_task_list_filters(client):
    response = client.get("/api/tasks?status=succeeded&capability=text_to_image")
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert client.get("/api/tasks?status=bogus").status_code == 400


def test_task_list_empty_filter(client):
    assert client.get("/tasks", params={"status": "", "capability": ""}).status_code == 200
    assert client.get("/api/tasks", params={"status": "", "capability": ""}).status_code == 200
