"""Breeze TTS adapter and task tests."""

from __future__ import annotations

import asyncio
import base64

from helpers import FakeAsyncClient, FakeResponse

from app.entities import ModelConfig
from app.providers.base import ProviderRuntime, TaskInput
from app.providers.breeze import adapter as breeze_adapter
from app.providers.breeze.adapter import BreezeAdapter

BASE_URL = "https://api.breeze.blue/v1"
AUDIO = b"fake-audio-bytes"


def _model(external_model_id: str = "breeze-tts-2") -> ModelConfig:
    return ModelConfig(
        id="m",
        provider_id="breeze",
        external_model_id=external_model_id,
        name="Breeze TTS 2",
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
        provider_id="breeze",
        base_url=BASE_URL,
        api_key="test-key",
        timeout=5,
        public_base_url=None,
        media=None,
    )


def test_validate_requires_voice_and_text():
    adapter = BreezeAdapter()
    model = _model()
    assert adapter.validate(
        TaskInput(prompt="你好", parameters={}, assets=[], capability="text_to_speech"), model
    )
    assert adapter.validate(
        TaskInput(
            prompt="你好",
            parameters={"voice_id": "voc_123"},
            assets=[],
            capability="text_to_speech",
        ),
        model,
    ) == []
    assert adapter.validate(
        TaskInput(
            prompt="你好",
            parameters={"voice_id": "voc_123", "speed": 3},
            assets=[],
            capability="text_to_speech",
        ),
        model,
    )


def test_submit_builds_request(monkeypatch):
    captured: dict = {}

    async def handle(payload):
        captured.update(payload)
        return FakeResponse({"ignored": True}, content=AUDIO, headers={"content-type": "audio/mpeg"})

    FakeAsyncClient.routes = {
        ("POST", f"{BASE_URL}/text-to-speech/voc_123"): handle,
    }
    monkeypatch.setattr(breeze_adapter.httpx, "AsyncClient", FakeAsyncClient)

    adapter = BreezeAdapter()
    task_input = TaskInput(
        prompt="你好，世界",
        parameters={
            "voice_id": "voc_123",
            "language_code": "zh",
            "instructions": "温柔一点",
            "output_format": "wav",
            "guidance_scale": 4,
            "speed": 1.2,
            "volume": 0.9,
        },
        assets=[],
        capability="text_to_speech",
    )
    ref = asyncio.run(adapter.submit(task_input, _model(), _runtime()))
    assert captured["text"] == "你好，世界"
    assert captured["model_id"] == "breeze-tts-2"
    assert captured["language_code"] == "zh"
    assert captured["instructions"] == "温柔一点"
    assert captured["voice_settings"] == {
        "guidance_scale": 4.0,
        "speed": 1.2,
        "volume": 0.9,
    }
    assert ref.result_urls == [f"data:audio/mpeg;base64,{base64.b64encode(AUDIO).decode()}"]


def test_tts_task_creates_audio_asset(client, monkeypatch):
    created = client.post(
        "/api/settings/models",
        json={"providerId": "breeze", "preset": "breeze-tts-2", "name": "Breeze TTS 2"},
    )
    assert created.status_code == 201, created.text
    model_id = created.json()["id"]

    async def handle(payload):
        return FakeResponse({"ignored": True}, content=AUDIO, headers={"content-type": "audio/wav"})

    FakeAsyncClient.routes = {
        ("POST", f"{BASE_URL}/text-to-speech/voc_abc"): handle,
    }
    monkeypatch.setattr(breeze_adapter.httpx, "AsyncClient", FakeAsyncClient)

    task = client.post(
        "/api/tasks",
        json={
            "modelId": model_id,
            "capability": "text_to_speech",
            "prompt": "你好，世界",
            "parameters": {"voice_id": "voc_abc", "output_format": "wav"},
        },
    ).json()
    assert task["status"] == "succeeded", task
    detail = client.get(f"/api/tasks/{task['id']}").json()
    output = next(item for item in detail["assets"] if item["role"] == "output")["asset"]
    assert output["mimeType"] == "audio/wav"
    assert client.get(f"/api/media/{output['id']}").content == AUDIO
    assert "下载音频" in client.get(f"/tasks/{task['id']}").text


VOICE_LIST = {
    "voices": [
        {
            "voice_id": "voc_1",
            "name": "Alice",
            "language_code": "en",
            "gender": "female",
            "age": "young",
            "accent": "american",
            "description": None,
            "preview_url": None,
        }
    ],
    "total": 1,
    "page": 1,
    "page_size": 50,
    "has_more": False,
}


def test_list_voices(monkeypatch):
    async def handle(params):
        return FakeResponse(VOICE_LIST)

    FakeAsyncClient.routes = {("GET", f"{BASE_URL}/voices"): handle}
    monkeypatch.setattr(breeze_adapter.httpx, "AsyncClient", FakeAsyncClient)

    result = asyncio.run(BreezeAdapter().list_voices(_runtime(), page=1, page_size=50))
    assert result["total"] == 1
    assert result["voices"][0]["voiceId"] == "voc_1"
    assert result["voices"][0]["name"] == "Alice"
    assert result["voices"][0]["languageCode"] == "en"


def test_voices_api(client, monkeypatch):
    async def handle(params):
        return FakeResponse(VOICE_LIST)

    FakeAsyncClient.routes = {("GET", f"{BASE_URL}/voices"): handle}
    monkeypatch.setattr(breeze_adapter.httpx, "AsyncClient", FakeAsyncClient)

    response = client.get("/api/voices", params={"provider": "breeze"})
    assert response.status_code == 200, response.text
    assert response.json()["voices"][0]["voiceId"] == "voc_1"

    missing = client.get("/api/voices", params={"provider": "agnes"})
    assert missing.status_code == 400
