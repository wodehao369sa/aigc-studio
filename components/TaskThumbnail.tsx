import type { TaskSummary } from "@/lib/types";

export default function TaskThumbnail({
  resultAssetId,
  resultMimeType,
  alt
}: Pick<TaskSummary, "resultAssetId" | "resultMimeType"> & { alt: string }) {
  if (!resultAssetId) {
    return <div className="task-thumb-placeholder">待生成</div>;
  }

  if (resultMimeType?.startsWith("video/")) {
    return (
      <video
        className="task-thumb-media"
        src={`/api/media/${resultAssetId}`}
        preload="metadata"
        muted
        playsInline
        aria-label={alt}
      />
    );
  }

  return (
    <img
      className="task-thumb-media"
      src={`/api/media/${resultAssetId}`}
      alt={alt}
      loading="lazy"
      decoding="async"
    />
  );
}
