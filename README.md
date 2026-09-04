# AIGC Studio

个人自托管 AIGC 创作平台：Agnes Video 2.5 和 ModelScope 图像生成，单用户、SQLite、本地媒体目录与 Nginx Basic Auth。

## 本地运行

1. `cp .env.example .env.local`，按需修改数据库、媒体目录和公网 URL。
2. `cp providers.yaml.example providers.yaml`，写入 API Key；生产环境使用 `/etc/aigc-studio/providers.yaml` 并设置权限为 `0640`。
3. `pnpm install && pnpm dev`。
4. 在“设置”添加 ModelScope 图像模型及 Agnes `agnes-video-2.5` 模型。

## Ubuntu 部署

以 `aigc` 用户安装项目到 `/opt/aigc-studio`，运行 `pnpm install && pnpm build`。standalone 运行时由构建产物提供，因此构建完成后可删除开发依赖。复制 `deploy/environment.example` 到 `/etc/aigc-studio/environment`，复制提供方配置并限制文件权限。

部署时必须让服务端 bundle 与浏览器静态资源来自同一次构建：将 `scripts/deploy-standalone.sh` 放在项目根目录执行。脚本会清理并同步 `.next/standalone` 和 `.next/static`，避免 HTML 引用的新 hash 在 Nginx 上找不到 CSS/JS。Nginx 的 `/_next/static/` 应指向 `/opt/aigc-studio/.next/standalone/.next/static/`，不要指向并行的 `/opt/aigc-studio/.next/static/`。

安装 `deploy/aigc-studio.service`、`deploy/aigc-studio-poll.service`、`deploy/aigc-studio-poll.timer` 到 `/etc/systemd/system/`，执行 `systemctl daemon-reload && systemctl enable --now aigc-studio aigc-studio-poll.timer`。

将 `deploy/nginx.conf` 安装为站点配置；示例复用服务器已有的 `/etc/nginx/.htpasswd`。站点监听 `8083`，因此访问地址为 `https://服务器公网IP:8083`；请同时在 Volcengine 安全组开放 TCP 8083。自签 IP 证书需包含 IP SAN，例如：

```bash
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/aigc-studio/certs/server.key \
  -out /etc/aigc-studio/certs/server.crt \
  -subj '/CN=YOUR_PUBLIC_IP' -addext 'subjectAltName = IP:YOUR_PUBLIC_IP'
```

手机和电脑首次访问自签证书会显示安全警告，需手动信任。不要公开 3000 端口。

## 备份

定期执行 `scripts/backup.sh /mnt/backup/aigc-studio`。该脚本通过 SQLite 在线备份复制数据库，并归档本地媒体文件。恢复时停止服务，再恢复数据库和媒体目录。
