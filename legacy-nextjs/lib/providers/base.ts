import type { ModelRecord, ProviderStatus, ProviderTaskRef, TaskInput } from "@/lib/types";

export interface ProviderAdapter {
  validate(input: TaskInput, model: ModelRecord): string[];
  submit(input: TaskInput, model: ModelRecord): Promise<ProviderTaskRef>;
  getStatus(ref: ProviderTaskRef, model: ModelRecord): Promise<ProviderStatus>;
}
