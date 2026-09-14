import { NextResponse } from "next/server";
import { z } from "zod";
import { deleteTasks } from "@/lib/tasks";

export const runtime = "nodejs";

const bulkDeleteSchema = z.object({
  ids: z.array(z.string().min(1)).min(1).max(100)
});

export async function POST(request: Request) {
  try {
    const body = bulkDeleteSchema.parse(await request.json());
    await deleteTasks(body.ids);
    return NextResponse.json({ ok: true, count: body.ids.length });
  } catch (error) {
    const message = error instanceof z.ZodError
      ? error.issues.map((issue) => issue.message).join("；")
      : error instanceof Error ? error.message : "批量删除失败";
    return NextResponse.json({ error: message }, { status: 400 });
  }
}
