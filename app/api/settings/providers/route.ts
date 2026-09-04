import { NextResponse } from "next/server";
import { sqlite } from "@/lib/db";
import { listProviders } from "@/lib/tasks";
export const runtime = "nodejs";
export async function GET() { return NextResponse.json(listProviders()); }
export async function PATCH(request: Request) { try { const body = await request.json(); sqlite.prepare("UPDATE providers SET enabled=?, max_concurrency=? WHERE id=?").run(body.enabled ? 1 : 0, Number(body.maxConcurrency ?? 1), body.id); return NextResponse.json({ ok: true }); } catch { return NextResponse.json({ error: "更新失败" }, { status: 400 }); } }
