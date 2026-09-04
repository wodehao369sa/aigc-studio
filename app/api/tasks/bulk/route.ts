import { NextResponse } from "next/server";
import { deleteTasks } from "@/lib/tasks";
export const runtime = "nodejs";
export async function POST(request: Request) {
  try {
    const body = await request.json();
    const ids = Array.isArray(body.ids) ? body.ids.filter((id: unknown): id is string => typeof id === "string") : [];
    if (!ids.length || ids.length > 100) return NextResponse.json({ error: "请选择要删除的任务。" }, { status: 400 });
    await deleteTasks(ids);
    return NextResponse.json({ ok: true, count: ids.length });
  } catch (error) { return NextResponse.json({ error: error instanceof Error ? error.message : "批量删除失败" }, { status: 400 }); }
}
