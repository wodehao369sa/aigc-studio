"""Xiaomi MiMo TTS adapter and task tests."""

from __future__ import annotations

import asyncio
import base64

from helpers import FakeAsyncClient, FakeResponse

from app.entities import ModelConfig
from app.providers.base import ProviderRuntime, TaskInput
from app.providers.xiaomi_mimo import adapter as mimo_adapter
from app.providers.xiaomi_mimo.adapter import XiaomiMiMoAdapter

BASE_URL = "https://api.xiaomimimo.com/v1"
WAV = base64.b64decode("UklGRgAAAABXQVZFZm10IBAAAA==")  # minimal wav header bytes


def _model(external_model_id: str) -> ModelConfig:
    return ModelConfig(
        id="m",
        provider_id="xiaomi_mimo",
        external_model_id=external_model_id,
        name="MiMo TTS",
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
        provider_id="xiaomi_mimo",
        base_url=BASE_URL,
        api_key="test-key",
        timeout=5,
        public_base_url=None,
        media=None,
    )


def test_validate_requires_voice_description():
    adapter = XiaomiMiMoAdapter()
    model = _model("mimo-v2.5-tts-voicedesign")
    errors = adapter.validate(
        TaskInput(prompt="Hello", parameters={}, assets=[], capability="text_to_speech"), model
    )
    assert any("音色" in error for error in errors)
    valid = adapter.validate(
        TaskInput(
            prompt="Hello",
            parameters={"voice_description": "warm and calm"},
            assets=[],
            capability="text_to_speech",
        ),
        model,
    )
    assert valid == []


def test_submit_builds_payload_and_returns_data_uri(monkeypatch):
    captured: dict = {}

    async def handle(payload):
        captured.update(payload)
        return FakeResponse({"choices": [{"message": {"audio": {"data": base64.b64encode(WAV).decode()}}}]})

    FakeAsyncClient.routes = {("POST", f"{BASE_URL}/chat/completions"): handle}
    monkeypatch.setattr(mimo_adapter.httpx, "AsyncClient", FakeAsyncClient)

    adapter = XiaomiMiMoAdapter()
    task_input = TaskInput(
        prompt="Hello there",
        parameters={"voice_description": "Warm, calm voice", "format": "wav"},
        assets=[],
        capability="text_to_speech",
    )
    ref = asyncio.run(adapter.submit(task_input, _model("mimo-v2.5-tts-voicedesign"), _runtime()))
    assert captured["model"] == "mimo-v2.5-tts-voicedesign"
    assert captured["messages"] == [
        {"role": "user", "content": "Warm, calm voice"},
        {"role": "assistant", "content": "Hello there"},
    ]
    assert captured["audio"] == {"format": "wav"}
    assert ref.result_urls == [f"data:audio/wav;base64,{base64.b64encode(WAV).decode()}"]


def test_preset_model_sets_voice(monkeypatch):
    captured: dict = {}

    async def handle(payload):
        captured.update(payload)
        return FakeResponse({"choices": [{"message": {"audio": {"data": base64.b64encode(WAV).decode()}}}]})

    FakeAsyncClient.routes = {("POST", f"{BASE_URL}/chat/completions"): handle}
    monkeypatch.setattr(mimo_adapter.httpx, "AsyncClient", FakeAsyncClient)

    adapter = XiaomiMiMoAdapter()
    task_input = TaskInput(
        prompt="你好",
        parameters={"voice": "茉莉", "format": "mp3"},
        assets=[],
        capability="text_to_speech",
    )
    asyncio.run(adapter.submit(task_input, _model("mimo-v2.5-tts"), _runtime()))
    assert captured["audio"] == {"format": "mp3", "voice": "茉莉"}
    assert captured["messages"] == [{"role": "assistant", "content": "你好"}]


def test_tts_task_creates_audio_asset(client, monkeypatch):
    created = client.post(
        "/api/settings/models",
        json={"providerId": "xiaomi_mimo", "preset": "mimo-v2.5-tts", "name": "MiMo TTS"},
    )
    assert created.status_code == 201, created.text
    model_id = created.json()["id"]

    async def handle(payload):
        return FakeResponse({"choices": [{"message": {"audio": {"data": base64.b64encode(WAV).decode()}}}]})

    FakeAsyncClient.routes = {("POST", f"{BASE_URL}/chat/completions"): handle}
    monkeypatch.setattr(mimo_adapter.httpx, "AsyncClient", FakeAsyncClient)

    task = client.post(
        "/api/tasks",
        json={
            "modelId": model_id,
            "capability": "text_to_speech",
            "prompt": "你好，世界",
            "parameters": {"voice": "mimo_default", "format": "wav"},
        },
    ).json()
    assert task["status"] == "succeeded", task

    detail = client.get(f"/api/tasks/{task['id']}").json()
    output = next(item for item in detail["assets"] if item["role"] == "output")["asset"]
    assert output["mimeType"] == "audio/wav"
    assert client.get(f"/api/media/{output['id']}").content == WAV
    page = client.get(f"/tasks/{task['id']}").text
    assert "<audio" in page
    assert "下载音频" in page
    assert "下载原图" not in page
