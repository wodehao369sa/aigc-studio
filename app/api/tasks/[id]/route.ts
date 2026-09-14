import { NextResponse } from "next/server";
import { z } from "zod";
import { deleteTask, getTaskDetail, setTaskFavorite } from "@/lib/tasks";

export const runtime = "nodejs";

const favoriteSchema = z.object({ favorite: z.boolean() });

export async function GET(_: Request, { params }: { params: Promise<{ id: string }> }) {
  const task = getTaskDetail((await params).id);
  return task
    ? NextResponse.json(task)
    : NextResponse.json({ error: "任务不存在" }, { status: 404 });
}

export async function PATCH(request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const body = favoriteSchema.parse(await request.json());
    const task = setTaskFavorite((await params).id, body.favorite);
    return task
      ? NextResponse.json(task)
      : NextResponse.json({ error: "任务不存在" }, { status: 404 });
  } catch (error) {
    const message = error instanceof z.ZodError
      ? error.issues.map((issue) => issue.message).join("；")
      : error instanceof Error ? error.message : "更新失败";
    return NextResponse.json({ error: message }, { status: 400 });
  }
}

export async function DELETE(_: Request, { params }: { params: Promise<{ id: string }> }) {
  await deleteTask((await params).id);
  return new Response(null, { status: 204 });
}
