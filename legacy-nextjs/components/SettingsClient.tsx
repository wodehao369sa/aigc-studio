"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { capabilityLabels, providerCapabilities } from "@/lib/catalog";
import { findProviderModelModule, providerModelModules } from "@/lib/provider-modules";
import type { ModelRecord, ProviderRecord } from "@/lib/types";

export default function SettingsClient({ providers, models }: {
  providers: (ProviderRecord & { configured: boolean })[];
  models: ModelRecord[];
}) {
  const router = useRouter();
  const [tab, setTab] = useState<"connections" | "models">("connections");
  const [editing, setEditing] = useState<ModelRecord | null | undefined>();
  const [providerId, setProviderId] = useState(providers[0]?.id ?? "");
  const [modelModuleType, setModelModuleType] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const provider = providers.find((item) => item.id === providerId);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setMessage("");
    setBusy(true);
    try {
      let parameterSchema: unknown;
      try { parameterSchema = JSON.parse(String(form.get("parameters") || "[]")); }
      catch { throw new Error("参数定义不是有效的 JSON。"); }
      const selectedModule = provider
        ? findProviderModelModule(provider.providerType, String(form.get("modelModuleType") ?? modelModuleType))
        : undefined;
      const result = await fetch("/api/settings/models", {
        method: editing ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...editing, providerId, parameterSchema,
          modelModuleType: selectedModule?.type,
          name: form.get("name"), externalModelId: selectedModule?.externalModelId ?? form.get("externalModelId"),
          description: form.get("description"), enabled: form.has("enabled"),
          capabilities: selectedModule ? [selectedModule.capability] : form.getAll("capability"), sortOrder: Number(form.get("sortOrder"))
        })
      });
      if (!result.ok) throw new Error((await result.json()).error ?? "保存失败。");
      setEditing(undefined);
      router.refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "保存失败。");
    } finally {
      setBusy(false);
    }
  }

  async function remove(model: ModelRecord) {
    if (!window.confirm(`删除模型“${model.name}”？`)) return;
    setMessage("");
    setBusy(true);
    try {
      const result = await fetch(`/api/settings/models?id=${encodeURIComponent(model.id)}`, { method: "DELETE" });
      if (!result.ok) throw new Error((await result.json()).error ?? "删除失败。");
      if (editing?.id === model.id) setEditing(undefined);
      router.refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "删除失败。");
    } finally {
      setBusy(false);
    }
  }

  function open(model: ModelRecord | null) {
    setProviderId(model?.providerId ?? providers[0]?.id ?? "");
    const modelProvider = providers.find((item) => item.id === (model?.providerId ?? providers[0]?.id));
    const module = modelProvider && providerModelModules[modelProvider.providerType]?.find((item) => item.externalModelId === model?.externalModelId);
    setModelModuleType(module?.type ?? providerModelModules[modelProvider?.providerType ?? "xiaomi_mimo"]?.[0]?.type ?? "");
    setMessage("");
    setEditing(model);
  }

  return <div className="settings">
    <div className="segments" aria-label="配置分类">
      <button aria-pressed={tab === "connections"} onClick={() => setTab("connections")}>服务连接</button>
      <button aria-pressed={tab === "models"} onClick={() => setTab("models")}>模型目录</button>
    </div>
    {tab === "connections" ? <section>
      <h2>服务连接</h2>
      <p className="hint">连接地址和凭据由服务器的 <code>providers.yaml</code> 管理。</p>
      {providers.map((item) => <div className="catalog-row" key={item.id}>
        <div><strong>{item.name}</strong><br/><code>{item.baseUrl}</code></div>
        <span className="status">{!item.configured ? "缺少配置" : item.enabled ? "已配置" : "已停用"}</span>
      </div>)}
    </section> : <section>
      <div className="section-toolbar"><h2>模型目录</h2>
        <button className="primary" disabled={!providers.length || busy} onClick={() => open(null)}>添加模型</button>
      </div>
      {models.map((item) => <div className="catalog-row" key={item.id}>
        <div><strong>{item.name}</strong> · {item.enabled ? "已启用" : "已停用"}<br/>
          <code>{providers.find((provider) => provider.id === item.providerId)?.name ?? item.providerId} / {item.externalModelId}</code><br/>
          <small>{item.capabilities.map((value) => capabilityLabels[value]).join("、")}</small>
        </div>
        <div className="actions">
          <button disabled={busy} onClick={() => open(item)}>编辑</button>
          <button disabled={busy} onClick={() => void remove(item)}>删除</button>
        </div>
      </div>)}
      {message && editing === undefined && <p className="error" role="alert">{message}</p>}
      {!models.length && <p className="hint">暂无模型。</p>}
      {editing !== undefined && <form key={editing?.id ?? "new"} onSubmit={save} className="panel form-grid model-editor">
        <h2 className="wide">{editing ? "编辑模型" : "添加模型"}</h2>
        <label>服务<select value={providerId} disabled={Boolean(editing)} onChange={(event) => setProviderId(event.target.value)}>
          {providers.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
        </select></label>
        {provider && providerModelModules[provider.providerType]?.length ? <label>模型类型<select name="modelModuleType" value={modelModuleType} disabled={Boolean(editing)} onChange={(event) => setModelModuleType(event.target.value)}>
          {providerModelModules[provider.providerType]?.map((item) => <option key={item.type} value={item.type}>{item.label}</option>)}
        </select></label> : null}
        <label>显示名称<input name="name" defaultValue={editing?.name} required /></label>
        {!provider || !providerModelModules[provider.providerType]?.length ? <label>服务商模型 ID<input name="externalModelId" defaultValue={editing?.externalModelId} required /></label> : <label>服务商模型 ID<input value={findProviderModelModule(provider.providerType, modelModuleType)?.externalModelId ?? ""} readOnly /></label>}
        <label>排序<input name="sortOrder" type="number" min="0" max="99999" defaultValue={editing?.sortOrder ?? models.length} required /></label>
        {!provider || !providerModelModules[provider.providerType]?.length ? <fieldset className="wide" key={providerId}><legend>创作能力</legend>
          {provider && providerCapabilities[provider.providerType]?.map((value) => <label key={value}>
            <input name="capability" type="checkbox" value={value} defaultChecked={editing?.capabilities.includes(value)} />{capabilityLabels[value]}
          </label>)}
        </fieldset> : null}
        <label className="wide">说明<input name="description" defaultValue={editing?.description ?? ""} /></label>
        {!provider || !providerModelModules[provider.providerType]?.length ? <details className="wide"><summary>高级参数</summary>
          <label>参数定义（JSON）<textarea name="parameters" defaultValue={JSON.stringify(editing?.parameterSchema ?? [], null, 2)} /></label>
        </details> : null}
        <fieldset className="wide"><label><input name="enabled" type="checkbox" defaultChecked={editing?.enabled ?? true} />启用模型</label></fieldset>
        {message && <p className="error wide" role="alert">{message}</p>}
        <div className="actions wide"><button className="primary" disabled={busy}>保存</button>
          <button type="button" disabled={busy} onClick={() => setEditing(undefined)}>取消</button></div>
      </form>}
    </section>}
  </div>;
}
