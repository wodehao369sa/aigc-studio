import { NextResponse } from "next/server";
import { deleteTask, getTask, listTaskAssets } from "@/lib/tasks";
export const runtime = "nodejs";
export async function GET(_: Request, { params }: { params: Promise<{ id: string }> }) { const task = getTask((await params).id); return task ? NextResponse.json({ ...task, assets: listTaskAssets(task.id) }) : NextResponse.json({ error: "任务不存在" }, { status: 404 }); }
export async function DELETE(_: Request, { params }: { params: Promise<{ id: string }> }) { await deleteTask((await params).id); return new Response(null, { status: 204 }); }
