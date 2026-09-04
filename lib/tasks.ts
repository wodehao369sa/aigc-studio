import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { initializeDatabase, sqlite } from "@/lib/db";
import { mediaPath, removeMedia, writeMedia } from "@/lib/media";
import { getAdapter } from "@/lib/providers";
import type { AssetRecord, Capability, ModelRecord, ProviderRecord, TaskInput, TaskRecord } from "@/lib/types";

initializeDatabase();
const parse = <T>(value: string) => JSON.parse(value) as T;
const id = () => crypto.randomUUID();

export function listProviders(): ProviderRecord[] { return sqlite.prepare("SELECT id, provider_type providerType, name, base_url baseUrl, enabled, max_concurrency maxConcurrency FROM providers ORDER BY name").all().map((item: any) => ({ ...item, enabled: Boolean(item.enabled) })) as ProviderRecord[]; }
export function listModels(capability?: string, includeDisabled = false): ModelRecord[] {
  const rows = sqlite.prepare(`SELECT id, provider_id providerId, external_model_id externalModelId, name, version, description, capabilities_json capabilitiesJson, parameter_schema_json parameterSchemaJson, input_constraints_json inputConstraintsJson, enabled, sort_order sortOrder FROM models ${includeDisabled ? "" : "WHERE enabled=1"} ORDER BY sort_order, name`).all() as any[];
  return rows.map((row) => ({ ...row, enabled: Boolean(row.enabled), capabilities: parse(row.capabilitiesJson), parameterSchema: parse(row.parameterSchemaJson), inputConstraints: parse(row.inputConstraintsJson) })).filter((model) => !capability || model.capabilities.includes(capability as Capability));
}
export function getModel(modelId: string): ModelRecord | undefined { return listModels(undefined, true).find((model) => model.id === modelId); }
export function getProvider(id: string): ProviderRecord | undefined { return listProviders().find((provider) => provider.id === id); }
export function getAsset(assetId: string): AssetRecord | undefined { const row = sqlite.prepare("SELECT id, storage_key storageKey, original_filename originalFilename, mime_type mimeType, size_bytes sizeBytes, metadata_json metadataJson, created_at createdAt FROM assets WHERE id=?").get(assetId) as any; return row ? { ...row, metadata: parse(row.metadataJson) } : undefined; }
export function getTask(taskId: string): TaskRecord | undefined { const row = sqlite.prepare("SELECT id, provider_id providerId, model_id modelId, capability, mode, parameters_json parametersJson, status, progress, external_task_id externalTaskId, external_video_id externalVideoId, error, created_at createdAt, started_at startedAt, completed_at completedAt, parent_task_id parentTaskId, result_asset_id resultAssetId FROM tasks WHERE id=?").get(taskId) as any; return row ? { ...row, parameters: parse(row.parametersJson) } : undefined; }
export function listTaskAssets(taskId: string) { return (sqlite.prepare("SELECT ta.role, a.id FROM task_assets ta JOIN assets a ON a.id=ta.asset_id WHERE ta.task_id=?").all(taskId) as { role: string; id: string }[]).map((item) => ({ role: item.role, asset: getAsset(item.id)! })); }
export function listTasks() { return (sqlite.prepare("SELECT id FROM tasks ORDER BY created_at DESC").all() as { id: string }[]).map((row) => getTask(row.id)!); }
export async function deleteTasks(taskIds: string[]) { for (const taskId of taskIds) await deleteTask(taskId); }

export async function createAsset(file: File): Promise<AssetRecord> {
  if (!["image/png", "image/jpeg", "image/webp"].includes(file.type)) throw new Error("仅支持 PNG、JPEG、WebP 图片。");
  const buffer = Buffer.from(await file.arrayBuffer());
  if (buffer.byteLength > 20 * 1024 * 1024) throw new Error("单个文件不得超过 20 MB。");
  const storageKey = await writeMedia(buffer, file.name);
  const asset: AssetRecord = { id: id(), storageKey, originalFilename: file.name, mimeType: file.type, sizeBytes: buffer.byteLength, metadata: {}, createdAt: Date.now() };
  sqlite.prepare("INSERT INTO assets VALUES (@id,@storageKey,@originalFilename,@mimeType,@sizeBytes,@metadataJson,@createdAt)").run({ ...asset, metadataJson: JSON.stringify(asset.metadata) });
  return asset;
}

