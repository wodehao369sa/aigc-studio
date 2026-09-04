import { NextResponse } from "next/server";
import { pollOneTask } from "@/lib/tasks";
export const runtime = "nodejs";
// This route is reachable publicly only through the Nginx Basic Auth boundary.
export async function POST() { try { return NextResponse.json({ task: await pollOneTask() }); } catch (error) { return NextResponse.json({ error: error instanceof Error ? error.message : "轮询失败" }, { status: 500 }); } }
