"use strict";

const CAPABILITY_LABELS = {
  text_generation: "文本生成",
  text_to_image: "文生图",
  image_to_image: "图生图",
  text_to_video: "文生视频",
  image_to_video: "图生视频",
  keyframe_video: "首尾帧视频",
  reference_video: "图片参考视频",
};

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[ch]));
}

function formatTime(ms) {
  if (!ms) return "";
  const date = new Date(ms);
  const pad = (value) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

async function api(path, options = {}) {
  const response = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  if (response.status === 204) return null;
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || data.detail || "请求失败");
  return data;
}

async function uploadAsset(file) {
  const body = new FormData();
  body.append("file", file);
  const response = await fetch("/api/assets", { method: "POST", body });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || "上传失败");
  return data.id;
}

function readScriptJSON(id) {
  const node = document.getElementById(id);
  return node ? JSON.parse(node.textContent) : null;
}

// --- create form -------------------------------------------------------------

function initCreateForm() {
  const root = document.getElementById("create-form");
  if (!root) return;
  const models = JSON.parse(root.dataset.models);
  const labels = JSON.parse(root.dataset.labels);
  const workspaces = JSON.parse(root.dataset.workspaces);
  let capability = workspaces[0].modes[0];
  let modelId = "";
  const selectedFiles = {};

  const modelsFor = (cap) => models.filter((model) => model.capabilities.includes(cap));
  const selectedModel = () => {
    const matching = modelsFor(capability);
    return matching.find((model) => model.id === modelId) || matching[0];
  };
  const fileRoles = (cap) => {
    if (cap === "image_to_image" || cap === "image_to_video") return ["source_image"];
    if (cap === "keyframe_video") return ["first_frame", "last_frame"];
    if (cap === "reference_video") return ["reference_image"];
    return [];
  };
  const roleLabel = (role) => ({
    source_image: "源图片",
    first_frame: "首帧图片",
    last_frame: "尾帧图片",
    reference_image: "参考图片",
  }[role] || role);

  function fieldHTML(field) {
    const label = esc(field.label);
    const key = esc(field.key);
    const defaultValue = esc(field.default ?? "");
    if (field.type === "select") {
      const options = (field.options || [])
        .map((option) => `<option value="${esc(option)}"${option === field.default ? " selected" : ""}>${esc(option)}</option>`)
        .join("");
      return `<label>${label}<select name="${key}">${options}</select></label>`;
    }
    if (field.type === "textarea") {
      return `<label class="wide">${label}<textarea name="${key}"${field.required ? " required" : ""}>${defaultValue}</textarea></label>`;
    }
    const attrs = [
      `name="${key}"`,
      `value="${defaultValue}"`,
      field.required ? "required" : "",
      field.min != null ? `min="${field.min}"` : "",
      field.max != null ? `max="${field.max}"` : "",
    ].filter(Boolean).join(" ");
    const type = field.type === "number" ? "number" : "text";
    return `<label>${label}<input type="${type}" ${attrs} /></label>`;
  }

  function render() {
    const group = workspaces.find((workspace) => workspace.modes.includes(capability)) || workspaces[0];
    const matching = modelsFor(capability);
    const model = selectedModel();
    const roles = fileRoles(capability);

    const workspaceButtons = workspaces
      .map(
        (workspace) =>
          `<button type="button" class="workspace" data-mode="${workspace.modes[0]}" ` +
          `aria-pressed="${workspace.modes.includes(capability)}">${esc(workspace.label)}</button>`,
      )
      .join("");
    const capabilityOptions = group.modes
      .map(
        (mode) =>
          `<option value="${mode}"${mode === capability ? " selected" : ""}>` +
          `${esc(labels[mode] || mode)}</option>`,
      )
      .join("");
    const modelOptions = matching.length
      ? matching
          .map((item) => {
            const selected = model && item.id === model.id ? " selected" : "";
            const version = item.version ? ` · ${esc(item.version)}` : "";
            return `<option value="${item.id}"${selected}>${esc(item.name)}${version}</option>`;
          })
          .join("")
      : "<option value=\"\">暂无模型</option>";
    const parameterFields = model ? model.parameterSchema.map(fieldHTML).join("") : "";
    const fileFields = roles
      .map(
        (role) =>
          `<div class="file-field">
            <label>${roleLabel(role)}<input type="file" name="${role}" accept="image/png,image/jpeg,image/webp" /></label>
            <div class="file-preview" data-role="${role}" hidden>
              <button type="button" class="file-clear" data-role="${role}" title="移除">×</button>
              <img alt="${roleLabel(role)}预览" />
            </div>
          </div>`,
      )
      .join("");
    const emptyHint = !model
      ? '<p class="wide hint">暂无可用模型。<a href="/settings">前往服务与模型</a></p>'
      : "";

    root.innerHTML = `
      <form id="create" class="studio">
        <div class="segments">${workspaceButtons}</div>
        <div class="form-grid">
          <label>创作方式
            <select name="capability">${capabilityOptions}</select>
          </label>
          <label>模型
            <select name="modelId">${modelOptions}</select>
          </label>
          <label class="wide">提示词
            <textarea name="prompt" required placeholder="描述主体、动作、环境、镜头和风格"></textarea>
          </label>
          ${parameterFields}
          ${fileFields}
          ${emptyHint}
          <div class="actions wide"><button type="submit" class="primary" id="submit-task">开始生成</button></div>
          <p class="wide error" id="create-message" role="alert" hidden></p>
        </div>
      </form>`;
    restoreFiles();
    bind();
  }

  function restoreFiles() {
    Object.entries(selectedFiles).forEach(([role, file]) => {
      const input = root.querySelector(`input[type="file"][name="${role}"]`);
      if (!input) return;
      try {
        const transfer = new DataTransfer();
        transfer.items.add(file);
        input.files = transfer.files;
      } catch {
        /* older browsers: file cannot be restored */
      }
      const preview = root.querySelector(`.file-preview[data-role="${role}"]`);
      const image = preview ? preview.querySelector("img") : null;
      if (preview && image) {
        image.src = URL.createObjectURL(file);
        preview.hidden = false;
      }
    });
  }

  function bind() {
    root.querySelectorAll(".workspace").forEach((button) => {
      button.addEventListener("click", () => {
        const workspace = workspaces.find((item) => item.modes[0] === button.dataset.mode);
        const mode = workspace.modes.find((candidate) => modelsFor(candidate).length) || workspace.modes[0];
        capability = mode;
        modelId = "";
        render();
      });
    });
    const capabilitySelect = root.querySelector('[name="capability"]');
    if (capabilitySelect) {
      capabilitySelect.addEventListener("change", (event) => {
        capability = event.target.value;
        modelId = "";
        render();
      });
    }
    const modelSelect = root.querySelector('[name="modelId"]');
    if (modelSelect) {
      modelSelect.addEventListener("change", (event) => {
        modelId = event.target.value;
        render();
      });
    }
    const form = root.querySelector("#create");
    form.addEventListener("submit", submit);
    bindFileFields();
  }

  function bindFileFields() {
    root.querySelectorAll('input[type="file"][name]').forEach((input) => {
      input.addEventListener("change", () => {
        const role = input.getAttribute("name");
        const preview = root.querySelector(`.file-preview[data-role="${role}"]`);
        const image = preview ? preview.querySelector("img") : null;
        const file = input.files && input.files[0];
        if (file) selectedFiles[role] = file;
        else delete selectedFiles[role];
        if (preview && image) {
          if (file) {
            image.src = URL.createObjectURL(file);
            preview.hidden = false;
          } else {
            image.removeAttribute("src");
            preview.hidden = true;
          }
        }
      });
    });
    root.querySelectorAll(".file-clear").forEach((button) => {
      button.addEventListener("click", () => {
        const role = button.dataset.role;
        const input = root.querySelector(`input[type="file"][name="${role}"]`);
        const preview = root.querySelector(`.file-preview[data-role="${role}"]`);
        const image = preview ? preview.querySelector("img") : null;
        if (input) input.value = "";
        delete selectedFiles[role];
        if (image) image.removeAttribute("src");
        if (preview) preview.hidden = true;
      });
    });
  }

  function showMessage(message) {
    const node = root.querySelector("#create-message");
    node.textContent = message;
    node.hidden = !message;
  }

  async function submit(event) {
    event.preventDefault();
    const form = event.target;
    const model = selectedModel();
    if (!model) {
      showMessage("该能力暂无已启用模型，请前往设置添加。");
      return;
    }
    const submitButton = root.querySelector("#submit-task");
    submitButton.disabled = true;
    showMessage("");
    try {
      const assets = [];
      for (const role of fileRoles(capability)) {
        const input = form.querySelector(`[name="${role}"]`);
        const file = input && input.files && input.files[0];
        if (file && file.size) assets.push({ role, assetId: await uploadAsset(file) });
      }
      const parameters = {};
      for (const field of model.parameterSchema) {
        const input = form.querySelector(`[name="${field.key}"]`);
        const value = input ? input.value : undefined;
        if (value !== undefined && value !== null && value !== "") {
          parameters[field.key] = field.type === "number" ? Number(value) : value;
        }
      }
      const prompt = form.querySelector('[name="prompt"]').value;
      const task = await api("/api/tasks", {
        method: "POST",
        body: JSON.stringify({ modelId: model.id, capability, prompt, parameters, assets }),
      });
      window.location.assign(`/tasks/${task.id}`);
    } catch (error) {
      showMessage(error.message || "创建任务失败");
      submitButton.disabled = false;
    }
  }

  render();
}