export function publicReferenceUrl(taskId: string, assetId: string, baseUrl: string) {
  const token = crypto.randomBytes(32).toString("base64url"); const expiresAt = Date.now() + 24 * 60 * 60 * 1000;
  sqlite.prepare("INSERT INTO reference_tokens (token,task_id,asset_id,expires_at) VALUES (?,?,?,?)").run(token, taskId, assetId, expiresAt);
  return `${baseUrl.replace(/\/$/, "")}/api/reference/${token}`;
}
export function referenceAsset(token: string) { const row = sqlite.prepare("SELECT asset_id assetId FROM reference_tokens WHERE token=? AND invalidated_at IS NULL AND expires_at>? ").get(token, Date.now()) as { assetId: string } | undefined; return row ? getAsset(row.assetId) : undefined; }
export function invalidateTokens(taskId: string) { sqlite.prepare("UPDATE reference_tokens SET invalidated_at=? WHERE task_id=? AND invalidated_at IS NULL").run(Date.now(), taskId); }

export async function createTask(input: { modelId: string; capability: Capability; mode?: string; prompt: string; parameters: Record<string, unknown>; assets: { role: string; assetId: string }[] }, parentTaskId?: string) {
  const model = getModel(input.modelId); if (!model || !model.enabled) throw new Error("模型不存在或已禁用。");
  if (!model.capabilities.includes(input.capability)) throw new Error("所选模型不支持该创作方式。");
  const provider = getProvider(model.providerId); if (!provider?.enabled) throw new Error("服务不可用。");
  const taskId = id(); const assets = input.assets.map(({ role, assetId }) => { const asset = getAsset(assetId); if (!asset) throw new Error("参考素材不存在。"); return { role, asset }; });
  const publicBase = process.env.PUBLIC_BASE_URL; if (!publicBase && provider.providerType === "agnes" && assets.length) throw new Error("未配置 PUBLIC_BASE_URL，无法向 Agnes 提供参考媒体。");
  const parameters = { ...input.parameters, mode: input.mode ?? input.parameters.mode };
  const adapter = getAdapter(provider.providerType); const errors = adapter.validate({ prompt: input.prompt, parameters, assets }, model); if (errors.length) throw new Error(errors.join(" "));
  const providerInput: TaskInput = { prompt: input.prompt, parameters, assets: assets.map((item) => ({ ...item, publicUrl: provider.providerType === "agnes" ? publicReferenceUrl(taskId, item.asset.id, publicBase!) : undefined })) };
  sqlite.prepare("INSERT INTO tasks (id,provider_id,model_id,capability,mode,parameters_json,status,progress,created_at,parent_task_id) VALUES (?,?,?,?,?,?,?,?,?,?)").run(taskId, provider.id, model.id, input.capability, input.mode ?? null, JSON.stringify({ ...input.parameters, prompt: input.prompt }), "pending", 0, Date.now(), parentTaskId ?? null);
  for (const item of assets) sqlite.prepare("INSERT INTO task_assets (task_id,asset_id,role) VALUES (?,?,?)").run(taskId, item.asset.id, item.role);
  try { const ref = await adapter.submit(providerInput, model); sqlite.prepare("UPDATE tasks SET status='running', progress=0, external_task_id=?, external_video_id=?, started_at=? WHERE id=?").run(ref.taskId, ref.videoId ?? null, Date.now(), taskId); if (ref.resultUrls?.length) await completeTaskWithUrls(taskId, ref.resultUrls); } catch (error) { sqlite.prepare("UPDATE tasks SET status='failed', error=?, completed_at=? WHERE id=?").run(error instanceof Error ? error.message : "任务提交失败", Date.now(), taskId); invalidateTokens(taskId); }
  return getTask(taskId)!;
}

