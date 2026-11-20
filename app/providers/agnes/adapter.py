"""Agnes AI adapter: request mapping, validation and status normalization.

Upstream docs:
- text:   POST /v1/chat/completions
- image:  POST /v1/images/generations
- video:  POST /v1/videos  +  GET /agnesapi?video_id=...&model_name=...
"""

from __future__ import annotations

import base64
import re
from urllib.parse import urlparse

import httpx

from ..base import (
    ProviderAdapter,
    ProviderError,
    ProviderRuntime,
    ProviderStatus,
    ProviderTaskRef,
    TaskInput,
)
from ...entities import ModelConfig

TEXT_CAPABILITY = "text_generation"
IMAGE_CAPABILITIES = ("text_to_image", "image_to_image")
VIDEO_CAPABILITIES = ("text_to_video", "image_to_video", "keyframe_video", "reference_video")

IMAGE_SIZES = ("1K", "2K", "3K", "4K")
IMAGE_RATIOS = ("1:1", "3:4", "4:3", "16:9", "9:16", "2:3", "3:2", "21:9")
VIDEO_RATIOS = ("21:9", "16:9", "4:3", "1:1", "3:4", "9:16")
VIDEO_MODE_BY_CAPABILITY = {
    "text_to_video": "text",
    "image_to_video": "reference",
    "keyframe_video": "keyframe",
    "reference_video": "reference",
}
MAX_VIDEO_REFERENCE_IMAGES = 5


