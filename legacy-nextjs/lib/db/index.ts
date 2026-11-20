import Database from "better-sqlite3";
import { drizzle } from "drizzle-orm/better-sqlite3";
import fs from "node:fs";
import path from "node:path";
import { loadProviderConfig } from "@/lib/config";

const url = process.env.DATABASE_URL ?? "./data/aigc-studio.db";
fs.mkdirSync(path.dirname(url), { recursive: true });
const sqlite = new Database(url);
sqlite.pragma("journal_mode = WAL");
sqlite.pragma("foreign_keys = ON");
sqlite.pragma("busy_timeout = 10000");
export const db = drizzle(sqlite);
export { sqlite };

function ensureTaskColumns() {
  const columns = sqlite.prepare("PRAGMA table_info(tasks)").all() as { name: string }[];
  const names = new Set(columns.map((column) => column.name));
  if (!names.has("is_favorite")) {
    sqlite.exec("ALTER TABLE tasks ADD COLUMN is_favorite INTEGER NOT NULL DEFAULT 0");
  }
  if (!names.has("favorited_at")) {
    sqlite.exec("ALTER TABLE tasks ADD COLUMN favorited_at INTEGER");
  }
}

export function initializeDatabase() {
  sqlite.exec(`
    CREATE TABLE IF NOT EXISTS providers (
      id TEXT PRIMARY KEY,
      provider_type TEXT NOT NULL,
      name TEXT NOT NULL,
      base_url TEXT NOT NULL,
      enabled INTEGER NOT NULL DEFAULT 1,
      max_concurrency INTEGER NOT NULL DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS models (
      id TEXT PRIMARY KEY,
      provider_id TEXT NOT NULL,
      external_model_id TEXT NOT NULL,
      name TEXT NOT NULL,
      version TEXT,
      description TEXT,
      capabilities_json TEXT NOT NULL,
      parameter_schema_json TEXT NOT NULL,
      input_constraints_json TEXT NOT NULL,
      enabled INTEGER NOT NULL DEFAULT 1,
      sort_order INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS assets (
      id TEXT PRIMARY KEY,
      storage_key TEXT NOT NULL UNIQUE,
      original_filename TEXT NOT NULL,
      mime_type TEXT NOT NULL,
      size_bytes INTEGER NOT NULL,
      metadata_json TEXT NOT NULL,
      created_at INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS tasks (
      id TEXT PRIMARY KEY,
      provider_id TEXT NOT NULL,
      model_id TEXT NOT NULL,
      capability TEXT NOT NULL,
      mode TEXT,
      parameters_json TEXT NOT NULL,
      status TEXT NOT NULL,
      progress INTEGER NOT NULL DEFAULT 0,
      external_task_id TEXT,
      external_video_id TEXT,
      error TEXT,
      created_at INTEGER NOT NULL,
      started_at INTEGER,
      completed_at INTEGER,
      parent_task_id TEXT,
      result_asset_id TEXT,
      is_favorite INTEGER NOT NULL DEFAULT 0,
      favorited_at INTEGER
    );
    CREATE TABLE IF NOT EXISTS task_assets (
      task_id TEXT NOT NULL,
      asset_id TEXT NOT NULL,
      role TEXT NOT NULL,
      PRIMARY KEY(task_id, asset_id, role)
    );
    CREATE TABLE IF NOT EXISTS reference_tokens (
      token TEXT PRIMARY KEY,
      task_id TEXT NOT NULL,
      asset_id TEXT NOT NULL,
      expires_at INTEGER NOT NULL,
      invalidated_at INTEGER
    );
  `);

  const providerColumns = sqlite.prepare("PRAGMA table_info(providers)").all() as { name: string }[];
  if (providerColumns.some((column) => column.name === "api_key")) {
    sqlite.exec("UPDATE providers SET api_key='' WHERE api_key<>''");
  }

  ensureTaskColumns();
  sqlite.exec(`
    CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_tasks_favorite_created_at
      ON tasks(favorited_at DESC)
      WHERE is_favorite = 1;
    CREATE INDEX IF NOT EXISTS idx_tasks_gallery
      ON tasks(favorited_at DESC)
      WHERE is_favorite = 1
        AND status = 'succeeded'
        AND result_asset_id IS NOT NULL;
  `);

  const configs = loadProviderConfig();
  const upsert = sqlite.prepare(`
    INSERT INTO providers (id, provider_type, name, base_url, enabled, max_concurrency)
    VALUES (@id, @providerType, @name, @baseUrl, 1, 1)
    ON CONFLICT(id) DO UPDATE SET name=excluded.name, base_url=excluded.base_url
  `);
  for (const item of configs.providers) {
    upsert.run({ id: item.type, providerType: item.type, name: item.name, baseUrl: item.baseUrl });
  }
}
