# AGENTS.md

## 项目定位

AIGC Studio 是一个个人自托管的 AIGC 创作平台，用于调用 Agnes 与 ModelScope 生成图片和视频。当前版本面向单用户、小规模部署，采用 Next.js 单体应用、SQLite、本地媒体目录和 Nginx Basic Auth。不要默认引入 PostgreSQL、Redis、消息队列、MinIO 等额外服务；V1 的目标是轻量、可备份、易部署。

## 核心约束条件

1. **仅个人使用**：项目面向单人使用，不做多用户、注册、团队协作或数据隔离；若未来开放给多人，必须重新评估认证、权限、配额和安全边界。
2. **资源限制**：项目会部署在个人电脑或 2C2G 服务器上。所有设计都应控制 CPU、内存、磁盘扫描和并发开销；默认不要引入重量级服务或高内存依赖。
3. **真实可用、可靠且低复杂度**：优先保证核心链路真实可用、可靠、可排障、可备份；在满足这些目标的前提下保持实现简单直接，重构以减少实际故障点和维护成本为目标，避免堆叠抽象层和过度设计。

主要事实来源：

- `README.md`：本地运行、Ubuntu 部署、备份和端口边界。
- `AIGC_CREATIVE_PLATFORM_PRD.md`：产品需求、验收标准、资源预算和明确不做的范围。
- 本文件：代码结构、开发约定、当前已知问题和后续开发注意事项。

## 技术栈与运行方式

- Node.js `>=22 <25`，包管理器使用 pnpm `>=9`。
- Next.js 15 App Router + React 19，TypeScript 严格模式。
- SQLite：`better-sqlite3`，Drizzle ORM 已引入，但当前业务代码大量直接使用 raw SQL。
- 外部服务：Agnes（视频和部分图片能力）、ModelScope（异步图片生成）。
- 媒体：本地文件系统，默认 `./media`；生产环境为 `/var/lib/aigc-studio/media`。
- 部署：Next.js standalone 输出，systemd 运行应用和 5 秒轮询 timer，Nginx 提供 HTTPS 与 Basic Auth。

常用命令：

```bash
pnpm install
pnpm dev
pnpm test
pnpm build
pnpm poll              # 手动轮询一个外部任务
pnpm db:generate
pnpm db:migrate
```

注意：

- `pnpm lint` 目前会进入 Next.js 的交互式 ESLint 初始化流程，非交互环境下会失败；仓库尚无可用 ESLint 配置。不要把 `pnpm lint` 当作当前质量门禁。
- `pnpm test` 当前只有 5 个 Provider 校验测试；`pnpm build` 会执行类型检查。改动任务、API、数据库或 Provider 后，至少运行 `pnpm test` 和 `pnpm build`，并按需补充测试。

## 环境与敏感信息

本地需要：

- `.env.local`：可从 `.env.example` 复制，包含 `DATABASE_URL`、`MEDIA_ROOT`、`PUBLIC_BASE_URL`、`PROVIDERS_CONFIG_PATH`。
- `providers.yaml`：可从 `providers.yaml.example` 复制，包含外部服务 API Key。

生产环境需要：

- `/etc/aigc-studio/environment`
- `/etc/aigc-studio/providers.yaml`
- `/etc/aigc-studio/certs/server.crt` 和 `server.key`

硬性规则：

- 不要提交真实 API Key、`.env*`、`providers.yaml`、数据库文件或媒体文件。
- API Key 只允许在服务端读取，不要写入前端响应、普通日志或错误信息。
- 应用监听 `127.0.0.1:3000`，公网访问必须经过 Nginx；不要开放 3000 端口。
- `/api/internal/poll` 只应由本机 systemd timer 调用，必须保持网络限制。

## 文件组织

```text
AIGC_CREATIVE_PLATFORM_PRD.md  产品需求与验收标准
README.md                      运行、部署、备份说明
app/                           Next.js App Router 页面和 API
  page.tsx                     创作页
  tasks/page.tsx               任务列表
  tasks/[id]/page.tsx          任务详情
  settings/page.tsx            服务与模型设置
  api/assets/                  上传参考图片
  api/tasks/                   任务创建、查询、删除、重试、批量删除
  api/settings/                Provider 与模型配置
  api/media/[id]/              从本地媒体目录读取结果
  api/reference/[token]/       给 Agnes 读取参考图的临时 token URL
  api/internal/poll/           本机轮询入口
components/                    客户端组件
lib/
  config.ts                    读取 providers.yaml 和服务凭据
  db/index.ts                  SQLite 初始化与连接
  db/schema.ts                 部分 Drizzle 表定义
  media.ts                     媒体写入、路径、容量统计
  tasks.ts                     当前核心业务逻辑
  providers/                   Provider Adapter 与外部 API 映射
  types.ts                     能力、状态、任务、模型等类型
scripts/                       部署、轮询、备份脚本
deploy/                        systemd 与 Nginx 示例配置
tests/                         Vitest 测试
data/                          运行时 SQLite 数据库（不入库）
media/                         运行时媒体文件（不入库）
.next/                         构建产物（不入库）
```

