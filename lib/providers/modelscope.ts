import { providerCredential } from "@/lib/config";
import type { ModelRecord, ProviderStatus, ProviderTaskRef, TaskInput } from "@/lib/types";
import type { ProviderAdapter } from "./base";
import { mediaPath } from "@/lib/media";
import fs from "node:fs/promises";

export class ModelScopeAdapter implements ProviderAdapter {
  validate(input: TaskInput, _model: ModelRecord) { return input.prompt.trim() ? [] : ["请输入提示词。"]; }
  async submit(input: TaskInput, model: ModelRecord): Promise<ProviderTaskRef> {
    const { baseUrl, apiKey } = providerCredential("modelscope");
    const body: Record<string, unknown> = { model: model.externalModelId, prompt: input.prompt, ...input.parameters };
    delete body.mode;
    const reference = input.assets.find((item) => item.role === "source_image");
    if (reference) { const bytes = await fs.readFile(mediaPath(reference.asset.storageKey)); body.image_url = `data:${reference.asset.mimeType};base64,${bytes.toString("base64")}`; }
    const response = await fetch(`${baseUrl}/v1/images/generations`, { method: "POST", headers: { Authorization: `Bearer ${apiKey}`, "Content-Type": "application/json", "X-ModelScope-Async-Mode": "true" }, body: JSON.stringify(body) });
    if (!response.ok) throw new Error(`ModelScope 创建失败: ${response.status} ${await response.text()}`);
    const data = await response.json() as { task_id?: string };
    if (!data.task_id) throw new Error("ModelScope 未返回 task_id。");
    return { taskId: data.task_id };
  }
  async getStatus(ref: ProviderTaskRef): Promise<ProviderStatus> {
    const { baseUrl, apiKey } = providerCredential("modelscope");
    const response = await fetch(`${baseUrl}/v1/tasks/${ref.taskId}`, { headers: { Authorization: `Bearer ${apiKey}`, "X-ModelScope-Task-Type": "image_generation" } });
    if (!response.ok) throw new Error(`ModelScope 查询失败: ${response.status}`);
    const data = await response.json() as { task_status: string; output_images?: string[]; message?: string };
    if (data.task_status === "SUCCEED") return { status: "succeeded", progress: 100, resultUrls: data.output_images ?? [] };
    if (data.task_status === "FAILED") return { status: "failed", progress: 100, error: data.message ?? "ModelScope 图片生成失败。" };
    return { status: "running", progress: 0 };
  }
}
