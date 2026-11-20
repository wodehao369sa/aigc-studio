import { notFound } from "next/navigation";
import TaskDetail from "@/components/TaskDetail";
import { getTaskDetail } from "@/lib/tasks";

export const dynamic = "force-dynamic";

export default async function TaskPage({ params }: { params: Promise<{ id: string }> }) {
  const task = getTaskDetail((await params).id);
  if (!task) notFound();
  return <TaskDetail initialTask={task} />;
}