// --- task detail -------------------------------------------------------------

function resultHTML(task) {
  const outputs = (task.assets || []).filter((item) => item.role === "output");
  const output =
    outputs.find((item) => item.asset.id === task.resultAssetId) || outputs[0];
  if (output) {
    const asset = output.asset;
    if (asset.mimeType.startsWith("video/")) {
      return `<video src="/api/media/${asset.id}" controls></video><div class="result-links"><a class="primary" href="/api/media/${asset.id}" download>下载原片</a></div>`;
    }
    if (asset.mimeType.startsWith("audio/")) {
      return `<audio src="/api/media/${asset.id}" controls></audio><div class="result-links"><a class="primary" href="/api/media/${asset.id}" download>下载原文件</a></div>`;
    }
    return `<a class="result-thumb-link" href="/api/media/${asset.id}" target="_blank" rel="noopener"><img class="result-thumb" src="/api/thumbnail/${asset.id}" alt="生成结果" /></a><div class="result-links"><a class="primary" href="/api/media/${asset.id}" download>下载原图</a></div>`;
  }
  if (task.resultText) {
    return `<div class="panel"><pre class="text-result">${esc(task.resultText)}</pre></div>`;
  }
  return '<div class="panel"><h2>等待结果</h2><p>页面会自动刷新状态。关闭页面不影响服务器轮询任务。</p></div>';
}

