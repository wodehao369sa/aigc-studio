import { NextResponse } from "next/server";
import { createTask, listTasks } from "@/lib/tasks";
import { mediaUsage, LIMIT_BYTES } from "@/lib/media";
export const runtime = "nodejs";
export async function GET() { return NextResponse.json(listTasks()); }
export async function POST(request: Request) { try { if (await mediaUsage() >= LIMIT_BYTES) return NextResponse.json({ error: "媒体目录已达到 5 GB 上限，请先清理任务。" }, { status: 507 }); const body = await request.json(); const task = await createTask(body); return NextResponse.json(task, { status: 202 }); } catch (error) { return NextResponse.json({ error: error instanceof Error ? error.message : "创建失败" }, { status: 400 }); } }
