"""Prompt enhancement tests."""

from __future__ import annotations

import base64

from helpers import FakeAsyncClient, FakeResponse

from app.providers.agnes import adapter as agnes_adapter

AGNES = "https://apihub.agnes-ai.com/v1"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _register_models(client):
    client.post(
        "/api/settings/models",
        json={"providerId": "agnes", "preset": "agnes-3.0-flash", "name": "Agnes 3.0 Flash"},
    )
    client.post(
        "/api/settings/models",
        json={"providerId": "agnes", "preset": "agnes-image-2.5-flash", "name": "Agnes Image 2.5 Flash"},
    )
    models = {item["externalModelId"]: item for item in client.get("/api/models").json()}
    return models["agnes-3.0-flash"]["id"], models["agnes-image-2.5-flash"]["id"]


def test_template_and_binding_crud(client):
    text_model, image_model = _register_models(client)
    created = client.post(
        "/api/settings/prompt-templates",
        json={"name": "插画增强", "content": "把下面的提示词扩展为细节丰富的插画描述：{{prompt}}"},
    )
    assert created.status_code == 201, created.text
    template_id = created.json()["id"]

    saved = client.put(
        f"/api/settings/models/{image_model}/prompt-templates",
        json={
            "bindings": [
                {"templateId": template_id, "enhancerModelId": text_model, "isDefault": True}
            ]
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()[0]["isDefault"] is True
    assert saved.json()[0]["templateName"] == "插画增强"

    listed = client.get(f"/api/settings/models/{image_model}/prompt-templates").json()
    assert [item["templateId"] for item in listed] == [template_id]


def test_preview_and_direct_enhancement(client, monkeypatch):
    text_model, image_model = _register_models(client)
    template_id = client.post(
        "/api/settings/prompt-templates",
        json={"name": "增强", "content": "Enhance this prompt: {{prompt}}"},
    ).json()["id"]
    client.put(
        f"/api/settings/models/{image_model}/prompt-templates",
        json={"bindings": [{"templateId": template_id, "enhancerModelId": text_model, "isDefault": True}]},
    )

    captured_text: dict = {}
    captured_image: dict = {}

    async def handle_text(payload):
        captured_text.update(payload)
        return FakeResponse({"choices": [{"message": {"content": "AN ENHANCED PROMPT"}}]})

    async def handle_image(payload):
        captured_image.update(payload)
        data_uri = "data:image/png;base64," + base64.b64encode(PNG).decode()
        return FakeResponse({"data": [{"url": data_uri}]})

    FakeAsyncClient.routes = {
        ("POST", f"{AGNES}/chat/completions"): handle_text,
        ("POST", f"{AGNES}/images/generations"): handle_image,
    }
    monkeypatch.setattr(agnes_adapter.httpx, "AsyncClient", FakeAsyncClient)

    preview = client.post(
        "/api/prompt-enhance/preview",
        json={
            "templateId": template_id,
            "enhancerModelId": text_model,
            "prompt": "a cat",
            "modelId": image_model,
            "capability": "text_to_image",
        },
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["enhancedPrompt"] == "AN ENHANCED PROMPT"
    assert "Enhance this prompt" in captured_text["messages"][-1]["content"]

    task = client.post(
        "/api/tasks",
        json={
            "modelId": image_model,
            "capability": "text_to_image",
            "prompt": "a cat",
            "originalPrompt": "a cat",
            "enhanceTemplateId": template_id,
        },
    ).json()
    assert task["status"] == "succeeded", task
    assert captured_image["prompt"] == "AN ENHANCED PROMPT"
    assert task["originalPrompt"] == "a cat"
    assert task["promptTemplateId"] == template_id
    assert task["enhancedPrompt"] == "AN ENHANCED PROMPT"


def test_preview_mode_records_template_without_server_enhance(client, monkeypatch):
    _, image_model = _register_models(client)
    template_id = "whatever"
    captured_image: dict = {}

    async def handle_image(payload):
        captured_image.update(payload)
        data_uri = "data:image/png;base64," + base64.b64encode(PNG).decode()
        return FakeResponse({"data": [{"url": data_uri}]})

    FakeAsyncClient.routes = {("POST", f"{AGNES}/images/generations"): handle_image}
    monkeypatch.setattr(agnes_adapter.httpx, "AsyncClient", FakeAsyncClient)

    task = client.post(
        "/api/tasks",
        json={
            "modelId": image_model,
            "capability": "text_to_image",
            "prompt": "already enhanced prompt",
            "originalPrompt": "raw prompt",
            "promptTemplateId": template_id,
        },
    ).json()
    assert task["status"] == "succeeded", task
    assert captured_image["prompt"] == "already enhanced prompt"
    assert task["originalPrompt"] == "raw prompt"
    assert task["promptTemplateId"] == template_id
    assert task["enhancedPrompt"] is None


def test_retry_uses_original_prompt_without_enhancement(client, monkeypatch):
    text_model, image_model = _register_models(client)
    template_id = client.post(
        "/api/settings/prompt-templates", json={"name": "t", "content": "Enhance {{prompt}}"}
    ).json()["id"]
    client.put(
        f"/api/settings/models/{image_model}/prompt-templates",
        json={"bindings": [{"templateId": template_id, "enhancerModelId": text_model, "isDefault": True}]},
    )
    data_uri = "data:image/png;base64," + base64.b64encode(PNG).decode()
    captured: dict = {}

    async def handle_text(payload):
        return FakeResponse({"choices": [{"message": {"content": "ENHANCED"}}]})

    async def handle_image(payload):
        captured.update(payload)
        return FakeResponse({"data": [{"url": data_uri}]})

    FakeAsyncClient.routes = {
        ("POST", f"{AGNES}/chat/completions"): handle_text,
        ("POST", f"{AGNES}/images/generations"): handle_image,
    }
    monkeypatch.setattr(agnes_adapter.httpx, "AsyncClient", FakeAsyncClient)

    task = client.post(
        "/api/tasks",
        json={
            "modelId": image_model,
            "capability": "text_to_image",
            "prompt": "raw",
            "originalPrompt": "raw",
            "enhanceTemplateId": template_id,
        },
    ).json()
    assert captured["prompt"] == "ENHANCED"

    tid = task["id"]
    client.app.state.ctx.db.execute(
        "UPDATE tasks SET status='failed', error='moderation' WHERE id=?", (tid,)
    )
    captured.clear()
    retried = client.post(f"/api/tasks/{tid}/retry").json()
    assert retried["status"] == "succeeded"
    assert captured["prompt"] == "raw"
    assert retried["promptTemplateId"] is None


def test_global_default_is_offered_to_unbound_models(client):
    from app.services import prompt_enhance as service

    text_model, image_model = _register_models(client)
    service.ensure_defaults(client.app.state.ctx)

    items = service.available_bindings(client.app.state.ctx, image_model, "text_to_image")
    assert any(item["source"] == "global" for item in items)

    saved = client.put(
        "/api/settings/prompt-enhance-default",
        json={"enabled": False, "templateId": None, "enhancerModelId": None},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["enabled"] is False
    items = service.available_bindings(client.app.state.ctx, image_model, "text_to_image")
    assert items == []


def test_extract_rewritten_handles_fenced_json():
    from app.services.prompt_enhance import _extract_rewritten

    assert (
        _extract_rewritten('```json\n{"rewritten_prompt": "hi", "wh_ratio": "3:2"}\n```')
        == "hi"
    )
    assert _extract_rewritten('{"rewritten_prompt": "hi"}') == "hi"
    assert _extract_rewritten("plain text") == "plain text"


def test_as_system_template_still_renders_placeholders(client, monkeypatch):
    text_model, image_model = _register_models(client)
    template_id = client.post(
        "/api/settings/prompt-templates",
        json={"name": "sys", "content": "SYS {{prompt}} | {{model}} | {{capability}}", "asSystem": True},
    ).json()["id"]
    captured: dict = {}

    async def handle(payload):
        captured.update(payload)
        return FakeResponse({"choices": [{"message": {"content": "ok"}}]})

    FakeAsyncClient.routes = {("POST", f"{AGNES}/chat/completions"): handle}
    monkeypatch.setattr(agnes_adapter.httpx, "AsyncClient", FakeAsyncClient)

    preview = client.post(
        "/api/prompt-enhance/preview",
        json={
            "templateId": template_id,
            "enhancerModelId": text_model,
            "prompt": "hi",
            "modelId": image_model,
            "capability": "text_to_image",
        },
    )
    assert preview.status_code == 200, preview.text
    roles = {message["role"]: message["content"] for message in captured["messages"]}
    assert roles["system"] == "SYS hi | Agnes Image 2.5 Flash | 文生图"
    assert roles["user"] == "hi"


def test_ensure_defaults_seeds_qwen_templates(client):
    from app.services.prompt_enhance import ensure_defaults

    _register_models(client)
    qwen = client.post(
        "/api/settings/models",
        json={"providerId": "modelscope", "preset": "Qwen/Qwen-Image-2.1", "name": "Qwen Image 2.1"},
    )
    assert qwen.status_code == 201, qwen.text
    model_id = qwen.json()["id"]

    ensure_defaults(client.app.state.ctx)
    templates = client.get("/api/settings/prompt-templates").json()
    assert any("Qwen-Image-2.1" in item["name"] for item in templates)
    bindings = client.get(f"/api/settings/models/{model_id}/prompt-templates").json()
    assert {item["capability"] for item in bindings} == {"text_to_image", "image_to_image"}
    assert all(item["isDefault"] for item in bindings)

    # idempotent
    ensure_defaults(client.app.state.ctx)
    assert len(client.get("/api/settings/prompt-templates").json()) == len(templates)
