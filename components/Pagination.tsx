import Link from "next/link";

type Props = {
  basePath: string;
  page: number;
  pageSize: number;
  total: number;
};

export default function Pagination({ basePath, page, pageSize, total }: Props) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <nav className="pagination" aria-label="分页">
      {page > 1 ? (
        <Link href={`${basePath}?page=${page - 1}`}>上一页</Link>
      ) : (
        <span className="disabled">上一页</span>
      )}
      <span>
        第 {page} / {totalPages} 页 · 共 {total} 项
      </span>
      {page < totalPages ? (
        <Link href={`${basePath}?page=${page + 1}`}>下一页</Link>
      ) : (
        <span className="disabled">下一页</span>
      )}
    </nav>
  );
}
