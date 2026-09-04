import Link from "next/link";
import { listTasks } from "@/lib/tasks";
export const dynamic = "force-dynamic";
export default function TasksPage() { const tasks = listTasks(); return <><section className="page-heading"><div><p className="eyebrow">GENERATION HISTORY</p><h1>任务记录</h1><p>成功、进行中和失败的生成任务都会保留在本机。</p></div></section><div className="task-list">{tasks.length ? tasks.map((task) => <Link href={`/tasks/${task.id}`} className="task-row" key={task.id}><span className={`status ${task.status}`}>{task.status}</span><strong>{task.capability}</strong><span>{new Date(task.createdAt).toLocaleString("zh-CN")}</span><span>{task.progress}%</span></Link>) : <p className="empty">还没有生成任务。</p>}</div></>; }