class AgnesAdapter(ProviderAdapter):
    provider_id = "agnes"

    def __init__(self, runtime: ProviderRuntime) -> None:
        self.runtime = runtime

    # --- validation ---------------------------------------------------------

    def validate(self, task_input: TaskInput, model: ModelConfig) -> list[str]:
        capability = task_input.capability
        if capability == TEXT_CAPABILITY:
            return self._validate_text(task_input)
        if capability in IMAGE_CAPABILITIES:
            return self._validate_image(task_input)
        if capability in VIDEO_CAPABILITIES:
            return self._validate_video(task_input)
        return ["不支持的能力。"]

    def _validate_text(self, task_input: TaskInput) -> list[str]:
        errors: list[str] = []
        if not task_input.prompt.strip():
            errors.append("请输入提示词。")
        errors.extend(_number_errors(task_input.parameters, "max_tokens", 1, 65536))
        errors.extend(_number_errors(task_input.parameters, "temperature", 0, 2))
        return errors

    def _validate_image(self, task_input: TaskInput) -> list[str]:
        errors: list[str] = []
        parameters = task_input.parameters
        if not task_input.prompt.strip():
            errors.append("请输入提示词。")
        size = str(parameters.get("size", "1K"))
        if size not in IMAGE_SIZES and not _PRECISE_SIZE.match(size):
            errors.append("请选择有效图片尺寸。")
        if str(parameters.get("ratio", "1:1")) not in IMAGE_RATIOS:
            errors.append("请选择有效宽高比。")
        has_source = any(asset.role in ("source_image", "reference_image") for asset in task_input.assets)
        if task_input.capability == "image_to_image" and not has_source:
            errors.append("图生图需要上传源图片。")
        if task_input.capability == "text_to_image" and has_source:
            errors.append("文生图不能携带参考图片。")
        if has_source and len(task_input.assets) > 8:
            errors.append("参考图片最多 8 张。")
        return errors

    def _validate_video(self, task_input: TaskInput) -> list[str]:
        errors: list[str] = []
        parameters = task_input.parameters
        capability = task_input.capability
        if not task_input.prompt.strip():
            errors.append("请输入提示词。")

        seconds = parameters.get("seconds", 5)
        if not _is_int(seconds) or not 4 <= int(seconds) <= 12:
            errors.append("视频时长必须为 4 到 12 秒。")
        if str(parameters.get("aspect_ratio", "16:9")) not in VIDEO_RATIOS:
            errors.append("请选择有效画幅。")

        first = any(asset.role == "first_frame" for asset in task_input.assets)
        last = any(asset.role == "last_frame" for asset in task_input.assets)
        references = [
            asset for asset in task_input.assets if asset.role in ("source_image", "reference_image")
        ]
        mode = VIDEO_MODE_BY_CAPABILITY[capability]
        if mode == "keyframe" and not (first or last):
            errors.append("首尾帧模式至少需要一张图片。")
        if mode == "reference" and not references:
            errors.append("图片参考模式需要上传参考图。")
        if mode == "text" and (first or last or references):
            errors.append("文生视频不能携带参考图片。")
        if references and len(references) > MAX_VIDEO_REFERENCE_IMAGES:
            errors.append("参考图片最多 5 张。")
        return errors

    # --- submission ---------------------------------------------------------

    async def submit(self, task_input: TaskInput, model: ModelConfig, runtime: ProviderRuntime) -> ProviderTaskRef:
        capability = task_input.capability
        if capability == TEXT_CAPABILITY:
            return await self._submit_text(task_input, model)
        if capability in IMAGE_CAPABILITIES:
            return await self._submit_image(task_input, model)
        if capability in VIDEO_CAPABILITIES:
            return await self._submit_video(task_input, model)
        raise ProviderError(f"不支持的能力：{capability}")

    async def _submit_text(self, task_input: TaskInput, model: ModelConfig) -> ProviderTaskRef:
        if task_input.messages:
            messages = [dict(message) for message in task_input.messages]
        else:
            messages = []
            system_prompt = task_input.parameters.get("system_prompt")
            if system_prompt:
                messages.append({"role": "system", "content": str(system_prompt)})
            messages.append({"role": "user", "content": task_input.prompt})
        payload: dict = {"model": model.external_model_id, "messages": messages}
        max_tokens = task_input.parameters.get("max_tokens")
        if max_tokens is not None:
            payload["max_tokens"] = int(max_tokens)
        temperature = task_input.parameters.get("temperature")
        if temperature is not None:
            payload["temperature"] = float(temperature)

        data = await self._post("/chat/completions", payload)
        choices = data.get("choices") or []
        content = None
        if choices:
            message = choices[0].get("message") or {}
            content = message.get("content")
        if not content:
            raise ProviderError("Agnes 文本接口未返回结果。")
        return ProviderTaskRef(result_text=str(content))

    async def _submit_image(self, task_input: TaskInput, model: ModelConfig) -> ProviderTaskRef:
        parameters = task_input.parameters
        payload: dict = {
            "model": model.external_model_id,
            "prompt": task_input.prompt,
            "size": str(parameters.get("size", "1K")),
            "ratio": str(parameters.get("ratio", "1:1")),
            "extra_body": {"response_format": "url"},
        }
        if task_input.capability == "image_to_image":
            images = self._resolve_images(task_input, ("source_image", "reference_image"))
            payload["extra_body"]["image"] = images

        data = await self._post("/images/generations", payload)
        urls: list[str] = []
        for item in data.get("data") or []:
            if item.get("url"):
                urls.append(str(item["url"]))
            elif item.get("b64_json"):
                urls.append(f"data:image/png;base64,{item['b64_json']}")
        if not urls:
            raise ProviderError("Agnes 图片接口未返回结果。")
        return ProviderTaskRef(result_urls=urls)

    async def _submit_video(self, task_input: TaskInput, model: ModelConfig) -> ProviderTaskRef:
        parameters = task_input.parameters
        mode = VIDEO_MODE_BY_CAPABILITY[task_input.capability]
        payload: dict = {
            "model": model.external_model_id,
            "prompt": task_input.prompt,
            "mode": mode,
            "seconds": str(parameters.get("seconds", 5)),
            "size": "720P",
            "aspect_ratio": str(parameters.get("aspect_ratio", "16:9")),
            "n": 1,
        }
        seed = parameters.get("seed")
        if seed is not None:
            payload["seed"] = int(seed)

        if mode == "keyframe":
            first = self._first_public_url(task_input, "first_frame")
            last = self._first_public_url(task_input, "last_frame")
            if first:
                payload["first_frame"] = first
            if last:
                payload["last_frame"] = last
        elif mode == "reference":
            images = self._resolve_images(task_input, ("source_image", "reference_image"))
            if images:
                payload["images"] = images

        data = await self._post("/videos", payload)
        video_id = data.get("video_id")
        task_id = data.get("task_id") or data.get("id")
        if not video_id or not task_id:
            raise ProviderError("Agnes 返回了不完整的任务标识。")
        return ProviderTaskRef(external_task_id=str(task_id), external_video_id=str(video_id))

    # --- status -------------------------------------------------------------

    async def get_status(self, ref: ProviderTaskRef, model: ModelConfig, runtime: ProviderRuntime) -> ProviderStatus:
        if not ref.external_video_id:
            raise ProviderError("Agnes 任务缺少 video_id。")
        parsed = urlparse(runtime.base_url)
        url = f"{parsed.scheme}://{parsed.netloc}/agnesapi"
        async with httpx.AsyncClient(timeout=runtime.timeout) as client:
            response = await client.get(
                url,
                params={"video_id": ref.external_video_id, "model_name": model.external_model_id},
                headers={"Authorization": f"Bearer {runtime.api_key}"},
            )
        if not response.is_success:
            raise ProviderError(f"Agnes 查询失败: {response.status_code}")
        data = response.json()
        status = str(data.get("status", "")).lower()
        if status in ("completed", "succeeded", "success"):
            video_url = data.get("url")
            return ProviderStatus(status="succeeded", progress=100, result_urls=[video_url] if video_url else [])
        if status == "failed":
            error = data.get("error")
            message = error.get("message") if isinstance(error, dict) else str(error or "")
            return ProviderStatus(status="failed", progress=100, error=message or "Agnes 视频生成失败。")
        try:
            progress = int(data.get("progress") or 0)
        except (TypeError, ValueError):
            progress = 0
        return ProviderStatus(status="running", progress=max(0, min(100, progress)))

    # --- helpers ------------------------------------------------------------

    async def _post(self, path: str, payload: dict) -> dict:
        url = f"{self.runtime.base_url}{path}"
        async with httpx.AsyncClient(timeout=self.runtime.timeout) as client:
            response = await client.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.runtime.api_key}",
                    "Content-Type": "application/json",
                },
            )
        if not response.is_success:
            raise ProviderError(f"Agnes 请求失败: {response.status_code} {response.text[:500]}")
        try:
            data = response.json()
        except ValueError as error:
            raise ProviderError("Agnes 返回了无效的 JSON。") from error
        return data if isinstance(data, dict) else {}

    def _first_public_url(self, task_input: TaskInput, role: str) -> str | None:
        for asset in task_input.assets:
            if asset.role == role:
                return asset.public_url or self._data_uri(asset)
        return None

    def _resolve_images(self, task_input: TaskInput, roles: tuple[str, ...]) -> list[str]:
        images: list[str] = []
        for asset in task_input.assets:
            if asset.role in roles:
                images.append(asset.public_url or self._data_uri(asset))
        return images

    def _data_uri(self, asset) -> str:
        data = self.runtime.media.read_bytes(asset.storage_key)
        return f"data:{asset.mime_type};base64,{base64.b64encode(data).decode('ascii')}"


_PRECISE_SIZE = re.compile(r"^\d{3,5}x\d{3,5}$")


def _is_int(value: object) -> bool:
    try:
        int(value)  # type: ignore[arg-type]
        return True
    except (TypeError, ValueError):
        return False


def _number_errors(parameters: dict, key: str, minimum: float, maximum: float) -> list[str]:
    value = parameters.get(key)
    if value is None or value == "":
        return []
    try:
        number = float(value)
    except (TypeError, ValueError):
        return [f"{key} 必须是数字。"]
    if number < minimum or number > maximum:
        return [f"{key} 必须在 {minimum} 到 {maximum} 之间。"]
    return []
