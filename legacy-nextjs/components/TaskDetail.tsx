"use client";

import { useEffect, useState } from "react";
import FavoriteButton from "@/components/FavoriteButton";
import type { TaskDetailRecord } from "@/lib/types";

export default function TaskDetail({ initialTask }: { initialTask: TaskDetailRecord }) {
  const [task, setTask] = useState<TaskDetailRecord>(initialTask);
  const [favoriteBusy, setFavoriteBusy] = useState(false);

  useEffect(() => {
    if (!["pending", "running"].includes(task.status)) return;
    const timer = setInterval(async () => {
      const response = await fetch(`/api/tasks/${task.id}`);
      if (response.ok) setTask(await response.json());
    }, 5000);
    return () => clearInterval(timer);
  }, [task.id, task.status]);

  async function retry() {
    const response = await fetch(`/api/tasks/${task.id}/retry`, { method: "POST" });
    const data = await response.json();
    if (response.ok) location.assign(`/tasks/${data.id}`);
    else alert(data.error ?? "重试失败");
  }

  async function remove() {
    if (!confirm("删除任务与无引用的媒体文件？")) return;
    await fetch(`/api/tasks/${task.id}`, { method: "DELETE" });
    location.assign("/tasks");
  }

  async function toggleFavorite() {
    const next = !task.isFavorite;
    setFavoriteBusy(true);
    setTask((current) => ({ ...current, isFavorite: next }));
    const response = await fetch(`/api/tasks/${task.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ favorite: next })
    });
    if (response.ok) {
      const detail = await response.json();
      setTask((current) => ({ ...current, ...detail }));
    } else {
      setTask((current) => ({ ...current, isFavorite: task.isFavorite }));
      alert("更新收藏状态失败。");
    }
    setFavoriteBusy(false);
  }

  const output = task.assets.find((item) => item.role === "output")?.asset;
  const prompt = typeof task.parameters.prompt === "string" ? task.parameters.prompt : "无提示词";

  return (
    <>
      <section className="page-heading">
        <div>
          <p className="eyebrow">TASK DETAIL</p>
          <h1>生成任务</h1>
          <p>
            <span className={`status ${task.status}`}>{task.status}</span>
            {task.progress}%{task.error ? ` · ${task.error}` : ""}
          </p>
        </div>
        <div className="actions">
          <FavoriteButton favorite={task.isFavorite} busy={favoriteBusy} onToggle={() => void toggleFavorite()} />
          {task.status === "failed" && <button type="button" onClick={() => void retry()}>重试</button>}
          <button type="button" className="danger-button" onClick={() => void remove()}>删除</button>
        </div>
      </section>
      {output ? (
        <section className="result">
          {output.mimeType.startsWith("video/") ? (
            <video src={`/api/media/${output.id}`} controls />
          ) : output.mimeType.startsWith("audio/") ? (
            <audio src={`/api/media/${output.id}`} controls />
          ) : (
            <img src={`/api/media/${output.id}`} alt="生成结果" />
          )}
          <a className="primary" href={`/api/media/${output.id}`} download>下载结果</a>
        </section>
      ) : (
        <section className="panel">
          <h2>等待结果</h2>
          <p>页面会自动刷新状态。关闭页面不影响服务器轮询任务。</p>
        </section>
      )}
      <section className="panel">
        <h2>任务信息</h2>
        <dl className="task-detail-meta">
          <div><dt>模型</dt><dd>{task.modelName}</dd></div>
          <div><dt>创建时间</dt><dd>{new Date(task.createdAt).toLocaleString("zh-CN")}</dd></div>
          <div><dt>完成时间</dt><dd>{task.completedAt ? new Date(task.completedAt).toLocaleString("zh-CN") : "未完成"}</dd></div>
        </dl>
        <h3>提示词</h3>
        <p className="task-detail-prompt">{prompt}</p>
      </section>
      <section className="panel">
        <h2>输入参数</h2>
        <pre>{JSON.stringify(task.parameters, null, 2)}</pre>
      </section>
    </>
  );
}
