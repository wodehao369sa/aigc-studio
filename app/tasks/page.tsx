import { listTasks } from "@/lib/tasks";
import TaskList from "@/components/TaskList";
export const dynamic = "force-dynamic";
export default function TasksPage() { const tasks = listTasks(); return <><section className="page-heading"><div><p className="eyebrow">GENERATION HISTORY</p><h1>任务记录</h1><p>成功、进行中和失败的生成任务都会保留在本机。</p></div></section><TaskList tasks={tasks}/></>; }
