import { integer, sqliteTable, text } from "drizzle-orm/sqlite-core";

export const providers = sqliteTable("providers", {
  id: text("id").primaryKey(),
  providerType: text("provider_type").notNull(),
  name: text("name").notNull(),
  baseUrl: text("base_url").notNull(),
  enabled: integer("enabled", { mode: "boolean" }).notNull(),
  maxConcurrency: integer("max_concurrency").notNull()
});

export const models = sqliteTable("models", {
  id: text("id").primaryKey(),
  providerId: text("provider_id").notNull(),
  externalModelId: text("external_model_id").notNull(),
  name: text("name").notNull(),
  version: text("version"),
  description: text("description"),
  capabilitiesJson: text("capabilities_json").notNull(),
  parameterSchemaJson: text("parameter_schema_json").notNull(),
  inputConstraintsJson: text("input_constraints_json").notNull(),
  enabled: integer("enabled", { mode: "boolean" }).notNull(),
  sortOrder: integer("sort_order").notNull()
});

export const assets = sqliteTable("assets", {
  id: text("id").primaryKey(),
  storageKey: text("storage_key").notNull(),
  originalFilename: text("original_filename").notNull(),
  mimeType: text("mime_type").notNull(),
  sizeBytes: integer("size_bytes").notNull(),
  metadataJson: text("metadata_json").notNull(),
  createdAt: integer("created_at").notNull()
});

export const tasks = sqliteTable("tasks", {
  id: text("id").primaryKey(),
  providerId: text("provider_id").notNull(),
  modelId: text("model_id").notNull(),
  capability: text("capability").notNull(),
  mode: text("mode"),
  parametersJson: text("parameters_json").notNull(),
  status: text("status").notNull(),
  progress: integer("progress").notNull(),
  externalTaskId: text("external_task_id"),
  externalVideoId: text("external_video_id"),
  error: text("error"),
  createdAt: integer("created_at").notNull(),
  startedAt: integer("started_at"),
  completedAt: integer("completed_at"),
  parentTaskId: text("parent_task_id"),
  resultAssetId: text("result_asset_id"),
  isFavorite: integer("is_favorite", { mode: "boolean" }).notNull().default(false),
  favoritedAt: integer("favorited_at")
});

export const taskAssets = sqliteTable("task_assets", {
  taskId: text("task_id").notNull(),
  assetId: text("asset_id").notNull(),
  role: text("role").notNull()
});

export const referenceTokens = sqliteTable("reference_tokens", {
  token: text("token").primaryKey(),
  taskId: text("task_id").notNull(),
  assetId: text("asset_id").notNull(),
  expiresAt: integer("expires_at").notNull(),
  invalidatedAt: integer("invalidated_at")
});
