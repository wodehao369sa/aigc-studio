import { AgnesAdapter } from "./agnes";
import { ModelScopeAdapter } from "./modelscope";
import type { ProviderAdapter } from "./base";
import type { ProviderType } from "@/lib/types";

export function getAdapter(type: ProviderType): ProviderAdapter { return type === "agnes" ? new AgnesAdapter() : new ModelScopeAdapter(); }
