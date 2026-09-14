import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";

export const MEDIA_ROOT = path.resolve(process.env.MEDIA_ROOT ?? "./media");
export const WARN_BYTES = 4 * 1024 * 1024 * 1024;
export const LIMIT_BYTES = 5 * 1024 * 1024 * 1024;

const allowedExtensions = new Set([".png", ".jpg", ".jpeg", ".webp", ".mp4"]);

export async function ensureMediaRoot() {
  await fs.mkdir(MEDIA_ROOT, { recursive: true });
}

export function safeKey(key: string) {
  if (path.isAbsolute(key)) {
    throw new Error("非法媒体路径。");
  }

  const normalized = path.normalize(key.replace(/^\/+/, ""));
  if (
    !normalized ||
    normalized === "." ||
    normalized === ".." ||
    normalized.startsWith(`..${path.sep}`) ||
    path.isAbsolute(normalized)
  ) {
    throw new Error("非法媒体路径。");
  }

  const root = path.resolve(MEDIA_ROOT);
  const target = path.resolve(root, normalized);
  if (!target.startsWith(`${root}${path.sep}`)) {
    throw new Error("非法媒体路径。");
  }
  return normalized;
}

export function mediaPath(key: string) {
  return path.resolve(MEDIA_ROOT, safeKey(key));
}

export async function writeMedia(buffer: Buffer, originalName: string) {
  await ensureMediaRoot();
  const extension = path.extname(originalName).slice(0, 12).toLowerCase();
  const safeExtension = allowedExtensions.has(extension) ? extension : ".bin";
  const key = `${new Date().toISOString().slice(0, 10)}/${crypto.randomUUID()}${safeExtension}`;
  const file = mediaPath(key);
  await fs.mkdir(path.dirname(file), { recursive: true });
  await fs.writeFile(file, buffer);
  return key;
}

export async function mediaUsage(dir = MEDIA_ROOT): Promise<number> {
  try {
    const entries = await fs.readdir(dir, { withFileTypes: true });
    let sum = 0;
    for (const entry of entries) {
      const file = path.join(dir, entry.name);
      sum += entry.isDirectory() ? await mediaUsage(file) : (await fs.stat(file)).size;
    }
    return sum;
  } catch {
    return 0;
  }
}

export async function removeMedia(key: string) {
  await fs.rm(mediaPath(key), { force: true });
}