function initTaskDetail() {
  const node = document.getElementById("task-data");
  if (!node) return;
  let task = JSON.parse(node.textContent);
  const id = task.id;
  const resultSection = document.getElementById("result-section");

  function render(next) {
    const status = document.getElementById("task-status");
    status.textContent = next.status;
    status.className = `status ${next.status}`;
    document.getElementById("task-progress").textContent = `${next.progress}%`;
    const error = document.getElementById("task-error");
    if (error) error.textContent = next.error ? ` · ${next.error}` : "";
    const completed = document.getElementById("task-completed");
    if (completed && next.completedAt) completed.textContent = formatTime(next.completedAt);
    document.getElementById("retry-task").hidden = next.status !== "failed";
    resultSection.innerHTML = resultHTML(next);
  }

  async function refresh() {
    if (!["pending", "running"].includes(task.status)) return;
    try {
      task = await api(`/api/tasks/${id}`);
      render(task);
    } catch {
      /* keep polling */
    }
  }

  setInterval(refresh, 5000);

  document.getElementById("retry-task").addEventListener("click", async () => {
    if (!confirm("基于当前参数创建重试任务？")) return;
    try {
      const next = await api(`/api/tasks/${id}/retry`, { method: "POST" });
      location.assign(`/tasks/${next.id}`);
    } catch (error) {
      alert(error.message || "重试失败");
    }
  });

  document.getElementById("delete-task").addEventListener("click", async () => {
    if (!confirm("删除任务与无引用的媒体文件？")) return;
    await api(`/api/tasks/${id}`, { method: "DELETE" });
    location.assign("/tasks");
  });
}

