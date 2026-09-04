import { notFound } from "next/navigation";
import { getTask, listTaskAssets } from "@/lib/tasks";
import TaskDetail from "@/components/TaskDetail";
export const dynamic = "force-dynamic";
export default async function TaskPage({ params }: { params: Promise<{ id: string }> }) { const task = getTask((await params).id); if (!task) notFound(); return <TaskDetail initialTask={{ ...task, assets: listTaskAssets(task.id) }}/>; }
