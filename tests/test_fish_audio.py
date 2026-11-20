"""Fish Audio TTS adapter and task tests."""

from __future__ import annotations

import asyncio
import base64

from helpers import FakeAsyncClient, FakeResponse

from app.entities import ModelConfig
from app.providers.base import ProviderRuntime, TaskInput
from app.providers.fish_audio import adapter as fish_adapter
from app.providers.fish_audio.adapter import FishAudioAdapter

BASE_URL = "https://api.fish.audio/v1"
AUDIO = b"ID3fake-mp3-bytes"


def _model() -> ModelConfig:
    return ModelConfig(
        id="m",
        provider_id="fish_audio",
        external_model_id="s2.1-pro-free",
        name="Fish Audio S2.1 Pro (Free)",
        version=None,
        description=None,
        capabilities=["text_to_speech"],
        parameter_schema=[],
        input_constraints={},
        enabled=True,
        sort_order=0,
    )


def _runtime() -> ProviderRuntime:
    return ProviderRuntime(
        provider_id="fish_audio",
        base_url=BASE_URL,
        api_key="test-key",
        timeout=5,
        public_base_url=None,
        media=None,
    )


def test_validate_requires_text():
    adapter = FishAudioAdapter()
    assert adapter.validate(
        TaskInput(prompt="  ", parameters={}, assets=[], capability="text_to_speech"), _model()
    )
    assert adapter.validate(
        TaskInput(prompt="你好", parameters={}, assets=[], capability="text_to_speech"), _model()
    ) == []


def test_submit_posts_to_tts_and_returns_data_uri(monkeypatch):
    captured: dict = {}

    async def handle(payload):
        captured.update(payload)
        return FakeResponse({"ignored": True}, content=AUDIO, headers={"content-type": "audio/mpeg"})

    FakeAsyncClient.routes = {("POST", f"{BASE_URL}/tts"): handle}
    monkeypatch.setattr(fish_adapter.httpx, "AsyncClient", FakeAsyncClient)

    adapter = FishAudioAdapter()
    task_input = TaskInput(
        prompt="你好，世界",
        parameters={"format": "mp3", "latency": "balanced", "seed": 7},
        assets=[],
        capability="text_to_speech",
    )
    ref = asyncio.run(adapter.submit(task_input, _model(), _runtime()))
    assert captured["text"] == "你好，世界"
    assert captured["format"] == "mp3"
    assert captured["latency"] == "balanced"
    assert captured["seed"] == 7
    assert ref.result_urls == [f"data:audio/mpeg;base64,{base64.b64encode(AUDIO).decode()}"]


def test_tts_task_creates_audio_asset(client, monkeypatch):
    created = client.post(
        "/api/settings/models",
        json={"providerId": "fish_audio", "preset": "s2.1-pro-free", "name": "Fish Audio S2.1 Pro (Free)"},
    )
    assert created.status_code == 201, created.text
    model_id = created.json()["id"]

    async def handle(payload):
        return FakeResponse({"ignored": True}, content=AUDIO, headers={"content-type": "audio/mpeg"})

    FakeAsyncClient.routes = {("POST", f"{BASE_URL}/tts"): handle}
    monkeypatch.setattr(fish_adapter.httpx, "AsyncClient", FakeAsyncClient)

    task = client.post(
        "/api/tasks",
        json={
            "modelId": model_id,
            "capability": "text_to_speech",
            "prompt": "你好，世界",
            "parameters": {"format": "mp3"},
        },
    ).json()
    assert task["status"] == "succeeded", task
    detail = client.get(f"/api/tasks/{task['id']}").json()
    output = next(item for item in detail["assets"] if item["role"] == "output")["asset"]
    assert output["mimeType"] == "audio/mpeg"
    assert client.get(f"/api/media/{output['id']}").content == AUDIO
    assert "下载音频" in client.get(f"/tasks/{task['id']}").text