// --- task list ---------------------------------------------------------------

function taskRowHTML(task) {
  const thumb =
    task.resultMimeType && task.resultMimeType.startsWith("image/") && task.resultAssetId
      ? `<img class="task-thumb-media" src="/api/thumbnail/${task.resultAssetId}" alt="${esc(task.prompt || "生成结果")}" loading="lazy" />`
      : `<span class="task-thumb-placeholder">${
          task.resultMimeType && task.resultMimeType.startsWith("video/") ? "视频" : task.resultText ? "文本" : "结果"
        }</span>`;
  return `
    <div class="task-row" data-task-id="${task.id}">
      <a class="task-link" href="/tasks/${task.id}">
        ${thumb}
        <div class="task-main">
          <div class="task-meta">
            <span class="status ${task.status}">${task.status}</span>
            <strong>${esc(task.modelName)}</strong>
            <span>${esc(CAPABILITY_LABELS[task.capability] || task.capability)}</span>
          </div>
          <p class="task-prompt">${esc(task.prompt || "无提示词")}</p>
          <div class="task-footer"><span>${formatTime(task.createdAt)}</span><span>${task.progress}%</span></div>
        </div>
      </a>
      <div class="task-side">
        ${task.status === "failed" ? `<button type="button" class="retry-task" data-id="${task.id}">重试</button>` : ""}
        <button type="button" class="danger-button delete-task" data-id="${task.id}">删除</button>
      </div>
    </div>`;
}

function initTaskList() {
  const list = document.getElementById("task-list");
  if (!list) return;
  const params = new URLSearchParams(location.search);
  const page = Number(params.get("page") || 1);
  const status = params.get("status") || "";
  const capability = params.get("capability") || "";

  function bindRows() {
    list.querySelectorAll(".delete-task").forEach((button) => {
      button.addEventListener("click", async () => {
        if (!confirm("删除任务与无引用的媒体文件？")) return;
        await api(`/api/tasks/${button.dataset.id}`, { method: "DELETE" });
        refresh();
      });
    });
    list.querySelectorAll(".retry-task").forEach((button) => {
      button.addEventListener("click", async () => {
        const next = await api(`/api/tasks/${button.dataset.id}/retry`, { method: "POST" });
        location.assign(`/tasks/${next.id}`);
      });
    });
  }

  async function refresh() {
    const query = new URLSearchParams({ page, pageSize: 20 });
    if (status) query.set("status", status);
    if (capability) query.set("capability", capability);
    try {
      const data = await api(`/api/tasks?${query.toString()}`);
      list.innerHTML = data.items.length
        ? data.items.map(taskRowHTML).join("")
        : '<p class="empty">还没有生成任务。</p>';
      bindRows();
    } catch {
      /* keep the last rendered list */
    }
  }

  bindRows();
  setInterval(refresh, 5000);
}

// --- settings ----------------------------------------------------------------