## 核心数据流

1. 用户在创作页选择能力与模型，上传参考图，提交提示词和参数。
2. `POST /api/assets` 先保存上传图片并创建 `assets` 记录。
3. `POST /api/tasks` 在 `lib/tasks.ts` 中：
   - 校验模型能力、Provider 状态、素材和 Adapter 参数；
   - 为 Agnes 生成 24 小时有效的 `reference_tokens`；
   - 写入 `tasks` 与 `task_assets`；
   - 调用 Provider Adapter 提交外部任务；
   - 成功时保存外部任务 ID 并置为 `running`，失败时置为 `failed`。
4. systemd timer 每 5 秒调用一次 `POST /api/internal/poll`。
5. `pollOneTask()` 查询最早一个未完成任务，成功后下载结果到本地媒体目录，创建输出 Asset，并将任务置为 `succeeded`。
6. 前端任务详情页每 5 秒轮询应用内任务状态。

## 数据模型

当前 SQLite 表：

- `providers`：服务实例、类型、Base URL、启用状态、最大并发。
- `models`：模型配置、能力 JSON、参数 schema JSON、输入约束 JSON、排序与启用状态。
- `assets`：上传或生成结果文件。
- `tasks`：任务状态、外部任务 ID、参数快照、时间、父任务和输出 Asset。
- `task_assets`：任务与素材的多对多关系及角色。
- `reference_tokens`：给外部 Provider 使用的临时素材访问 token。

重点问题：`lib/db/schema.ts` 只定义了 `providers`、`models`、`assets`、`tasks`，未定义 `task_assets` 和 `reference_tokens`；实际建表逻辑在 `lib/db/index.ts` 的 raw SQL 中。修改表结构时必须同时考虑 `schema.ts`、`initializeDatabase()`、已有数据迁移和 API 查询，避免三处漂移。

## 功能点

已实现的主要功能：

- 创作页能力切换：文生图、图生图、文生视频、图生视频、首尾帧视频、图片参考视频。
- 根据模型 `parameterSchema` 渲染动态参数表单。
- PNG/JPEG/WebP 参考图上传，单文件 20 MB 限制。
- 媒体目录 4 GB 警告、5 GB 上限。
- Agnes Provider Adapter：
  - 视频 2.x 的模式、时长/帧数、分辨率、画幅和图片角色校验；
  - 图片生成和视频异步任务提交与状态查询；
  - 通过临时 token URL 提供参考图。
- ModelScope Provider Adapter：
  - 文生图、图生图；
  - 异步任务创建与状态查询；
  - 参考图转 Base64。
- 任务列表、任务详情、状态展示、自动刷新、失败重试、单删与批量删除。
- 成功结果的图片/视频预览和下载。
- 设置页可查看 Provider 状态、添加模型、启用/禁用模型。
- systemd timer 轮询、standalone 构建部署脚本、数据库和媒体备份脚本。

## 当前不合理或高风险之处

以下问题应在后续开发中优先处理，开发新功能时不要继续扩大这些债务。

### 1. 业务逻辑与数据访问过度集中

`lib/tasks.ts` 同时承担查询、任务状态机、素材、token、Provider 调用、结果下载、删除和重试逻辑。大量逻辑压缩在超长单行中，可读性和可测试性差。`listTasks()`、`listTaskAssets()`、`getModel()` 等还存在明显 N+1 查询。建议逐步拆分为 repository、task service、asset service、provider orchestration，并保持函数短小。

### 2. Drizzle 与 raw SQL 混用且 schema 不完整

`initializeDatabase()` 使用 raw SQL 建表，`drizzle.config.ts` 指向的 `schema.ts` 缺少两张关系表。表间没有外键约束，删除逻辑依赖应用代码。后续应统一迁移策略，补全 schema，并为生产数据提供可重复执行的迁移。

### 3. API 输入校验不足

项目依赖了 `zod`，但 API 基本未使用。`POST/PATCH` 直接信任请求体，存在隐式类型转换、空值、非法 JSON、未知字段和不存在 ID 的问题。尤其 `PATCH /api/settings/models` 没有检查更新行数。应先为创建任务、上传、设置模型、批量删除等入口建立 Zod schema。

