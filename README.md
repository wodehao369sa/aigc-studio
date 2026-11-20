# AIGC Studio

个人自托管 AIGC 创作平台。FastAPI 单体应用 + SQLite + 本地媒体目录 + Nginx
Basic Auth，面向单用户、2C2G 服务器。服务商以可热插拔的 Provider 模块组织。

接入的服务商与模型：

**Agnes AI**

| 模型 | 能力 | 说明 |
| --- | --- | --- |
| `agnes-3.0-flash` | 文本生成 | `/v1/chat/completions`，同步返回文本 |
| `agnes-image-2.5-flash` | 文生图、图生图 | `/v1/images/generations`，支持 1K-4K 档位与宽高比 |
| `agnes-video-2.5-flash` | 文生视频、图生视频、首尾帧、图片参考 | `/v1/videos` 异步任务，720P |

**Xiaomi MiMo（语音合成）**

| 模型 | 能力 | 说明 |
| --- | --- | --- |
| `mimo-v2.5-tts` | 文本转语音 | 预置音色（mimo_default / 冰糖 / 茉莉 / 苏打 / 白桦 / Mia / Chloe / Milo / Dean） |
| `mimo-v2.5-tts-voicedesign` | 文本转语音 | 用文字描述设计音色，填写「音色与风格描述」 |

MiMo 使用 OpenAI 兼容的 `/v1/chat/completions`，认证头为 `api-key`，音频以
Base64 内联返回，同步生成。

**ModelScope API-Inference（图片）**

| 模型 | 能力 | 说明 |
| --- | --- | --- |
| `Qwen/Qwen-Image-2.1-Turbo` | 文生图、图生图 | 7B 加速版，8 步出图，支持多参考图编辑 |
| `Qwen/Qwen-Image-2.1` | 文生图、图生图 | 统一文生图/图像编辑，支持 RGBA 透明通道 |
| `Tongyi-MAI/Z-Image-Turbo` | 文生图 | 6B 蒸馏模型，风格多样、支持负向提示 |
| `openmoss/MOSS-Image-SFT` | 文生图 | 文本渲染、布局生成、长提示词 |

ModelScope 使用异步任务：`POST /v1/images/generations`（`X-ModelScope-Async-Mode: true`）
→ 轮询 `GET /v1/tasks/{id}`（`X-ModelScope-Task-Type: image_generation`），本地参考图以
Base64 Data URI 通过 `image_url` 提交。

## 技术栈

- Python 3.11+、FastAPI、Uvicorn
- Jinja2 服务端模板 + 原生 JS（无前端构建）
- SQLite（标准库 `sqlite3`）、本地文件系统媒体
- httpx 调用外部服务商
- systemd + Nginx 部署

## 本地运行

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp providers.yaml.example providers.yaml   # 填入 Agnes API Key
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 3000
```

打开 <http://127.0.0.1:3000>，在“设置 → 模型目录 → 添加模型”中选择 Agnes
预设模型。需要对外提供参考图时，设置 `PUBLIC_BASE_URL`。

## 服务商插件架构

代码按服务商拆分，新增或移除服务商不改任务、素材和 API 层：

```text
app/providers/
  base.py            # ProviderAdapter / ProviderDefinition / 运行时契约
  __init__.py        # 启动时扫描子目录并注册
  agnes/             # Agnes AI
    definition.py    # PROVIDER_DEFINITION + create_adapter
    adapter.py       # 请求映射、校验、状态归一化
    models.py        # 三个模型的预设参数
  xiaomi_mimo/       # 小米 MiMo TTS（结构相同）
  modelscope/        # ModelScope API-Inference（异步图片任务）
```

新增服务商只需复制 `agnes/` 目录、改名并实现 `definition.py`，然后调用
`POST /api/settings/providers/reload`。详见 `app/providers/README.md`。

## 任务与轮询

- `POST /api/tasks` 在短请求内完成校验、提交或记录同步结果，返回 `202`。
- 应用内后台调度器每 `POLL_INTERVAL_SECONDS` 秒轮询一个未完成任务；视频任务
  查询到结果后下载到本地媒体目录并转为 `succeeded`。
- `POST /api/internal/poll` 只允许本机调用，用于手动触发一次轮询。
- 每个服务商遵守 `max_concurrency`，默认 1，避免 2C2G 主机积压。
- 图片结果在 `media/thumbs/` 生成 480px JPEG 缩略图并缓存，列表和详情默认使用
  `/api/thumbnail/{id}`，原图仍通过 `/api/media/{id}` 提供（inline 预览 + 下载）。
- 图生图/文生图把参考图以 **Base64 Data URI** 直接提交，不需要公网 URL；
  视频参考图（图生视频/首尾帧/参考视频）必须是公网可访问的 URL，自签证书会
  导致 Agnes 下载失败，可参考 `deploy/aigc-studio-reference-80.conf`。
- 连续对话：`/conversations` 支持多轮对话，每轮是一个文本任务，自动携带
  历史消息；刷新页面会恢复未完成的轮次。

## 部署（Ubuntu + systemd + Nginx）

```bash
sudo useradd -r -m -d /opt/aigc-studio aigc
sudo -u aigc git clone <repo> /opt/aigc-studio
sudo -u aigc bash -c 'cd /opt/aigc-studio && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt'

sudo mkdir -p /etc/aigc-studio /var/lib/aigc-studio
sudo cp deploy/environment.example /etc/aigc-studio/environment
sudo cp providers.yaml /etc/aigc-studio/providers.yaml   # 含真实 Key
sudo chmod 640 /etc/aigc-studio/providers.yaml
sudo cp deploy/aigc-studio.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now aigc-studio
```

Nginx 使用 `deploy/nginx.conf`（HTTPS 8083 + Basic Auth），并将
`PUBLIC_BASE_URL` 设置为 `https://服务器公网IP:8083`。`/api/reference/` 由
Nginx 放行给 Agnes 读取临时参考图，`/api/internal/poll` 仅允许 127.0.0.1。

## 备份

```bash
./scripts/backup.sh /mnt/backup/aigc-studio
```

脚本用 SQLite 在线备份复制数据库，并打包媒体目录。恢复时停止应用，还原数据库
与媒体目录。

## 测试

```bash
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest
```

测试覆盖 Agnes 适配器（模拟上游）、任务状态机、并发上限、参考图 token、素材
上传校验和设置 API。

## 目录结构

```text
app/
  main.py              # FastAPI 应用与生命周期
  config.py            # 环境变量
  db.py                # SQLite 连接与建表
        repository.py      # 所有 SQL
  entities.py          # 领域 dataclass
  serializers.py       # 对外 JSON
  catalog.py           # 能力枚举
  providers/           # 可热插拔服务商模块
  routers/             # 页面与 API
  services/            # 媒体、素材、任务、设置、调度
  templates/ static/   # Jinja2 模板与原生 JS/CSS
tests/                 # pytest
deploy/ scripts/       # systemd、Nginx、备份
```
