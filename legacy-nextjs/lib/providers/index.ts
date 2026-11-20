import { AgnesAdapter } from "./agnes";
import { ModelScopeAdapter } from "./modelscope";
import type { ProviderAdapter } from "./base";
import type { ProviderType } from "@/lib/types";
import { OpenAICompatibleAdapter } from "./openai-compatible";
import { XiaomiMiMoAdapter } from "./xiaomi-mimo";

export function getAdapter(type: ProviderType): ProviderAdapter {
  if (type === "agnes") return new AgnesAdapter();
  if (type === "modelscope") return new ModelScopeAdapter();
  if (type === "xiaomi_mimo") return new XiaomiMiMoAdapter();
  return new OpenAICompatibleAdapter(type);
}
