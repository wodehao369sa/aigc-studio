import { NextResponse } from "next/server";
import { listModels } from "@/lib/tasks";
export async function GET(request: Request) { return NextResponse.json(listModels(new URL(request.url).searchParams.get("capability") ?? undefined)); }
