"""Agnes adapter tests with a mocked upstream HTTP layer."""

from __future__ import annotations

import asyncio
import base64
from pathlib import Path

import pytest

from app.entities import ModelConfig
from app.providers.agnes import adapter as agnes_adapter
from app.providers.agnes.adapter import AgnesAdapter
from app.providers.base import AssetInput, ProviderRuntime, TaskInput
from app.services.media import MediaService
from helpers import FakeAsyncClient, FakeResponse

BASE_URL = "https://apihub.agnes-ai.com/v1"


@pytest.fixture()
def runtime(tmp_path: Path):
    media = MediaService(tmp_path / "media")
    media.ensure_root()
    return ProviderRuntime(
        provider_id="agnes",
        base_url=BASE_URL,
        api_key="test-key",
        timeout=5,
        public_base_url="https://public.example.com",
        media=media,
    )


@pytest.fixture()
def video_model():
    return ModelConfig(
        id="model-video",
        provider_id="agnes",
        external_model_id="agnes-video-2.5-flash",
        name="Agnes Video 2.5 Flash",
        version=None,
        description=None,
        capabilities=["text_to_video", "image_to_video", "keyframe_video", "reference_video"],
        parameter_schema=[],
        input_constraints={},
        enabled=True,
        sort_order=0,
    )


def _video_input(**overrides) -> TaskInput:
    data = {
        "prompt": "一只猫在森林里走路",
        "parameters": {"seconds": 5, "aspect_ratio": "16:9"},
        "assets": [],
        "capability": "text_to_video",
    }
    data.update(overrides)
    return TaskInput(**data)


def test_video_validation_rules():
    adapter = AgnesAdapter(None)  # type: ignore[arg-type]
    model = ModelConfig(
        id="m", provider_id="agnes", external_model_id="agnes-video-2.5-flash", name="v",
        version=None, description=None, capabilities=[], parameter_schema=[],
        input_constraints={}, enabled=True, sort_order=0,
    )
    assert adapter.validate(_video_input(prompt=""), model)  # prompt required
    assert adapter.validate(_video_input(parameters={"seconds": 3}), model)  # too short
    assert adapter.validate(_video_input(parameters={"seconds": 13}), model)  # too long
    assert adapter.validate(_video_input(parameters={"aspect_ratio": "2:1"}), model)  # bad ratio
    keyframe = _video_input(capability="keyframe_video")
    assert any("首尾帧" in error for error in adapter.validate(keyframe, model))
    reference = _video_input(capability="reference_video")
    assert any("参考图" in error for error in adapter.validate(reference, model))
    text_with_image = _video_input(assets=[AssetInput("source_image", "a", "k", "image/png")])
    assert any("文生视频" in error for error in adapter.validate(text_with_image, model))


def test_image_validation_rules():
    adapter = AgnesAdapter(None)  # type: ignore[arg-type]
    model = ModelConfig(
        id="m", provider_id="agnes", external_model_id="agnes-image-2.5-flash", name="i",
        version=None, description=None, capabilities=[], parameter_schema=[],
        input_constraints={}, enabled=True, sort_order=0,
    )
    good = TaskInput(prompt="hi", parameters={"size": "2K", "ratio": "16:9"}, assets=[], capability="text_to_image")
    assert adapter.validate(good, model) == []
    assert adapter.validate(TaskInput(prompt="hi", parameters={"size": "9K"}, assets=[], capability="text_to_image"), model)
    img2img = TaskInput(prompt="hi", parameters={}, assets=[], capability="image_to_image")
    assert any("源图片" in error for error in adapter.validate(img2img, model))


def test_text_submit_parses_content(monkeypatch, runtime, video_model):
    video_model.external_model_id = "agnes-3.0-flash"
    video_model.capabilities = ["text_generation"]

    def handle(payload):
        assert payload["model"] == "agnes-3.0-flash"
        assert payload["messages"][-1]["content"] == "你好"
        assert payload["max_tokens"] == 64
        return FakeResponse({"choices": [{"message": {"content": "你好，世界"}}]})

    FakeAsyncClient.routes = {("POST", f"{BASE_URL}/chat/completions"): handle}
    monkeypatch.setattr(agnes_adapter.httpx, "AsyncClient", FakeAsyncClient)
    adapter = AgnesAdapter(runtime)
    task_input = TaskInput(prompt="你好", parameters={"max_tokens": 64}, assets=[], capability="text_generation")
    ref = asyncio.run(adapter.submit(task_input, video_model, runtime))
    assert ref.result_text == "你好，世界"


