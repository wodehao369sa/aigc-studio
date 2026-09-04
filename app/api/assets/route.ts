import { NextResponse } from "next/server";
import { createAsset } from "@/lib/tasks";
import { mediaUsage, LIMIT_BYTES } from "@/lib/media";
export const runtime = "nodejs";
export async function POST(request: Request) { try { if (await mediaUsage() >= LIMIT_BYTES) return NextResponse.json({ error: "媒体目录已达到 5 GB 上限，请先清理任务。" }, { status: 507 }); const file = (await request.formData()).get("file"); if (!(file instanceof File)) return NextResponse.json({ error: "缺少上传文件。" }, { status: 400 }); return NextResponse.json(await createAsset(file), { status: 201 }); } catch (error) { return NextResponse.json({ error: error instanceof Error ? error.message : "上传失败" }, { status: 400 }); } }
