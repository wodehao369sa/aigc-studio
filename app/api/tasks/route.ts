import { NextResponse } from "next/server";
import { z } from "zod";
import { mediaUsage, LIMIT_BYTES } from "@/lib/media";
import { createTask, listTaskSummaries } from "@/lib/tasks";
import { CAPABILITIES } from "@/lib/types";

export const runtime = "nodejs";

const listQuerySchema = z.object({
  page: z.coerce.number().int().min(1).default(1),
  pageSize: z.coerce.number().int().min(1).max(100).default(20),
  favorite: z.enum(["true", "false"]).optional().transform((value) => value === "true"),
  succeeded: z.enum(["true", "false"]).optional().transform((value) => value === "true"),
  status: z.enum(["pending", "running", "succeeded", "failed"]).optional(),
  capability: z.enum(CAPABILITIES).optional(),
  orderBy: z.enum(["createdAt", "favoritedAt"]).optional()
});

const createTaskSchema = z.object({
  modelId: z.string().min(1),
  capability: z.enum(CAPABILITIES),
  mode: z.string().min(1).optional(),
  prompt: z.string().min(1),
  parameters: z.record(z.unknown()).default({}),
  assets: z.array(z.object({
    role: z.string().min(1),
    assetId: z.string().min(1)
  })).max(8).default([])
});

function searchParamsObject(url: URL) {
  return Object.fromEntries(url.searchParams.entries());
}

function errorMessage(error: unknown, fallback: string) {
  if (error instanceof z.ZodError) {
    return error.issues.map((issue) => `${issue.path.join(".") || "请求参数"}: ${issue.message}`).join("；");
  }
  return error instanceof Error ? error.message : fallback;
}

export async function GET(request: Request) {
  try {
    const query = listQuerySchema.parse(searchParamsObject(new URL(request.url)));
    return NextResponse.json(listTaskSummaries(query));
  } catch (error) {
    return NextResponse.json({ error: errorMessage(error, "查询失败") }, { status: 400 });
  }
}

export async function POST(request: Request) {
  try {
    if (await mediaUsage() >= LIMIT_BYTES) {
      return NextResponse.json({ error: "媒体目录已达到 5 GB 上限，请先清理任务。" }, { status: 507 });
    }
    const body = await request.json();
    const input = createTaskSchema.parse(body);
    const task = await createTask(input);
    return NextResponse.json(task, { status: 202 });
  } catch (error) {
    return NextResponse.json({ error: errorMessage(error, "创建失败") }, { status: 400 });
  }
}
