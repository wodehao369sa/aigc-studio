import { listModels, listProviders } from "@/lib/tasks";
import SettingsClient from "@/components/SettingsClient";
export const dynamic = "force-dynamic";
export default function SettingsPage() { return <><section className="page-heading"><div><p className="eyebrow">LOCAL CONFIGURATION</p><h1>设置</h1><p>API 密钥只从服务器的 providers.yaml 读取，不会显示在这里。</p></div></section><SettingsClient providers={listProviders()} models={listModels(undefined, true)}/></>; }
