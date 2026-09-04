import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";

export const MEDIA_ROOT = path.resolve(process.env.MEDIA_ROOT ?? "./media");
export const WARN_BYTES = 4 * 1024 * 1024 * 1024;
export const LIMIT_BYTES = 5 * 1024 * 1024 * 1024;

export async function ensureMediaRoot() { await fs.mkdir(MEDIA_ROOT, { recursive: true }); }
export function safeKey(key: string) { return key.replace(/[^a-zA-Z0-9._/-]/g, "_").replace(/^\/+/, ""); }
export function mediaPath(key: string) { return path.join(MEDIA_ROOT, safeKey(key)); }
export async function writeMedia(buffer: Buffer, originalName: string) {
  await ensureMediaRoot();
  const ext = path.extname(originalName).slice(0, 12) || ".bin";
  const key = `${new Date().toISOString().slice(0, 10)}/${crypto.randomUUID()}${ext}`;
  const file = mediaPath(key);
  await fs.mkdir(path.dirname(file), { recursive: true });
  await fs.writeFile(file, buffer);
  return key;
}
export async function mediaUsage(dir = MEDIA_ROOT): Promise<number> {
  try { const entries = await fs.readdir(dir, { withFileTypes: true }); let sum = 0; for (const entry of entries) { const file = path.join(dir, entry.name); sum += entry.isDirectory() ? await mediaUsage(file) : (await fs.stat(file)).size; } return sum; } catch { return 0; }
}
export async function removeMedia(key: string) { await fs.rm(mediaPath(key), { force: true }); }
