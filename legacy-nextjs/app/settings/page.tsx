import { listModels, listProviders } from "@/lib/tasks";
import { loadProviderConfig } from "@/lib/config";
import SettingsClient from "@/components/SettingsClient";
export const dynamic = "force-dynamic";
export default function SettingsPage() { return <><section className="page-heading"><div><p className="eyebrow">LOCAL CONFIGURATION</p><h1>服务与模型</h1><p>API 密钥只从服务器的 providers.yaml 读取，不会显示在这里。</p></div></section><SettingsClient providers={listProviders().map((provider) => ({ ...provider, configured: loadProviderConfig().providers.some((item) => item.type === provider.providerType && Boolean(item.apiKey) && !item.apiKey.startsWith("REPLACE_WITH")) }))} models={listModels(undefined, true)}/></>; }
