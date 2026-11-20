import { randomUUID } from "node:crypto";
import { NextResponse } from "next/server";
import { z } from "zod";
import { providerCapabilities } from "@/lib/catalog";
import { findProviderModelModule } from "@/lib/provider-modules";
import { sqlite } from "@/lib/db";
import { getProvider, listModels } from "@/lib/tasks";
import { CAPABILITIES } from "@/lib/types";

export const runtime = "nodejs";

const field = z.object({
  key: z.string().regex(/^[a-zA-Z][a-zA-Z0-9_]{0,63}$/).refine(
    (key) => !["prompt", "model", "input", "mode", "constructor"].includes(key)
  ),
  label: z.string().trim().min(1).max(80),
  type: z.enum(["text", "textarea", "number", "select"]),
  required: z.boolean().optional(),
  default: z.union([z.string(), z.number()]).optional(),
  options: z.array(z.string().min(1)).min(1).max(50).optional(),
  min: z.number().optional(),
  max: z.number().optional()
}).refine((value) => value.type !== "select" || Boolean(value.options?.length));

const model = z.object({
  providerId: z.string().min(1),
  modelModuleType: z.string().optional(),
  externalModelId: z.string().trim().min(1).max(200),
  name: z.string().trim().min(1).max(100),
  version: z.string().max(80).nullable().default(null),
  description: z.string().max(1000).nullable().default(null),
  capabilities: z.array(z.enum(CAPABILITIES)).min(1).max(CAPABILITIES.length),
  parameterSchema: z.array(field).max(32).default([]).refine(
    (fields) => new Set(fields.map(({ key }) => key)).size === fields.length
  ),
  inputConstraints: z.record(z.unknown()).default({}),
  enabled: z.boolean().default(true),
  sortOrder: z.number().int().min(0).max(99999).default(0)
});

export async function GET() {
  return NextResponse.json(listModels(undefined, true));
}

async function save(request: Request, edit: boolean) {
  const body: unknown = await request.json().catch(() => null);
  const parsed = (edit ? model.extend({ id: z.string().min(1) }) : model).safeParse(body);
  if (!parsed.success) {
    const issue = parsed.error.issues[0];
    return NextResponse.json({ error: `配置有误：${issue.path.join(".")} · ${issue.message}` }, { status: 400 });
  }
  const data = parsed.data;
  const provider = getProvider(data.providerId);
  const selectedModule = provider && data.modelModuleType
    ? findProviderModelModule(provider.providerType, data.modelModuleType)
    : undefined;
  if (!provider || (data.modelModuleType && !selectedModule) || (!data.modelModuleType && data.capabilities.some((capability) => !providerCapabilities[provider.providerType]?.includes(capability)))) {
    return NextResponse.json({ error: "所选服务不支持这些能力。" }, { status: 400 });
  }
  const capabilities = selectedModule ? [selectedModule.capability] : data.capabilities;
  const externalModelId = selectedModule?.externalModelId ?? data.externalModelId;
  const parameterSchema = selectedModule?.parameterSchema ?? data.parameterSchema;
  const id = edit ? (data as typeof data & { id: string }).id : randomUUID();
  const row = {
    ...data, id, externalModelId, enabled: Number(data.enabled),
    capabilitiesJson: JSON.stringify(capabilities),
    parameterSchemaJson: JSON.stringify(parameterSchema),
    inputConstraintsJson: JSON.stringify(data.inputConstraints)
  };
  const result = edit
    ? sqlite.prepare(`UPDATE models SET name=@name, external_model_id=@externalModelId, version=@version,
      description=@description, capabilities_json=@capabilitiesJson, parameter_schema_json=@parameterSchemaJson,
      input_constraints_json=@inputConstraintsJson, enabled=@enabled, sort_order=@sortOrder
      WHERE id=@id AND provider_id=@providerId`).run(row)
    : sqlite.prepare(`INSERT INTO models (id,provider_id,external_model_id,name,version,description,
      capabilities_json,parameter_schema_json,input_constraints_json,enabled,sort_order)
      VALUES (@id,@providerId,@externalModelId,@name,@version,@description,@capabilitiesJson,
      @parameterSchemaJson,@inputConstraintsJson,@enabled,@sortOrder)`).run(row);
  if (!result.changes) return NextResponse.json({ error: "模型不存在或服务已变更。" }, { status: 404 });
  return NextResponse.json({ id }, { status: edit ? 200 : 201 });
}

export const POST = (request: Request) => save(request, false);
export const PATCH = (request: Request) => save(request, true);

export async function DELETE(request: Request) {
  const modelId = new URL(request.url).searchParams.get("id");
  const parsedId = z.string().trim().min(1).max(200).safeParse(modelId);
  if (!parsedId.success) {
    return NextResponse.json({ error: "模型 ID 无效。" }, { status: 400 });
  }

  const result = sqlite.prepare("DELETE FROM models WHERE id=?").run(parsedId.data);
  if (!result.changes) {
    return NextResponse.json({ error: "模型不存在。" }, { status: 404 });
  }
  return NextResponse.json({ ok: true });
}