def test_image_submit_builds_extra_body(monkeypatch, runtime, video_model):
    video_model.external_model_id = "agnes-image-2.5-flash"
    video_model.capabilities = ["image_to_image"]

    def handle(payload):
        assert payload["extra_body"]["image"] == ["https://public.example.com/ref.png"]
        assert payload["extra_body"]["response_format"] == "url"
        return FakeResponse({"data": [{"url": "https://cdn.example.com/out.png"}]})

    FakeAsyncClient.routes = {("POST", f"{BASE_URL}/images/generations"): handle}
    monkeypatch.setattr(agnes_adapter.httpx, "AsyncClient", FakeAsyncClient)
    adapter = AgnesAdapter(runtime)
    task_input = TaskInput(
        prompt="edit",
        parameters={"size": "1K", "ratio": "1:1"},
        assets=[AssetInput("source_image", "a", "k", "image/png", public_url="https://public.example.com/ref.png")],
        capability="image_to_image",
    )
    ref = asyncio.run(adapter.submit(task_input, video_model, runtime))
    assert ref.result_urls == ["https://cdn.example.com/out.png"]


def test_video_submit_and_status(monkeypatch, runtime, video_model):
    def create(payload):
        assert payload["mode"] == "keyframe"
        assert payload["size"] == "720P"
        assert payload["first_frame"] == "https://public.example.com/first.png"
        return FakeResponse({"video_id": "vid-1", "task_id": "task-1"})

    states = {"status": "running", "progress": 40}

    def status(params):
        return FakeResponse(states)

    FakeAsyncClient.routes = {
        ("POST", f"{BASE_URL}/videos"): create,
        ("GET", "https://apihub.agnes-ai.com/agnesapi"): status,
    }
    monkeypatch.setattr(agnes_adapter.httpx, "AsyncClient", FakeAsyncClient)
    adapter = AgnesAdapter(runtime)
    task_input = _video_input(
        capability="keyframe_video",
        assets=[AssetInput("first_frame", "a", "k", "image/png", public_url="https://public.example.com/first.png")],
    )
    ref = asyncio.run(adapter.submit(task_input, video_model, runtime))
    assert ref.external_video_id == "vid-1"
    assert ref.external_task_id == "task-1"

    result = asyncio.run(adapter.get_status(ref, video_model, runtime))
    assert result.status == "running"
    assert result.progress == 40

    states.update({"status": "completed", "url": "https://cdn.example.com/video.mp4", "progress": 100})
    result = asyncio.run(adapter.get_status(ref, video_model, runtime))
    assert result.status == "succeeded"
    assert result.result_urls == ["https://cdn.example.com/video.mp4"]

    states.update({"status": "failed", "error": {"message": "boom"}})
    result = asyncio.run(adapter.get_status(ref, video_model, runtime))
    assert result.status == "failed"
    assert result.error == "boom"


def test_image_data_uri_fallback(monkeypatch, tmp_path, runtime, video_model):
    video_model.external_model_id = "agnes-image-2.5-flash"
    video_model.capabilities = ["image_to_image"]
    payload = b"\x89PNG\r\n\x1a\nfake"
    key = runtime.media.write_bytes(payload, ".png")

    def handle(body):
        image = body["extra_body"]["image"][0]
        assert image.startswith("data:image/png;base64,")
        return FakeResponse({"data": [{"b64_json": base64.b64encode(payload).decode()}]})

    FakeAsyncClient.routes = {("POST", f"{BASE_URL}/images/generations"): handle}
    monkeypatch.setattr(agnes_adapter.httpx, "AsyncClient", FakeAsyncClient)
    adapter = AgnesAdapter(runtime)
    task_input = TaskInput(
        prompt="edit",
        parameters={},
        assets=[AssetInput("source_image", "a", key, "image/png")],
        capability="image_to_image",
    )
    ref = asyncio.run(adapter.submit(task_input, video_model, runtime))
    assert ref.result_urls and ref.result_urls[0].startswith("data:image/png;base64,")
