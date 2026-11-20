import { providerCredential } from "@/lib/config";
import type { ModelRecord, ProviderStatus, ProviderTaskRef, TaskInput } from "@/lib/types";
import type { ProviderAdapter } from "./base";

export class OpenAICompatibleAdapter implements ProviderAdapter {
  constructor(private readonly type: "openai_compatible" | "fish_audio") {}
  validate(input: TaskInput) { return input.prompt.trim() ? [] : ["请输入文本。 "]; }
  async submit(input: TaskInput, model: ModelRecord): Promise<ProviderTaskRef> {
    const { baseUrl, apiKey } = providerCredential(this.type);
    const speech = model.capabilities.includes("text_to_speech");
    const endpoint = speech ? "/audio/speech" : "/images/generations";
    const body = speech ? { model: model.externalModelId, input: input.prompt, voice: input.parameters.voice ?? "alloy", response_format: input.parameters.response_format ?? "mp3", ...input.parameters } : { model: model.externalModelId, prompt: input.prompt, ...input.parameters };
    const response = await fetch(`${baseUrl}${endpoint}`, { method: "POST", headers: { Authorization: `Bearer ${apiKey}`, "Content-Type": "application/json" }, body: JSON.stringify(body), signal: AbortSignal.timeout(60_000) });
    if (!response.ok) throw new Error(`Provider 请求失败: ${response.status}`);
    const contentType = response.headers.get("content-type") ?? "";
    if (speech && contentType.startsWith("audio/")) return { taskId: `audio-${Date.now()}`, resultUrls: [`data:${contentType};base64,${Buffer.from(await response.arrayBuffer()).toString("base64")}`] };
    const data = await response.json() as { data?: { url?: string }[]; output?: string; task_id?: string };
    if (data.output) return { taskId: `result-${Date.now()}`, resultUrls: [data.output] };
    if (data.data?.[0]?.url) return { taskId: `result-${Date.now()}`, resultUrls: [data.data[0].url] };
    if (data.task_id) return { taskId: data.task_id };
    throw new Error("Provider 未返回任务或结果。");
  }
  async getStatus(): Promise<ProviderStatus> { return { status: "failed", progress: 100, error: "该 Provider 未声明异步状态接口。" }; }
}
