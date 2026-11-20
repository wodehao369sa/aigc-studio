"""Media serving and thumbnail tests."""

from __future__ import annotations

import io
import base64

from PIL import Image

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _big_png(width: int = 1200, height: int = 800) -> bytes:
    image = Image.new("RGB", (width, height), (200, 30, 30))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _upload_png(client, data: bytes, name: str = "big.png"):
    response = client.post("/api/assets", files={"file": (name, data, "image/png")})
    assert response.status_code == 201, response.text
    return response.json()


def test_thumbnail_is_generated_and_cached(client):
    asset = _upload_png(client, _big_png())
    response = client.get(f"/api/thumbnail/{asset['id']}")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/jpeg")
    image = Image.open(io.BytesIO(response.content))
    assert image.width == 480
    assert image.height == 320
    # second request is served from the cached file
    assert client.get(f"/api/thumbnail/{asset['id']}").content == response.content


def test_thumbnail_flattens_transparency_to_white(client):
    image = Image.new("RGBA", (1000, 1000), (0, 0, 0, 0))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    asset = _upload_png(client, buffer.getvalue())
    response = client.get(f"/api/thumbnail/{asset['id']}")
    assert response.status_code == 200
    thumbnail = Image.open(io.BytesIO(response.content)).convert("RGB")
    assert thumbnail.getpixel((240, 240)) == (255, 255, 255)


def test_media_serves_inline_for_viewing(client):
    asset = _upload_png(client, PNG)
    response = client.get(f"/api/media/{asset['id']}")
    assert response.status_code == 200
    assert response.headers["content-disposition"].startswith("inline")
    assert response.content == PNG


def test_thumbnail_404_for_unknown_asset(client):
    assert client.get("/api/thumbnail/does-not-exist").status_code == 404


def test_thumbnail_falls_back_for_non_image(client):
    from app.services.assets import create_result_asset

    ctx = client.app.state.ctx
    asset = create_result_asset(ctx.db, ctx.media, b"hello world", "text/markdown", "result.md")
    response = client.get(f"/api/thumbnail/{asset.id}")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.content == b"hello world"


def test_detail_page_uses_thumbnail(client, monkeypatch, registered_model):
    from helpers import FakeAsyncClient, FakeResponse

    from app.providers.agnes import adapter as agnes_adapter

    png = _big_png(1000, 500)
    asset = _upload_png(client, png)
    FakeAsyncClient.routes = {
        ("POST", "https://apihub.agnes-ai.com/v1/videos"): lambda payload: FakeResponse(
            {"video_id": "v", "task_id": "t"}
        )
    }
    monkeypatch.setattr(agnes_adapter.httpx, "AsyncClient", FakeAsyncClient)
    task = client.post(
        "/api/tasks",
        json={
            "modelId": registered_model["id"],
            "capability": "image_to_video",
            "prompt": "hi",
            "assets": [{"role": "source_image", "assetId": asset["id"]}],
        },
    ).json()
    data_uri = "data:image/png;base64," + base64.b64encode(png).decode()
    FakeAsyncClient.routes = {
        ("GET", "https://apihub.agnes-ai.com/agnesapi"): lambda params: FakeResponse(
            {"status": "completed", "url": data_uri, "progress": 100}
        )
    }
    client.post("/api/internal/poll")
    task = client.get(f"/api/tasks/{task['id']}").json()
    html = client.get(f"/tasks/{task['id']}").text
    assert f"/api/thumbnail/{task['resultAssetId']}" in html
    assert f"/api/media/{task['resultAssetId']}" in html
    assert 'class="result-thumb"' in html
    assert "查看原图" not in html
