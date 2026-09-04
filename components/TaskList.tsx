"use client";
import Link from "next/link";
import { useMemo, useState } from "react";
import type { TaskRecord } from "@/lib/types";

export default function TaskList({ tasks }: { tasks: TaskRecord[] }) {
  const [selected, setSelected] = useState<string[]>([]); const [busy, setBusy] = useState(false);
  const selectedTasks = useMemo(() => tasks.filter(t => selected.includes(t.id)), [tasks, selected]);
  const all = tasks.length > 0 && selected.length === tasks.length;
  function toggle(id: string) { setSelected(v => v.includes(id) ? v.filter(x => x !== id) : [...v, id]); }
  function toggleAll() { setSelected(all ? [] : tasks.map(t => t.id)); }
  async function remove() { if (!selected.length || !confirm(`确定删除选中的 ${selected.length} 个任务吗？`)) return; setBusy(true); const r = await fetch("/api/tasks/bulk", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ids: selected }) }); if (r.ok) location.reload(); else { const d = await r.json(); alert(d.error ?? "批量删除失败"); setBusy(false); } }
  function download() { const outputs = selectedTasks.filter(t => t.status === "succeeded" && t.resultAssetId); if (!outputs.length) { alert("选中的任务没有可下载结果。"); return; } outputs.forEach((t, i) => setTimeout(() => { const a = document.createElement("a"); a.href = `/api/media/${t.resultAssetId}`; a.download = `aigc-${t.id}`; document.body.appendChild(a); a.click(); a.remove(); }, i * 180)); }
  return <>
    <div className="bulk-toolbar"><label className="select-all"><input type="checkbox" checked={all} onChange={toggleAll} /> 全选</label><span>{selected.length ? `已选 ${selected.length} 项` : "请选择任务"}</span><div className="actions"><button type="button" onClick={download} disabled={!selected.length || busy}>批量下载</button><button type="button" className="danger-button" onClick={remove} disabled={!selected.length || busy}>批量删除</button></div></div>
    <div className="task-list">{tasks.length ? tasks.map(task => <div className="task-row task-row-selectable" key={task.id}><input className="task-check" type="checkbox" checked={selected.includes(task.id)} onChange={() => toggle(task.id)} aria-label={`选择任务 ${task.id}`} /><Link href={`/tasks/${task.id}`} className="task-link"><span className={`status ${task.status}`}>{task.status}</span><strong>{task.capability}</strong><span>{new Date(task.createdAt).toLocaleString("zh-CN")}</span><span>{task.progress}%</span></Link></div>) : <p className="empty">还没有生成任务。</p>}</div>
  </>;
}
