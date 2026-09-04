import { describe, expect, it } from "vitest";
import { AgnesAdapter } from "../lib/providers/agnes";
import { ModelScopeAdapter } from "../lib/providers/modelscope";
import type { AssetRecord, ModelRecord, TaskInput } from "../lib/types";

const asset: AssetRecord = { id: "a", storageKey: "a.png", originalFilename: "a.png", mimeType: "image/png", sizeBytes: 1, metadata: {}, createdAt: 0 };
const model: ModelRecord = { id: "m", providerId: "agnes", externalModelId: "agnes-video-2.5", name: "Agnes", version: null, description: null, capabilities: ["text_to_video"], parameterSchema: [], inputConstraints: {}, enabled: true, sortOrder: 0 };
const base = (parameters: Record<string, unknown>, assets: TaskInput["assets"] = []): TaskInput => ({ prompt: "a scene", parameters, assets });

describe("Agnes validation", () => {
  const adapter = new AgnesAdapter();
  it("accepts text video", () => expect(adapter.validate(base({ mode: "text", seconds: 5, size: "720P", aspect_ratio: "16:9" }), model)).toEqual([]));
  it("requires a keyframe", () => expect(adapter.validate(base({ mode: "keyframe", seconds: 5, size: "720P", aspect_ratio: "16:9" }), model)).toContain("首尾帧模式至少需要一张图片。"));
  it("accepts a first frame", () => expect(adapter.validate(base({ mode: "keyframe", seconds: 5, size: "720P", aspect_ratio: "16:9" }, [{ role: "first_frame", asset, publicUrl: "https://x/a" }]), model)).toEqual([]));
  it("requires a reference image", () => expect(adapter.validate(base({ mode: "reference", seconds: 5, size: "720P", aspect_ratio: "16:9" }), model)).toContain("图片参考模式需要上传一张参考图。"));
});

describe("ModelScope validation", () => { it("requires a prompt", () => expect(new ModelScopeAdapter().validate({ prompt: "", parameters: {}, assets: [] }, model)).toContain("请输入提示词。")); });
