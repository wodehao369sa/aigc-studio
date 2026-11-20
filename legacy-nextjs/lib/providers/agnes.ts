import { providerCredential } from "@/lib/config";
import type { ModelRecord, ProviderStatus, ProviderTaskRef, TaskInput } from "@/lib/types";
import type { ProviderAdapter } from "./base";
import { mediaPath } from "@/lib/media";
import fs from "node:fs/promises";

const ratios = ["21:9", "16:9", "4:3", "1:1", "3:4", "9:16"];
export class AgnesAdapter implements ProviderAdapter {
  validate(input: TaskInput, _model: ModelRecord) {
    const errors: string[] = [];
    if (_model.capabilities.includes("text_to_image") || _model.capabilities.includes("image_to_image")) {
      if (!input.prompt.trim()) errors.push("请输入提示词。");
      const size = String(input.parameters.size ?? "1K");
      if (!["1K", "2K", "3K", "4K"].includes(size) && !/^\\d+x\\d+$/.test(size)) errors.push("请选择有效图片尺寸。");
      return errors;
    }
    const mode = String(input.parameters.mode ?? "text");
    if (_model.externalModelId === "agnes-video-v2.0") {
      const hasSource = input.assets.some((item) => item.role === "source_image");
      const first = input.assets.some((item) => item.role === "first_frame");
      const last = input.assets.some((item) => item.role === "last_frame");
      const frames = Number(input.parameters.num_frames ?? 121);
      const frameRate = Number(input.parameters.frame_rate ?? 24);
      if (!input.prompt.trim()) errors.push("请输入提示词。");
      if (!["text", "image", "keyframe"].includes(mode)) errors.push("Agnes Video V2.0 模式无效。");
      if (mode === "image" && !hasSource) errors.push("图生视频需要上传源图片。");
      if (mode === "keyframe" && !first && !last) errors.push("关键帧模式至少需要一张图片。");
      if (!Number.isInteger(frames) || frames < 9 || frames > 441 || (frames - 1) % 8 !== 0) errors.push("视频帧数必须为不超过 441 的 8n + 1 整数。");
      if (frameRate < 1 || frameRate > 60) errors.push("帧率必须在 1 到 60 之间。");
      return errors;
    }
    const seconds = Number(input.parameters.seconds ?? 5);
    if (!input.prompt.trim()) errors.push("请输入提示词。");
    if (!["text", "keyframe", "reference"].includes(mode)) errors.push("Agnes 模式无效。");
    if (seconds < 4 || seconds > 12) errors.push("视频时长必须为 4 到 12 秒。");
    const sizes = _model.externalModelId === "agnes-video-2.5-flash" ? ["720P"] : ["720P", "960P", "2K"];
    if (!sizes.includes(String(input.parameters.size ?? "720P"))) errors.push("请选择有效分辨率。");
    if (!ratios.includes(String(input.parameters.aspect_ratio ?? "16:9"))) errors.push("请选择有效画幅。");
    const first = input.assets.some((item) => item.role === "first_frame");
    const last = input.assets.some((item) => item.role === "last_frame");
    const reference = input.assets.some((item) => item.role === "reference_image") || input.assets.some((item) => item.role === "source_image");
    if (mode === "keyframe" && !first && !last) errors.push("首尾帧模式至少需要一张图片。");
    if (mode === "reference" && !reference) errors.push("图片参考模式需要上传一张参考图。");
    if (mode === "text" && (first || last || reference)) errors.push("文生视频不能携带参考图片。");
    return errors;
  }
  async submit(input: TaskInput, model: ModelRecord): Promise<ProviderTaskRef> {
    const { baseUrl, apiKey } = providerCredential("agnes");
    if (model.capabilities.includes("text_to_image") || model.capabilities.includes("image_to_image")) {
      const size = String(input.parameters.size ?? "1K");
      const ratio = String(input.parameters.ratio ?? "1:1");
      const body: Record<string, unknown> = { model: model.externalModelId, prompt: input.prompt, size, ratio, extra_body: { response_format: "url" } };
      const images = await Promise.all(input.assets.filter((item) => item.role === "source_image").map(async (item) => {
        const bytes = await fs.readFile(mediaPath(item.asset.storageKey));
        return `data:${item.asset.mimeType};base64,${bytes.toString("base64")}`;
      }));
      if (images.length) body.extra_body = { ...(body.extra_body as object), image: images };
      const response = await fetch(`${baseUrl}/images/generations`, { method: "POST", headers: { Authorization: `Bearer ${apiKey}`, "Content-Type": "application/json" }, body: JSON.stringify(body) });
      if (!response.ok) throw new Error(`Agnes 图片创建失败: ${response.status} ${await response.text()}`);
      const data = await response.json() as { data?: { url?: string; b64_json?: string }[] };
      const urls = (data.data ?? []).flatMap((item) => item.url ? [item.url] : item.b64_json ? [`data:image/png;base64,${item.b64_json}`] : []);
      if (!urls.length) throw new Error("Agnes 图片接口未返回结果。");
      return { taskId: `agnes-image-${Date.now()}`, resultUrls: urls };
    }
    if (model.externalModelId === "agnes-video-v2.0") {
      const mode = String(input.parameters.mode ?? "text");
      const assetFor = (role: string) => input.assets.find((item) => item.role === role)?.publicUrl;
      const body: Record<string, unknown> = { model: model.externalModelId, prompt: input.prompt, width: Number(input.parameters.width ?? 1152), height: Number(input.parameters.height ?? 768), num_frames: Number(input.parameters.num_frames ?? 121), frame_rate: Number(input.parameters.frame_rate ?? 24), ...(input.parameters.seed ? { seed: Number(input.parameters.seed) } : {}), ...(input.parameters.negative_prompt ? { negative_prompt: String(input.parameters.negative_prompt) } : {}) };
      if (mode === "image") body.image = assetFor("source_image");
      if (mode === "keyframe") body.extra_body = { mode: "keyframes", image: [assetFor("first_frame"), assetFor("last_frame")].filter(Boolean) };
      const response = await fetch(`${baseUrl}/videos`, { method: "POST", headers: { Authorization: `Bearer ${apiKey}`, "Content-Type": "application/json" }, body: JSON.stringify(body) });
      if (!response.ok) throw new Error(`Agnes 创建失败: ${response.status} ${await response.text()}`);
      const data = await response.json() as { task_id?: string; id?: string; video_id?: string };
      if (!data.video_id || !(data.task_id ?? data.id)) throw new Error("Agnes 返回了不完整的任务标识。");
      return { taskId: data.task_id ?? data.id!, videoId: data.video_id };
    }
    const mode = String(input.parameters.mode ?? "text");
    const common = { model: model.externalModelId, prompt: input.prompt, mode, seconds: String(input.parameters.seconds ?? 5), size: String(input.parameters.size ?? "720P"), aspect_ratio: String(input.parameters.aspect_ratio ?? "16:9"), n: 1, ...(input.parameters.seed ? { seed: Number(input.parameters.seed) } : {}) };
    const assetFor = (role: string) => input.assets.find((item) => item.role === role)?.publicUrl;
    const body = mode === "keyframe" ? { ...common, first_frame: assetFor("first_frame"), last_frame: assetFor("last_frame") } : mode === "reference" ? { ...common, images: input.assets.filter((item) => item.role === "reference_image" || item.role === "source_image").map((item) => item.publicUrl) } : common;
    const response = await fetch(`${baseUrl}/videos`, { method: "POST", headers: { Authorization: `Bearer ${apiKey}`, "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!response.ok) throw new Error(`Agnes 创建失败: ${response.status} ${await response.text()}`);
    const data = await response.json() as { task_id?: string; id?: string; video_id?: string };
    if (!data.video_id || !(data.task_id ?? data.id)) throw new Error("Agnes 返回了不完整的任务标识。");
    return { taskId: data.task_id ?? data.id!, videoId: data.video_id };
  }
  async getStatus(ref: ProviderTaskRef, model: ModelRecord): Promise<ProviderStatus> {
    const { apiKey } = providerCredential("agnes");
    if (!ref.videoId) throw new Error("Agnes 任务缺少 video_id。");
    const url = new URL("https://apihub.agnes-ai.com/agnesapi"); url.searchParams.set("video_id", ref.videoId); if (model.externalModelId !== "agnes-video-v2.0") url.searchParams.set("model_name", model.externalModelId);
    const response = await fetch(url, { headers: { Authorization: `Bearer ${apiKey}` } });
    if (!response.ok) throw new Error(`Agnes 查询失败: ${response.status}`);
    const data = await response.json() as { status: string; progress?: number; metadata?: { url?: string }; error?: { message?: string } };
    if (data.status === "completed") return { status: "succeeded", progress: 100, resultUrls: data.metadata?.url ? [data.metadata.url] : [] };
    if (data.status === "failed") return { status: "failed", progress: 100, error: data.error?.message ?? "Agnes 视频生成失败。" };
    return { status: "running", progress: data.progress ?? 0 };
  }
}