function initSettings() {
  const data = readScriptJSON("settings-data");
  if (!data) return;
  const providers = data.providers;
  const presets = data.presets;
  const connections = document.getElementById("connections");
  const modelsSection = document.getElementById("models");
  const tabConnections = document.getElementById("tab-connections");
  const tabModels = document.getElementById("tab-models");
  const form = document.getElementById("model-form");

  function switchTab(name) {
    const showConnections = name === "connections";
    connections.hidden = !showConnections;
    modelsSection.hidden = showConnections;
    tabConnections.setAttribute("aria-pressed", String(showConnections));
    tabModels.setAttribute("aria-pressed", String(!showConnections));
  }
  tabConnections.addEventListener("click", () => switchTab("connections"));
  tabModels.addEventListener("click", () => switchTab("models"));

  document.getElementById("reload-providers").addEventListener("click", async () => {
    if (!confirm("重新扫描 app/providers 并更新服务列表？")) return;
    await api("/api/settings/providers/reload", { method: "POST" });
    location.reload();
  });

  document.querySelectorAll(".provider-enabled").forEach((input) => {
    input.addEventListener("change", () => saveProvider(input.dataset.id));
  });
  document.querySelectorAll(".provider-concurrency").forEach((input) => {
    input.addEventListener("change", () => saveProvider(input.dataset.id));
  });

  async function saveProvider(id) {
    const enabled = document.querySelector(`.provider-enabled[data-id="${id}"]`).checked;
    const maxConcurrency = Number(document.querySelector(`.provider-concurrency[data-id="${id}"]`).value);
    try {
      await api("/api/settings/providers", {
        method: "PATCH",
        body: JSON.stringify({ id, enabled, maxConcurrency }),
      });
    } catch (error) {
      alert(error.message || "保存失败");
    }
  }

  function providerPresets(providerId) {
    const preset = presets.find((item) => item.providerId === providerId);
    return preset ? preset.models : [];
  }

  function allowedCapabilities(providerId) {
    const preset = presets.find((item) => item.providerId === providerId);
    return preset ? preset.capabilities : Object.keys(CAPABILITY_LABELS);
  }

  function showMessage(message) {
    const node = document.getElementById("settings-message");
    node.textContent = message || "";
  }

  function renderCapabilityCheckboxes(providerId, selected) {
    const container = document.getElementById("model-capabilities");
    container.innerHTML = allowedCapabilities(providerId)
      .map(
        (capability) =>
          `<label><input type="checkbox" value="${capability}"${(selected || []).includes(capability) ? " checked" : ""} />${esc(CAPABILITY_LABELS[capability] || capability)}</label>`,
      )
      .join("");
  }

  function renderPresetOptions(providerId, selected) {
    const select = document.getElementById("model-preset");
    const options = providerPresets(providerId);
    const field = document.getElementById("preset-field");
    if (!options.length) {
      field.hidden = true;
      return;
    }
    field.hidden = false;
    select.innerHTML =
      '<option value="">自定义模型</option>' +
      options
        .map(
          (model) =>
            `<option value="${esc(model.externalModelId)}"${model.externalModelId === selected ? " selected" : ""}>${esc(model.name)}</option>`,
        )
        .join("");
  }

  function refreshCustomFields() {
    const providerId = document.getElementById("model-provider").value;
    const presetId = document.getElementById("model-preset").value;
    const preset = providerPresets(providerId).find((model) => model.externalModelId === presetId);
    document.getElementById("model-external").readOnly = Boolean(preset);
    document.getElementById("capability-field").hidden = Boolean(preset);
    document.getElementById("schema-field").hidden = Boolean(preset);
    if (preset) {
      document.getElementById("model-external").value = preset.externalModelId;
      if (!document.getElementById("model-name").value) {
        document.getElementById("model-name").value = preset.name;
      }
    }
  }

  function openModelForm(model) {
    form.hidden = false;
    form.dataset.editing = model ? model.id : "";
    document.getElementById("model-form-title").textContent = model ? "编辑模型" : "添加模型";
    const providerSelect = document.getElementById("model-provider");
    providerSelect.value = model ? model.providerId : providers[0]?.id || "";
    providerSelect.disabled = Boolean(model);
    renderPresetOptions(providerSelect.value, model ? model.externalModelId : "");
    document.getElementById("model-name").value = model ? model.name : "";
    document.getElementById("model-external").value = model ? model.externalModelId : "";
    document.getElementById("model-description").value = model ? model.description || "" : "";
    document.getElementById("model-sort").value = model ? model.sortOrder : models.length;
    document.getElementById("model-enabled").checked = model ? model.enabled : true;
    renderCapabilityCheckboxes(providerSelect.value, model ? model.capabilities : []);
    document.getElementById("model-schema").value = JSON.stringify(
      model ? model.parameterSchema || [] : [],
      null,
      2,
    );
    refreshCustomFields();
    showMessage("");
    form.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  document.getElementById("add-model").addEventListener("click", () => openModelForm(null));
  document.querySelectorAll(".edit-model").forEach((button) => {
    button.addEventListener("click", () => {
      const model = data.models.find((item) => item.id === button.dataset.id);
      if (model) openModelForm(model);
    });
  });
  document.querySelectorAll(".delete-model").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!confirm("删除该模型？")) return;
      try {
        await api(`/api/settings/models?id=${encodeURIComponent(button.dataset.id)}`, { method: "DELETE" });
        location.reload();
      } catch (error) {
        showMessage(error.message || "删除失败。");
      }
    });
  });

  document.getElementById("model-provider").addEventListener("change", (event) => {
    renderPresetOptions(event.target.value, "");
    renderCapabilityCheckboxes(event.target.value, []);
    refreshCustomFields();
  });
  document.getElementById("model-preset").addEventListener("change", refreshCustomFields);
  document.getElementById("cancel-model").addEventListener("click", () => {
    form.hidden = true;
    delete form.dataset.editing;
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const providerId = document.getElementById("model-provider").value;
    const presetId = document.getElementById("model-preset").value || null;
    const preset = providerPresets(providerId).find((model) => model.externalModelId === presetId);
    let parameterSchema = [];
    if (!preset) {
      try {
        parameterSchema = JSON.parse(document.getElementById("model-schema").value || "[]");
      } catch {
        showMessage("参数定义不是有效的 JSON。");
        return;
      }
    }
    const capabilities = preset
      ? preset.capabilities
      : Array.from(document.querySelectorAll("#model-capabilities input:checked")).map((input) => input.value);
    const payload = {
      providerId,
      preset: presetId,
      name: document.getElementById("model-name").value,
      externalModelId: preset ? preset.externalModelId : document.getElementById("model-external").value,
      description: document.getElementById("model-description").value,
      capabilities,
      parameterSchema,
      enabled: document.getElementById("model-enabled").checked,
      sortOrder: Number(document.getElementById("model-sort").value || 0),
    };
    try {
      if (form.dataset.editing) {
        await api("/api/settings/models", {
          method: "PATCH",
          body: JSON.stringify({ ...payload, id: form.dataset.editing }),
        });
      } else {
        await api("/api/settings/models", { method: "POST", body: JSON.stringify(payload) });
      }
      location.reload();
    } catch (error) {
      showMessage(error.message || "保存失败。");
    }
  });
}