async function completeTaskWithUrls(taskId: string, urls: string[]) {
  const current = getTask(taskId)!; const result = urls[0]; const response = await fetch(result); if (!response.ok) throw new Error(`下载结果失败: ${response.status}`); const buffer = Buffer.from(await response.arrayBuffer());
  const mimeType = response.headers.get("content-type")?.split(";")[0] ?? (current.capability.includes("image") ? "image/png" : "video/mp4"); const storageKey = await writeMedia(buffer, mimeType.startsWith("video") ? "result.mp4" : "result.png"); const assetId = id();
  sqlite.prepare("INSERT INTO assets VALUES (?,?,?,?,?,?,?)").run(assetId, storageKey, path.basename(storageKey), mimeType, buffer.byteLength, "{}", Date.now()); sqlite.prepare("UPDATE tasks SET status='succeeded', progress=100, result_asset_id=?, completed_at=? WHERE id=?").run(assetId, Date.now(), taskId); sqlite.prepare("INSERT INTO task_assets (task_id,asset_id,role) VALUES (?,?,?)").run(taskId, assetId, "output"); invalidateTokens(taskId);
}

export async function pollOneTask() {
  const task = sqlite.prepare("SELECT id FROM tasks WHERE status IN ('pending','running') AND external_task_id IS NOT NULL ORDER BY created_at LIMIT 1").get() as { id: string } | undefined;
  if (!task) return null; const current = getTask(task.id)!; const model = getModel(current.modelId); const provider = getProvider(current.providerId); if (!model || !provider) throw new Error("任务配置不存在。");
  try {
    const status = await getAdapter(provider.providerType).getStatus({ taskId: current.externalTaskId!, videoId: current.externalVideoId ?? undefined }, model);
    if (status.status === "running") { sqlite.prepare("UPDATE tasks SET status='running', progress=? WHERE id=?").run(status.progress, current.id); return getTask(current.id); }
    if (status.status === "failed") { sqlite.prepare("UPDATE tasks SET status='failed', progress=100, error=?, completed_at=? WHERE id=?").run(status.error ?? "生成失败", Date.now(), current.id); invalidateTokens(current.id); return getTask(current.id); }
    const result = status.resultUrls?.[0]; if (!result) throw new Error("任务完成但未提供结果 URL。"); await completeTaskWithUrls(current.id, status.resultUrls!); return getTask(current.id);
  } catch (error) { sqlite.prepare("UPDATE tasks SET status='failed', error=?, completed_at=? WHERE id=?").run(error instanceof Error ? error.message : "轮询失败", Date.now(), current.id); invalidateTokens(current.id); return getTask(current.id); }
}

export function retryTask(taskId: string) { const task = getTask(taskId); if (!task || task.status !== "failed") throw new Error("仅失败任务可重试。"); const params = task.parameters; return createTask({ modelId: task.modelId, capability: task.capability, mode: task.mode ?? undefined, prompt: String(params.prompt ?? ""), parameters: params, assets: listTaskAssets(taskId).filter((item) => item.role !== "output").map((item) => ({ role: item.role, assetId: item.asset.id })) }, taskId); }
export async function deleteTask(taskId: string) { const assets = listTaskAssets(taskId); invalidateTokens(taskId); sqlite.prepare("DELETE FROM task_assets WHERE task_id=?").run(taskId); sqlite.prepare("DELETE FROM tasks WHERE id=?").run(taskId); for (const item of assets) { const count = (sqlite.prepare("SELECT count(*) count FROM task_assets WHERE asset_id=?").get(item.asset.id) as { count: number }).count; if (!count) { await removeMedia(item.asset.storageKey); sqlite.prepare("DELETE FROM assets WHERE id=?").run(item.asset.id); } } }
