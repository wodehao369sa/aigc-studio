import type { Capability, ProviderType } from "@/lib/types";

export type ProviderModelModule = {
  type: string;
  label: string;
  externalModelId: string;
  capability: Capability;
  description: string;
  parameterSchema: {
    key: string;
    label: string;
    type: "text" | "textarea" | "number" | "select";
    required?: boolean;
    default?: string | number;
    options?: string[];
  }[];
};

export const providerModelModules: Partial<Record<ProviderType, ProviderModelModule[]>> = {
  xiaomi_mimo: [
    {
      type: "tts",
      label: "TTS · 预置音色",
      externalModelId: "mimo-v2.5-tts",
      capability: "text_to_speech",
      description: "MiMo-V2.5 预置音色语音合成。",
      parameterSchema: [
        { key: "voice", label: "音色", type: "select", default: "mimo_default", options: ["mimo_default", "冰糖", "茉莉", "苏打", "白桦", "Mia", "Chloe", "Milo", "Dean"] },
        { key: "format", label: "音频格式", type: "select", default: "mp3", options: ["mp3", "wav"] }
      ]
    },
    {
      type: "tts_voicedesign",
      label: "TTS · 音色设计",
      externalModelId: "mimo-v2.5-tts-voicedesign",
      capability: "text_to_speech",
      description: "通过文字描述设计音色。请在创作参数中填写声音特征和说话风格。",
      parameterSchema: [
        { key: "voice_description", label: "音色与风格描述", type: "textarea", required: true },
        { key: "format", label: "音频格式", type: "select", default: "mp3", options: ["mp3", "wav"] }
      ]
    }
  ]
};

export function findProviderModelModule(providerType: ProviderType, type: string) {
  return providerModelModules[providerType]?.find((item) => item.type === type);
}
