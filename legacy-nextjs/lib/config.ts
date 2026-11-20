import fs from "node:fs";
import YAML from "yaml";
import type { ProviderType } from "@/lib/types";

export type ConfigProvider = { type: ProviderType; name: string; baseUrl: string; apiKey: string };
const fallback: ConfigProvider[] = [
  { type: "agnes", name: "Agnes Video 2.5", baseUrl: "https://apihub.agnes-ai.com/v1", apiKey: "" },
  { type: "modelscope", name: "ModelScope", baseUrl: "https://api-inference.modelscope.cn", apiKey: "" },
  { type: "fish_audio", name: "Fish Audio S2 Pro", baseUrl: "https://api.fish.audio", apiKey: "" },
  { type: "xiaomi_mimo", name: "Mimo TTS", baseUrl: "https://api.xiaomimimo.com/v1", apiKey: "" },
];

export function loadProviderConfig(): { providers: ConfigProvider[] } {
  const configPath = process.env.PROVIDERS_CONFIG_PATH ?? "./providers.yaml";
  const parsed = fs.existsSync(configPath)
    ? YAML.parse(fs.readFileSync(configPath, "utf8")) as { providers?: Partial<ConfigProvider>[] }
    : {};
  const overrides = new Map((parsed.providers ?? []).map((item) => [item.type, item]));
  return {
    providers: fallback.map((provider) => {
      const override = overrides.get(provider.type);
      return {
        ...provider,
        ...override,
        type: provider.type,
        baseUrl: (override?.baseUrl ?? provider.baseUrl).replace(/\/$/, ""),
        apiKey: override?.apiKey ?? provider.apiKey
      };
    })
  };
}

export function providerCredential(type: ProviderType) {
  const config = loadProviderConfig().providers.find((item) => item.type === type);
  if (!config?.apiKey) throw new Error(`${type} API Key is not configured in providers.yaml`);
  return config;
}
