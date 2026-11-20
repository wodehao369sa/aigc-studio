import type { Capability, ProviderType } from "./types";

export const capabilityLabels: Record<Capability, string> = {
  text_to_image: "文生图", image_to_image: "图生图",
  text_to_video: "文生视频", image_to_video: "图生视频",
  keyframe_video: "首尾帧视频", reference_video: "参考图视频",
  text_to_speech: "文本转语音"
};

export const providerCapabilities: Record<ProviderType, readonly Capability[]> = {
  agnes: ["text_to_image", "image_to_image", "text_to_video", "image_to_video", "keyframe_video", "reference_video"],
  modelscope: ["text_to_image", "image_to_image"],
  openai_compatible: ["text_to_image", "text_to_speech"],
  fish_audio: ["text_to_speech"],
  xiaomi_mimo: ["text_to_speech"]
};

export const workspaces = [
  { label: "图片", modes: ["text_to_image", "image_to_image"] },
  { label: "视频", modes: ["text_to_video", "image_to_video", "keyframe_video", "reference_video"] },
  { label: "语音", modes: ["text_to_speech"] }
] satisfies { label: string; modes: Capability[] }[];
