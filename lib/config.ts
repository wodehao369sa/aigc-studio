import fs from "node:fs";
import YAML from "yaml";
import type { ProviderType } from "@/lib/types";

type ConfigProvider = { type: ProviderType; name: string; baseUrl: string; apiKey: string };
const fallback: ConfigProvider[] = [
  { type: "agnes", name: "Agnes Video 2.5", baseUrl: "https://apihub.agnes-ai.com/v1", apiKey: "" },
  { type: "modelscope", name: "ModelScope", baseUrl: "https://api-inference.modelscope.cn", apiKey: "" },
];

export function loadProviderConfig(): { providers: ConfigProvider[] } {
  const configPath = process.env.PROVIDERS_CONFIG_PATH ?? "./providers.yaml";
  if (!fs.existsSync(configPath)) return { providers: fallback };
  const parsed = YAML.parse(fs.readFileSync(configPath, "utf8")) as { providers?: ConfigProvider[] };
  return { providers: (parsed.providers ?? []).map((item) => ({ ...item, baseUrl: item.baseUrl.replace(/\/$/, "") })) };
}

export function providerCredential(type: ProviderType) {
  const config = loadProviderConfig().providers.find((item) => item.type === type);
  if (!config?.apiKey) throw new Error(`${type} API Key is not configured in providers.yaml`);
  return config;
}
