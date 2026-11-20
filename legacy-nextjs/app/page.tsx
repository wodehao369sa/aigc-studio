import { listModels } from "@/lib/tasks";
import { mediaUsage, WARN_BYTES, LIMIT_BYTES } from "@/lib/media";
import CreateForm from "@/components/CreateForm";
export const dynamic = "force-dynamic";
export default async function Home() { const [models, usage] = await Promise.all([Promise.resolve(listModels()), mediaUsage()]); return <><section className="page-heading"><div><p className="eyebrow">PERSONAL CREATIVE WORKSPACE</p><h1>开始创作</h1><p>选择模型、输入提示词并保存每一次生成结果。</p></div><div className={`storage ${usage >= LIMIT_BYTES ? "danger" : usage >= WARN_BYTES ? "warn" : ""}`}>媒体使用量 {formatBytes(usage)} / 5 GB<br/><small>{usage >= LIMIT_BYTES ? "已达到上限，请先删除任务或素材。" : usage >= WARN_BYTES ? "接近上限，请及时清理不需要的结果。" : "本地媒体目录正常。"}</small></div></section><CreateForm models={models} disabled={usage >= LIMIT_BYTES}/></>; }
function formatBytes(bytes: number) { return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`; }
