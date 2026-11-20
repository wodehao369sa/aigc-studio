import { z } from "zod";
import Pagination from "@/components/Pagination";
import TaskList from "@/components/TaskList";
import { listTaskSummaries } from "@/lib/tasks";

export const dynamic = "force-dynamic";

const pageSchema = z.coerce.number().int().min(1).catch(1);

export default async function TasksPage({
  searchParams
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const rawPage = Array.isArray(params.page) ? params.page[0] : params.page;
  const page = pageSchema.parse(rawPage ?? 1);
  const result = listTaskSummaries({ page, pageSize: 20 });

  return (
    <>
      <section className="page-heading">
        <div>
          <p className="eyebrow">GENERATION HISTORY</p>
          <h1>任务记录</h1>
          <p>查看提示词、模型、生成状态和成功结果，并收藏常用内容。</p>
        </div>
      </section>
      <TaskList result={result} />
      <Pagination basePath="/tasks" page={result.page} pageSize={result.pageSize} total={result.total} />
    </>
  );
}
