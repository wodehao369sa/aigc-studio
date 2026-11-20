import { NextResponse } from "next/server";
import { referenceAsset } from "@/lib/tasks";
export const runtime = "nodejs";
export async function GET(_: Request, { params }: { params: Promise<{ token: string }> }) { const asset = referenceAsset((await params).token); if (!asset) return new Response("Not found", { status: 404 }); const response = new NextResponse(null, { status: 200 }); response.headers.set("X-Accel-Redirect", `/_protected_media/${asset.storageKey}`); response.headers.set("Content-Type", asset.mimeType); response.headers.set("Cache-Control", "private, no-store"); return response; }
