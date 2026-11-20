# AGENTS.md

## 项目定位

AIGC Studio 是个人自托管的 AIGC 创作平台，用统一界面调用 Agnes 等外部服务，
沉淀任务、素材、参数和结果。当前为 FastAPI 单体应用 + SQLite + 本地媒体目录 +
Nginx Basic Auth，面向单用户、2C2G 服务器。不要引入 PostgreSQL、Redis、消息
队列、MinIO 等额外服务。

第一版接入 Agnes AI 三个模型（`agnes-3.0-flash` 文本、`agnes-image-2.5-flash`
图片、`agnes-video-2.5-flash` 视频）、小米 MiMo 两个 TTS 模型
（`mimo-v2.5-tts`、`mimo-v2.5-tts-voicedesign`）、Fish Audio `s2.1-pro-free`、
Breeze `breeze-tts-2` / `breeze-tts-2-multilingual`，以及 ModelScope
API-Inference 的 4 个图片模型（Qwen-Image-2.1[-Turbo]、MOSS-Image-SFT、
Z-Image-Turbo）。

## 技术栈与运行

- Python `>=3.11`，FastAPI + Uvicorn，Jinja2 + 原生 JS。
- SQLite 使用标准库 `sqlite3`，单连接 + 锁。
- 外部调用使用 httpx；密钥只从 `providers.yaml` 服务端读取。

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp providers.yaml.example providers.yaml
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 3000
.venv/bin/python -m pytest
```

- 纯 Python/FastAPI 项目，不再保留 Node.js/Next.js 代码或依赖。

## 核心约束

1. 仅个人使用：无账户、角色、注册；Nginx 统一认证。
2. 资源受限：控制内存、磁盘扫描和并发；默认单服务商并发 1。
3. 真实可用、低复杂度：优先核心链路可靠、可排障、可备份，避免过度抽象。

## 服务商插件架构（重点）

- 每个服务商是 `app/providers/<id>/` 下的独立包，暴露 `PROVIDER_DEFINITION`
  和 `create_adapter`。
- 启动时 `app/providers/__init__.py` 扫描并注册；新增/删除模块后调用
  `POST /api/settings/providers/reload` 即可热插拔。
- 适配器接口只有 `validate` / `submit` / `get_status`，详见
  `app/providers/README.md`。
- 任务、素材、API 层不得出现服务商特判；所有上游差异放适配器。
- 同步能力（文本、图片）在 `submit` 中直接返回结果；异步能力（视频）返回
  外部任务 ID，由应用内调度器轮询。

## 数据模型

SQLite 表：`providers`、`models`、`assets`、`tasks`、`task_assets`、
`reference_tokens`。建表在 `app/db.py`，所有 SQL 在 `app/repository.py`。
修改表结构时同步更新 `SCHEMA`、`repository` 查询和存量数据迁移。

任务状态固定为 `pending` / `running` / `succeeded` / `failed`，状态迁移只发生
在 `app/services/tasks.py`。页面和 API 不直接改状态。

连续对话用 `conversations` 表组织：每个文本任务带 `conversation_id`，适配器
收到完整 `messages` 历史（仅成功轮次）。图生图/文生图不需要公网 URL，视频
参考图仍需要。

## 开发约定

1. **输入校验**：API 用 pydantic 校验请求体、查询参数和文件元数据；上传校验
   MIME 与真实文件头（`app/services/media.py`）。
2. **媒体安全**：所有路径经 `MediaService.safe_key` 校验，确保不逃逸
   `MEDIA_ROOT`；结果下载限制 500 MB。
3. **密钥安全**：不打印配置对象和 Authorization；错误信息脱敏。
4. **类型优先**：不新增 `any`/`Any` 泛滥；对外响应先定义类型
   （`app/serializers.py`）。
5. **可测试性**：涉及任务、Provider、媒体的改动必须补测试，优先失败路径和
   并发路径。
6. **格式化**：按常规可读格式书写，不要把多步逻辑压缩成单行。

## 已知范围与后续

- 第一版聚焦核心链路；批量删除、模型参数可视化编辑暂缓。收藏/标签/画廊已实现。
- 轮询遇到瞬时上游错误（4xx/5xx/网络）会重试约 30 秒，仍失败才置 `failed`；`max_concurrency` 已生效。
- `mediaUsage()` 每次递归扫描目录，规模变大后需要缓存或增量统计。
- 旧 Next.js 实现已从仓库移除，不要在项目中重新引入 Node/Next 依赖。

## 敏感信息

不要提交真实 API Key、`.env*`、`providers.yaml`、数据库或媒体文件。应用监听
`127.0.0.1:3000`，公网必须经 Nginx；`/api/internal/poll` 保持本机限制。
