import { z } from "zod";
import GalleryGrid from "@/components/GalleryGrid";
import Pagination from "@/components/Pagination";
import { listTaskSummaries } from "@/lib/tasks";

export const dynamic = "force-dynamic";

const pageSchema = z.coerce.number().int().min(1).catch(1);

export default async function GalleryPage({
  searchParams
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const rawPage = Array.isArray(params.page) ? params.page[0] : params.page;
  const page = pageSchema.parse(rawPage ?? 1);
  const result = listTaskSummaries({
    page,
    pageSize: 24,
    favoriteOnly: true,
    succeededOnly: true,
    orderBy: "favoritedAt"
  });

  return (
    <>
      <section className="page-heading">
        <div>
          <p className="eyebrow">FAVORITE GALLERY</p>
          <h1>收藏画廊</h1>
          <p>这里展示已收藏且成功生成的图片和视频。</p>
        </div>
      </section>
      <GalleryGrid items={result.items} />
      <Pagination basePath="/gallery" page={result.page} pageSize={result.pageSize} total={result.total} />
    </>
  );
}