// --- conversations -----------------------------------------------------------

function initConversations() {
  const form = document.getElementById("new-conversation-form");
  if (!form) return;
  const message = document.getElementById("conversation-message");

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    message.hidden = true;
    try {
      const conversation = await api("/api/conversations", {
        method: "POST",
        body: JSON.stringify({
          modelId: document.getElementById("conversation-model").value,
          title: document.getElementById("conversation-title").value,
          systemPrompt: document.getElementById("conversation-system").value,
        }),
      });
      location.assign(`/conversations/${conversation.id}`);
    } catch (error) {
      message.textContent = error.message || "创建失败";
      message.hidden = false;
    }
  });
}

function initChat() {
  const data = readScriptJSON("chat-data");
  const list = document.getElementById("chat-messages");
  if (!data || !list) return;
  const conversationId = data.conversationId;
  const bubbleByMessage = new Map();
  let busy = false;

  function scrollBottom() {
    list.scrollTop = list.scrollHeight;
  }

  function makeBubble(role, content, status, createdAt) {
    const wrap = document.createElement("div");
    wrap.className = `chat-message ${role}`;
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.textContent = content || "";
    if (status === "pending") {
      const typing = document.createElement("span");
      typing.className = "typing";
      typing.textContent = " …";
      bubble.appendChild(typing);
    }
    if (status === "failed") bubble.classList.add("failed");
    if (role === "system") {
      wrap.appendChild(bubble);
      return wrap;
    }
    const inner = document.createElement("div");
    inner.className = "bubble-wrap";
    const meta = document.createElement("span");
    meta.className = "chat-meta";
    meta.textContent =
      (role === "user" ? "我" : "Agnes" + (status === "pending" ? " · 生成中" : "")) +
      (createdAt ? ` · ${formatTime(createdAt)}` : "");
    inner.appendChild(meta);
    inner.appendChild(bubble);
    wrap.appendChild(inner);
    return wrap;
  }

  function render() {
    list.innerHTML = "";
    bubbleByMessage.clear();
    if (!data.messages.length) {
      list.innerHTML = '<p class="hint chat-empty">开始对话吧。</p>';
      return;
    }
    data.messages.forEach((message) => {
      const node = makeBubble(message.role, message.content, message.status, message.createdAt);
      list.appendChild(node);
      bubbleByMessage.set(message, node.querySelector(".bubble"));
    });
    scrollBottom();
  }

  async function pollTask(taskId, bubble) {
    for (;;) {
      let task;
      try {
        task = await api(`/api/tasks/${taskId}`);
      } catch {
        await new Promise((resolve) => setTimeout(resolve, 3000));
        continue;
      }
      if (task.status === "succeeded") {
        bubble.textContent = task.resultText || "（无内容）";
        bubble.classList.remove("failed");
        scrollBottom();
        return;
      }
      if (task.status === "failed") {
        bubble.textContent = `生成失败：${task.error || "未知错误"}`;
        bubble.classList.add("failed");
        scrollBottom();
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, 3000));
    }
  }

  async function send(prompt) {
    if (busy) return;
    busy = true;
    const sendButton = document.getElementById("chat-send");
    sendButton.disabled = true;
    const hint = list.querySelector(".hint");
    if (hint) hint.remove();

    data.messages.push({ role: "user", content: prompt, createdAt: Date.now() });
    list.appendChild(makeBubble("user", prompt, null, Date.now()));

    const assistantMessage = { role: "assistant", content: "生成中…", status: "pending", createdAt: Date.now() };
    data.messages.push(assistantMessage);
    const assistantNode = makeBubble("assistant", "生成中…", "pending", Date.now());
    list.appendChild(assistantNode);
    bubbleByMessage.set(assistantMessage, assistantNode.querySelector(".bubble"));
    scrollBottom();

    try {
      const task = await api(`/api/conversations/${conversationId}/messages`, {
        method: "POST",
        body: JSON.stringify({ prompt, parameters: {} }),
      });
      assistantMessage.taskId = task.id;
      pollTask(task.id, assistantNode.querySelector(".bubble")).finally(() => {
        busy = false;
        sendButton.disabled = false;
      });
    } catch (error) {
      const bubble = assistantNode.querySelector(".bubble");
      bubble.textContent = error.message || "发送失败";
      bubble.classList.add("failed");
      busy = false;
      sendButton.disabled = false;
    }
  }

  document.getElementById("chat-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const input = document.getElementById("chat-prompt");
    const prompt = input.value.trim();
    if (!prompt) return;
    input.value = "";
    send(prompt);
  });
  document.getElementById("chat-prompt").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      event.target.form.requestSubmit();
    }
  });
  const chatInput = document.getElementById("chat-prompt");
  chatInput.addEventListener("input", () => {
    chatInput.style.height = "auto";
    chatInput.style.height = `${Math.min(chatInput.scrollHeight, 160)}px`;
  });
  document.getElementById("delete-conversation").addEventListener("click", async () => {
    if (!confirm("删除该对话及其所有消息任务？")) return;
    try {
      await api(`/api/conversations/${conversationId}`, { method: "DELETE" });
      location.assign("/conversations");
    } catch (error) {
      alert(error.message || "删除失败");
    }
  });

  render();
  data.messages.forEach((message) => {
    if (message.status === "pending" && message.taskId) {
      const bubble = bubbleByMessage.get(message);
      if (bubble) pollTask(message.taskId, bubble);
    }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initCreateForm();
  initTaskDetail();
  initTaskList();
  initSettings();
  initConversations();
  initChat();
});
