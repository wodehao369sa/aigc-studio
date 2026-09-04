import { NextResponse } from "next/server";
import { retryTask } from "@/lib/tasks";
export const runtime = "nodejs";
export async function POST(_: Request, { params }: { params: Promise<{ id: string }> }) { try { return NextResponse.json(await retryTask((await params).id), { status: 202 }); } catch (error) { return NextResponse.json({ error: error instanceof Error ? error.message : "重试失败" }, { status: 400 }); } }
