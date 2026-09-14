"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import FavoriteButton from "@/components/FavoriteButton";
import TaskThumbnail from "@/components/TaskThumbnail";
import type { TaskListResult, TaskSummary } from "@/lib/types";

const capabilityLabels: Record<TaskSummary["capability"], string> = {
  text_to_image: "文生图",
  image_to_image: "图生图",
  text_to_video: "文生视频",
  image_to_video: "图生视频",
  keyframe_video: "首尾帧视频",
  reference_video: "图片参考视频"
};

export default function TaskList({ result }: { result: TaskListResult }) {
  const [tasks, setTasks] = useState<TaskSummary[]>(result.items);
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [favoriteBusyId, setFavoriteBusyId] = useState<string | null>(null);

  useEffect(() => {
    setTasks(result.items);
    setSelected([]);
  }, [result.items]);

  const selectedTasks = useMemo(
    () => tasks.filter((task) => selected.includes(task.id)),
    [tasks, selected]
  );
  const all = tasks.length > 0 && selected.length === tasks.length;

  function toggle(id: string) {
    setSelected((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
  }

  function toggleAll() {
    setSelected(all ? [] : tasks.map((task) => task.id));
  }

  async function remove() {
    if (!selected.length || !confirm(`确定删除选中的 ${selected.length} 个任务吗？`)) return;
    setBusy(true);
    const response = await fetch("/api/tasks/bulk", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids: selected })
    });
    if (response.ok) {
      setTasks((current) => current.filter((task) => !selected.includes(task.id)));
      setSelected([]);
    } else {
      const data = await response.json();
      alert(data.error ?? "批量删除失败");
    }
    setBusy(false);
  }

  function download() {
    const outputs = selectedTasks.filter((task) => task.status === "succeeded" && task.resultAssetId);
    if (!outputs.length) {
      alert("选中的任务没有可下载结果。");
      return;
    }
    outputs.forEach((task, index) => {
      setTimeout(() => {
        const link = document.createElement("a");
        link.href = `/api/media/${task.resultAssetId}`;
        link.download = `aigc-${task.id}`;
        document.body.appendChild(link);
        link.click();
        link.remove();
      }, index * 180);
    });
  }

  async function toggleFavorite(task: TaskSummary) {
    const next = !task.isFavorite;
    setFavoriteBusyId(task.id);
    setTasks((current) => current.map((item) => item.id === task.id ? { ...item, isFavorite: next } : item));
    const response = await fetch(`/api/tasks/${task.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ favorite: next })
    });
    if (!response.ok) {
      setTasks((current) => current.map((item) => item.id === task.id ? { ...item, isFavorite: task.isFavorite } : item));
      alert("更新收藏状态失败。");
    }
    setFavoriteBusyId(null);
  }

  return (
    <>
      <div className="bulk-toolbar">
        <label className="select-all">
          <input type="checkbox" checked={all} onChange={toggleAll} />
          全选
        </label>
        <span>{selected.length ? `已选 ${selected.length} 项` : "请选择任务"}</span>
        <div className="actions">
          <button type="button" onClick={download} disabled={!selected.length || busy}>批量下载</button>
          <button type="button" className="danger-button" onClick={remove} disabled={!selected.length || busy}>批量删除</button>
        </div>
      </div>
      <div className="task-list">
        {tasks.length ? tasks.map((task) => (
          <div className="task-row task-row-selectable" key={task.id}>
            <input
              className="task-check"
              type="checkbox"
              checked={selected.includes(task.id)}
              onChange={() => toggle(task.id)}
              aria-label={`选择任务 ${task.id}`}
            />
            <Link href={`/tasks/${task.id}`} className="task-link">
              <TaskThumbnail
                resultAssetId={task.resultAssetId}
                resultMimeType={task.resultMimeType}
                alt={task.prompt ?? "生成结果"}
              />
              <div className="task-main">
                <div className="task-meta">
                  <span className={`status ${task.status}`}>{task.status}</span>
                  <strong>{task.modelName}</strong>
                  <span>{capabilityLabels[task.capability]}</span>
                </div>
                <p className="task-prompt">{task.prompt || "无提示词"}</p>
                <div className="task-footer">
                  <span>{new Date(task.createdAt).toLocaleString("zh-CN")}</span>
                  <span>{task.progress}%</span>
                </div>
              </div>
            </Link>
            <div className="task-side">
              <FavoriteButton
                favorite={task.isFavorite}
                busy={favoriteBusyId === task.id}
                compact
                onToggle={() => void toggleFavorite(task)}
              />
            </div>
          </div>
        )) : <p className="empty">还没有生成任务。</p>}
      </div>
    </>
  );
}
