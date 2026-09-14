"use client";

import Link from "next/link";
import { useState } from "react";
import FavoriteButton from "@/components/FavoriteButton";
import TaskThumbnail from "@/components/TaskThumbnail";
import type { TaskSummary } from "@/lib/types";

export default function GalleryGrid({ items }: { items: TaskSummary[] }) {
  const [galleryItems, setGalleryItems] = useState<TaskSummary[]>(items);
  const [favoriteBusyId, setFavoriteBusyId] = useState<string | null>(null);

  async function toggleFavorite(item: TaskSummary) {
    const next = !item.isFavorite;
    setFavoriteBusyId(item.id);
    setGalleryItems((current) => current.map((entry) => entry.id === item.id ? { ...entry, isFavorite: next } : entry));
    const response = await fetch(`/api/tasks/${item.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ favorite: next })
    });
    if (!response.ok) {
      setGalleryItems((current) => current.map((entry) => entry.id === item.id ? { ...entry, isFavorite: item.isFavorite } : entry));
      alert("更新收藏状态失败。");
    } else if (!next) {
      setGalleryItems((current) => current.filter((entry) => entry.id !== item.id));
    }
    setFavoriteBusyId(null);
  }

  if (!galleryItems.length) {
    return (
      <section className="panel gallery-empty">
        <h2>还没有收藏内容</h2>
        <p>在任务记录或任务详情中点击星标，成功生成的结果会出现在这里。</p>
      </section>
    );
  }

  return (
    <div className="gallery-grid">
      {galleryItems.map((item) => (
        <article className="gallery-card" key={item.id}>
          <Link href={`/tasks/${item.id}`} className="gallery-link">
            <TaskThumbnail
              resultAssetId={item.resultAssetId}
              resultMimeType={item.resultMimeType}
              alt={item.prompt ?? "收藏的生成结果"}
            />
            <div className="gallery-info">
              <strong>{item.modelName}</strong>
              <p>{item.prompt || "无提示词"}</p>
            </div>
          </Link>
          <div className="gallery-actions">
            <FavoriteButton
              favorite={item.isFavorite}
              busy={favoriteBusyId === item.id}
              compact
              onToggle={() => void toggleFavorite(item)}
            />
            {item.resultAssetId && (
              <a href={`/api/media/${item.resultAssetId}`} download aria-label="下载收藏结果">下载</a>
            )}
          </div>
        </article>
      ))}
    </div>
  );
}
