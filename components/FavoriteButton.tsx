"use client";

type Props = {
  favorite: boolean;
  busy?: boolean;
  compact?: boolean;
  onToggle: () => void;
};

export default function FavoriteButton({ favorite, busy = false, compact = false, onToggle }: Props) {
  return (
    <button
      type="button"
      className={`favorite-button${favorite ? " active" : ""}${compact ? " compact" : ""}`}
      onClick={onToggle}
      disabled={busy}
      aria-pressed={favorite}
      aria-label={favorite ? "取消收藏任务" : "收藏任务"}
      title={favorite ? "取消收藏" : "收藏"}
    >
      <span aria-hidden="true">{favorite ? "★" : "☆"}</span>
      {!compact && <span>{favorite ? "已收藏" : "收藏"}</span>}
    </button>
  );
}