### 4. 任务状态机不够健壮

- `providers.max_concurrency` 保存了但创建任务时没有生效。
- 外部提交失败会被记录为失败任务，但仍以 HTTP 202 返回，语义容易混淆。
- 轮询中的网络抖动、超时或临时 5xx 会立即把任务置为失败，没有重试次数、退避或区分“未知状态”。
- `pollOneTask()` 一次只轮询一个任务，且 `pending` 但没有 `external_task_id` 的任务永远不会被处理。
- 没有 stale task 检测和恢复策略。
- 外部 `fetch` 没有 timeout/AbortController，可能长时间阻塞。

### 5. 上传与媒体生命周期有泄漏风险

上传发生在创建任务之前。如果用户上传后放弃提交，或任务创建失败，Asset 会成为孤儿。当前没有清理任务，也没有 `source_task_id`/引用计数设计。媒体容量检查存在并发竞态，`mediaUsage()` 每次递归扫描整个目录，规模增长后会成为性能问题。

### 6. 文件处理安全性和资源占用不足

- MIME 类型信任浏览器 `file.type`，未校验文件魔数。
- 扩展名来自原始文件名，未严格限制为 `.png`、`.jpg`、`.jpeg`、`.webp`。
- `safeKey()` 只过滤非法字符和前导 `/`，没有显式拒绝 `..`；虽然当前 key 多由服务端生成，仍应改为白名单并验证最终路径始终位于 `MEDIA_ROOT` 内。
- 上传和结果下载均一次性读入内存 `Buffer`，大视频可能导致 512 MB systemd 限制下内存尖峰。
- 结果 URL 下载未限制大小和目标协议，也未校验响应内容。

### 7. 动态模型配置没有真正完成

设置页新增模型时 `parameterSchema` 固定提交为空数组，导致创作页无法显示该模型参数。PRD 要求新增、修改、排序或禁用模型后前台无需改代码，但当前设置页也不支持编辑参数 schema、修改模型 ID、排序或删除模型。后续应设计安全的 schema 编辑器或预设模板。

### 8. 前端工程质量不足

组件大量单行压缩，`TaskDetail` 使用 `any`，错误处理和加载状态不完整。表单切换能力后模型选择、文件字段和参数校验之间缺少清晰联动。应优先恢复常规格式化、补类型、提取小组件，再扩展功能。

### 9. 测试与观测性不足

当前测试只覆盖少量 Provider 校验，没有 API、任务状态机、数据库、媒体路径、上传/删除/重试的测试。缺少健康检查端点、结构化日志、请求 ID、外部调用耗时和失败计数。排障基本只能依赖 Nginx 和 systemd 日志。

### 10. 部署配置存在多版本和不一致

仓库同时存在 `deploy/nginx.conf`（8083 HTTPS）、`deploy/aigc-studio-443.conf`（443 HTTPS）和 `deploy/aigc-studio-reference-80.conf`（80 仅参考图）。`deploy/environment.example` 的 `PUBLIC_BASE_URL` 是 HTTPS，但 reference-80 方案暗示部分外部读取使用 HTTP。后续必须明确唯一生产拓扑，并让文档、Nginx、环境变量和 Agnes 可访问 URL 完全一致。PRD 写的是 Docker Compose，而当前实现是 systemd + Nginx，这也应在 PRD 或 README 中统一说明。

## 开发约定

1. **保持单体轻量**：默认在现有 Next.js 应用内实现；新增服务必须先证明瓶颈并征得明确决策。
2. **Provider 隔离**：外部 API 差异只放在 `lib/providers/*`，不要在页面或通用任务逻辑里写平台特判。新增 Provider 时实现 `ProviderAdapter`。
3. **类型优先**：不要新增 `any`；对外 API 响应先定义类型。
4. **输入验证**：所有新 API 使用 Zod 验证请求体、查询参数和文件元数据。
5. **状态机清晰**：不要在页面组件里推导或修改任务状态；状态迁移集中在服务层。
6. **数据库变更**：同步更新 `schema.ts`、初始化/迁移 SQL 和存量数据兼容方案，并补充测试。
7. **媒体安全**：所有文件路径必须经过严格校验并确保不会逃逸 `MEDIA_ROOT`；避免无上限读取内存。
8. **密钥安全**：不打印配置对象和 Authorization 头；错误信息要脱敏。
9. **可测试性**：涉及任务、Provider、媒体的改动必须补测试；优先覆盖失败路径和并发路径。
10. **格式化**：不要继续把多步逻辑压缩成单行；新代码按常规可读格式书写。
