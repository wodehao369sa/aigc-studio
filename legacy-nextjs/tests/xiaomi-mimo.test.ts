import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { XiaomiMiMoAdapter } from "../lib/providers/xiaomi-mimo";
import type { ModelRecord, TaskInput } from "../lib/types";

const baseModel: ModelRecord = {
  id: "mimo-tts",
  providerId: "xiaomi_mimo",
  externalModelId: "mimo-v2.5-tts",
  name: "MiMo TTS",
  version: null,
  description: null,
  capabilities: ["text_to_speech"],
  parameterSchema: [],
  inputConstraints: {},
  enabled: true,
  sortOrder: 0
};

describe("Xiaomi MiMo TTS adapter", () => {
  let tempDir: string;
  let originalConfigPath: string | undefined;
  const adapter = new XiaomiMiMoAdapter();

  beforeEach(() => {
    tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "aigc-mimo-"));
    originalConfigPath = process.env.PROVIDERS_CONFIG_PATH;
    process.env.PROVIDERS_CONFIG_PATH = path.join(tempDir, "providers.yaml");
    fs.writeFileSync(process.env.PROVIDERS_CONFIG_PATH, "providers:\n  - type: xiaomi_mimo\n    apiKey: test-key\n");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    if (originalConfigPath === undefined) delete process.env.PROVIDERS_CONFIG_PATH;
    else process.env.PROVIDERS_CONFIG_PATH = originalConfigPath;
    fs.rmSync(tempDir, { recursive: true, force: true });
  });

  it("requires a voice description for the voice design model", () => {
    const model = { ...baseModel, externalModelId: "mimo-v2.5-tts-voicedesign" };
    const input: TaskInput = { prompt: "Hello there", parameters: {}, assets: [] };
    expect(adapter.validate(input, model)).toContain("音色设计模型需要填写音色与风格描述。");
  });

  it("submits MiMo chat completions and returns decoded audio as a data URL", async () => {
    const fetchMock = vi.fn(async (_url: string | URL | Request, init?: RequestInit) => {
      expect(new Headers(init?.headers).get("api-key")).toBe("test-key");
      const body = JSON.parse(String(init?.body));
      expect(body).toMatchObject({
        model: "mimo-v2.5-tts-voicedesign",
        messages: [
          { role: "user", content: "Warm, calm voice" },
          { role: "assistant", content: "Hello there" }
        ],
        audio: { format: "wav" }
      });
      return new Response(JSON.stringify({ choices: [{ message: { audio: { data: "YXVkaW8=" } } }] }), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);

    const model = { ...baseModel, externalModelId: "mimo-v2.5-tts-voicedesign" };
    const result = await adapter.submit({
      prompt: "Hello there",
      parameters: { voice_description: "Warm, calm voice", format: "wav" },
      assets: []
    }, model);

    expect(fetchMock).toHaveBeenCalledWith("https://api.xiaomimimo.com/v1/chat/completions", expect.any(Object));
    expect(result.resultUrls?.[0]).toBe("data:audio/wav;base64,YXVkaW8=");
  });
});
