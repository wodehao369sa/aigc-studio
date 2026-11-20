import { providerCredential } from "@/lib/config";
import type { ModelRecord, ProviderStatus, ProviderTaskRef, TaskInput } from "@/lib/types";
import type { ProviderAdapter } from "./base";

type MiMoResponse = {
  choices?: { message?: { audio?: { data?: string } } }[];
  error?: { message?: string };
};

export class XiaomiMiMoAdapter implements ProviderAdapter {
  validate(input: TaskInput, model: ModelRecord) {
    const errors: string[] = [];
    if (!input.prompt.trim()) errors.push("请输入需要合成的文本。");
    if (model.externalModelId === "mimo-v2.5-tts-voicedesign" && !String(input.parameters.voice_description ?? "").trim()) {
      errors.push("音色设计模型需要填写音色与风格描述。");
    }
    return errors;
  }

  async submit(input: TaskInput, model: ModelRecord): Promise<ProviderTaskRef> {
    const { baseUrl, apiKey } = providerCredential("xiaomi_mimo");
    const voiceDescription = String(input.parameters.voice_description ?? "").trim();
    const messages = [
      ...(model.externalModelId === "mimo-v2.5-tts-voicedesign"
        ? [{ role: "user", content: voiceDescription }]
        : []),
      { role: "assistant", content: input.prompt }
    ];
    const audio: Record<string, unknown> = {
      format: input.parameters.format === "wav" ? "wav" : "mp3"
    };
    if (model.externalModelId === "mimo-v2.5-tts") {
      audio.voice = String(input.parameters.voice ?? "mimo_default");
    }

    const response = await fetch(`${baseUrl}/chat/completions`, {
      method: "POST",
      headers: { "api-key": apiKey, "Content-Type": "application/json" },
      body: JSON.stringify({ model: model.externalModelId, messages, audio }),
      signal: AbortSignal.timeout(120_000)
    });
    if (!response.ok) throw new Error(`Xiaomi MiMo 请求失败: ${response.status}`);
    const data = await response.json() as MiMoResponse;
    const encodedAudio = data.choices?.[0]?.message?.audio?.data;
    if (!encodedAudio) throw new Error("Xiaomi MiMo 未返回音频数据。");

    const format = audio.format as string;
    const contentType = format === "wav" ? "audio/wav" : "audio/mpeg";
    return {
      taskId: `mimo-${Date.now()}`,
      resultUrls: [`data:${contentType};base64,${encodedAudio}`]
    };
  }

  async getStatus(): Promise<ProviderStatus> {
    return { status: "failed", progress: 100, error: "MiMo TTS 使用同步生成，不支持异步状态查询。" };
  }
}
