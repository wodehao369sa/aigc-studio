import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";

describe("task summaries and favorites", () => {
  let tempDir: string;
  let sqlite: typeof import("../lib/db")["sqlite"];
  let tasks: typeof import("../lib/tasks");
  let media: typeof import("../lib/media");

  beforeAll(async () => {
    vi.resetModules();
    tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "aigc-tasks-"));
    process.env.DATABASE_URL = path.join(tempDir, "test.db");
    process.env.MEDIA_ROOT = path.join(tempDir, "media");
    process.env.PROVIDERS_CONFIG_PATH = path.join(tempDir, "missing-providers.yaml");

    const dbModule = await import("../lib/db");
    sqlite = dbModule.sqlite;
    tasks = await import("../lib/tasks");
    media = await import("../lib/media");

    sqlite.prepare(`
      INSERT OR IGNORE INTO providers (id, provider_type, name, base_url, enabled, max_concurrency)
      VALUES ('agnes', 'agnes', 'Agnes', 'https://example.com', 1, 1)
    `).run();
    sqlite.prepare(`
      INSERT INTO models (
        id, provider_id, external_model_id, name, version, description,
        capabilities_json, parameter_schema_json, input_constraints_json, enabled, sort_order
      ) VALUES (?, ?, ?, ?, NULL, NULL, ?, '[]', '{}', 1, 0)
    `).run(
      "model-image",
      "agnes",
      "external-image",
      "测试图片模型",
      JSON.stringify(["text_to_image"])
    );
    sqlite.prepare(`
      INSERT INTO assets (id, storage_key, original_filename, mime_type, size_bytes, metadata_json, created_at)
      VALUES ('asset-output', '2026/test.png', 'test.png', 'image/png', 10, '{}', 300)
    `).run();

    const insertTask = sqlite.prepare(`
      INSERT INTO tasks (
        id, provider_id, model_id, capability, mode, parameters_json, status, progress,
        external_task_id, external_video_id, error, created_at, started_at, completed_at,
        parent_task_id, result_asset_id, is_favorite, favorited_at
      ) VALUES (?, 'agnes', 'model-image', 'text_to_image', NULL, ?, ?, ?, NULL, NULL, NULL, ?, NULL, ?, NULL, ?, ?, ?)
    `);
    insertTask.run("favorite-task", JSON.stringify({ prompt: "收藏的测试提示词" }), "succeeded", 100, 300, 400, "asset-output", 1, 500);
    insertTask.run("pending-task", JSON.stringify({ prompt: "进行中的测试提示词" }), "pending", 20, 200, null, null, 0, null);
    insertTask.run("unfavorite-task", JSON.stringify({ prompt: "未收藏的测试提示词" }), "succeeded", 100, 100, 200, null, 0, null);

    sqlite.prepare(`
      INSERT INTO task_assets (task_id, asset_id, role)
      VALUES ('favorite-task', 'asset-output', 'output')
    `).run();
  });

  afterAll(() => {
    sqlite.close();
    fs.rmSync(tempDir, { recursive: true, force: true });
  });

  it("returns prompt, model name, and output information in one summary query", () => {
    const result = tasks.listTaskSummaries();
    expect(result.total).toBe(3);
    expect(result.items[0]).toMatchObject({
      id: "favorite-task",
      prompt: "收藏的测试提示词",
      modelName: "测试图片模型",
      resultAssetId: "asset-output",
      resultMimeType: "image/png",
      isFavorite: true
    });
  });

  it("filters the gallery to favorite tasks with successful outputs", () => {
    const result = tasks.listTaskSummaries({
      favoriteOnly: true,
      succeededOnly: true,
      orderBy: "favoritedAt"
    });
    expect(result.items.map((item) => item.id)).toEqual(["favorite-task"]);
  });

  it("updates favorite state and returns task detail", () => {
    const favorited = tasks.setTaskFavorite("pending-task", true);
    expect(favorited).toMatchObject({ id: "pending-task", isFavorite: true });
    expect(favorited?.favoritedAt).toEqual(expect.any(Number));

    const gallery = tasks.listTaskSummaries({ favoriteOnly: true });
    expect(gallery.items.map((item) => item.id)).toContain("pending-task");

    const unfavorited = tasks.setTaskFavorite("pending-task", false);
    expect(unfavorited).toMatchObject({ id: "pending-task", isFavorite: false, favoritedAt: null });
    expect(tasks.setTaskFavorite("missing", true)).toBeUndefined();
  });

  it("returns a typed task detail with model name and assets", () => {
    const detail = tasks.getTaskDetail("favorite-task");
    expect(detail?.modelName).toBe("测试图片模型");
    expect(detail?.assets).toEqual([
      { role: "output", asset: expect.objectContaining({ id: "asset-output" }) }
    ]);
  });

  it("rejects media keys that escape the media root", () => {
    expect(() => media.mediaPath("../outside.png")).toThrow("非法媒体路径");
    expect(() => media.mediaPath("/absolute.png")).toThrow("非法媒体路径");
  });
});
