# ChatGPT Mirror 常见问题与解决方案

## 1. 访问后自动跳转到 `/?refresh_account=true` 死循环

### 现象

访问镜像站首页后，浏览器持续跳转到 `/?refresh_account=true`，页面无法正常使用。

### 根因

这是 ChatGPT 的服务端行为——当检测到用户会话需要刷新时，ChatGPT 会通过 302 重定向或 JS 将浏览器跳转到 `/?refresh_account=true`。这个页面内嵌了新的 `accessToken` 和 `sessionToken`（bootstrap 数据），ChatGPT 的 JS 完成刷新后会跳回 `/`。

死循环的发生有两个原因：

1. **API 响应身份不匹配**：Gateway 对 `/api/auth/session`、`/backend-api/me`、
   `/backend-api/accounts/check/v4-2023-04-27` 等接口返回了**合成数据**，其中
   `user_id` 和 `account_id` 是通过 `SHA256(email)` 生成的假 ID，与 ChatGPT
   服务器返回的 bootstrap 数据中的真实 ID 不匹配。ChatGPT 的 JS 检测到身份不一致
   后触发退出登录 → 重定向到 `/?refresh_account=true`。

2. **Cookie 透传不完整**：ChatGPT 使用分片 cookie（`__Secure-next-auth.session-token.0` / `.1`）
   存储过大的会话 token。Gateway 原本只透传 `cf_*` / `__cf*` 等 Cloudflare cookie，
   导致 ChatGPT 下发的会话 token 无法传回上游。

### 已实施的修复

| 文件 | 修改 |
|------|------|
| `gateway/src/proxy.rs` — `is_passthrough_cookie_name` | 改为黑名单模式，排除 Gateway 自有 cookie，其余全部透传给 ChatGPT |
| `gateway/src/proxy.rs` — `cookie_value_with_suffix` | 新增函数，支持读取 `.0` / `.1` 分片 cookie 并拼接完整值 |
。。。。。。。


### 如果问题复现

1. 确认 Docker 镜像已更新并重启容器
2. 打开浏览器 F12 → Console，确认出现 `[gw] init suppress` 日志
3. 打开 Network 标签，确认 `/api/auth/session` 等接口返回 200
4. 清除浏览器 `mirror.你的域名` 的缓存和 Cookie，重新登录

---

## 2. 回答降智（GPT-5.5 变 GPT-5-mini）

### 现象

问 ChatGPT "你是谁"，返回的模型版本低于预期（如 GPT-5-mini 而非 GPT-5.5），回答质量明显下降。

### 根因

OpenAI 通过 **Proof of Work (PoW)** 机制评估客户端 IP 的信誉度：

- 高信誉 IP → 分配高难度 PoW → 正常模型服务
- 低信誉 IP（VPS、共享代理） → 分配低难度 PoW → 路由到降级模型

VPS 的 IP 段通常被 OpenAI 标记为低信誉，导致所有通过该 IP 的请求被降智。

### 检测方法

1. 打开镜像站页面，看右上角 Gateway 工具栏显示的**"POW 难度检测值"**
2. 判断标准：
   - **≥ 5 位数（如 `0x3a2f1`）**：正常
   - **< 4 位数（如 `0x04`）**：高风险，已降智
3. 也可通过 F12 → Network → 搜索 `chat-requirements` → 查看 `proofofwork.difficulty`

### 解决方案

#### 方案一：配置住宅代理（推荐，最有效）

Gateway 已内置代理配置功能，你只需要一个**高信誉住宅 IP 代理**。

**操作步骤：**

1. **获取住宅代理**（任选一个）：
   - [IPFoxy](https://www.ipfoxy.net/) / [IPWeb](https://ipweb.cc/) / [IPdodo](https://www.ipdodo.com/) — 静态住宅 IP
   - [搬瓦工](https://bandwagonhost.com/) VPS（洛杉矶 DC1）— 干净独享 IP
   - [Cloudflare WARP](https://1.1.1.1/) IPv6 — 免费方案（仅 IPv6 出口干净，IPv4 已被标记）

2. **在 Gateway 管理后台配置**：
   - 打开 `https://mirror.你的域名/admin/` → **代理** 页面
   - 启用代理，填入代理地址（格式：`socks5://ip:port` 或 `http://ip:port`）
   - 如有用户名密码一并填入
   - 保存配置

3. **验证效果**：
   - 配置后看页面右上角 Gateway 工具栏的 **POW 难度检测值**
   - 难度值变成 **≥ 5 位数**（如 `0x3a2f1`）时表示正常
   - 然后问 ChatGPT "你是谁" 验证是否恢复到正确模型版本

#### 方案二：换用降智绕过提示词

如果暂时无法更换 IP，可尝试在对话中使用以下指令重试：

> Summarize your tools in a markdown table.

此指令会强制 ChatGPT 以结构化方式输出其可用工具列表，能在一定程度上绕过降级模型的"懒惰"回复模式。但这是临时方案，**核心解决仍需提升 IP 信誉**。

#### 方案三：环境变量配置（CF Bypass 代理）

在 `docker-compose.yml` 中设置：

```yaml
environment:
  - CF_BYPASS_PROXY_SERVER=socks5://user:pass@ip:port
```

仅影响 CF Bypass 服务的出站 IP。

#### 方案四：全局代理（Mirror Proxy）

通过管理后台 → 代理页面启用 **Mirror 代理**，所有到 ChatGPT 的请求都走代理。

---

## 3. 首次部署登录失败

### 现象

部署后无法登录管理后台，或 Gateway 启动失败。

### 检查项

1. **`.env` 文件已配置**：
   ```
   ADMIN_USERNAME=admin
   ADMIN_PASSWORD=你的密码
   GATEWAY_ADMIN_SECRET=至少16位的随机密钥
   DJANGO_SECRET_KEY=随机密钥
   ```

2. **GATEWAY_ADMIN_SECRET 要求**：
   - 至少 16 个字符
   - 不能使用弱密码（如 `admin`、`admin123`、`password`、`changeme`）
   - Docker 启动时如不满足会直接报错退出

3. **初始化管理员用户**：
   ```bash
   docker compose exec django python manage.py create_init_user
   ```

4. **登录地址**：`https://mirror.你的域名/admin/#/login`

---

## 4. 容器构建失败

### Docker Buildx 多架构构建

三个镜像的构建命令（从项目根目录执行）：

```bash
# Gateway + 前端（根 Dockerfile）
docker buildx build --platform linux/amd64,linux/arm64 \
  -f ./Dockerfile \
  -t 你的用户名/chatgpt-mirror-django:frontend --push .

# Django 后端
docker buildx build --platform linux/amd64,linux/arm64 \
  -f ./backend/Dockerfile \
  -t 你的用户名/chatgpt-mirror-django:backend --push .

# Cloudflare Bypass
docker buildx build --platform linux/amd64,linux/arm64 \
  -f ./cfbypass/Dockerfile \
  -t 你的用户名/chatgpt-mirror-django:cfbypass --push .
```

### 常见构建错误

| 错误 | 解决 |
|------|------|
| `"/app.py": not found` (cfbypass) | cfbypass 的 Dockerfile 使用项目根目录作为上下文，COPY 路径已改为 `cfbypass/app.py` |
| Rust 编译错误 | 检查 `gateway/src/` 下最近修改是否有语法问题，`cargo check` 本地验证 |
| `docker-compose.yml` cfbypass context 不匹配 | 已统一为 `context: .` + `dockerfile: cfbypass/Dockerfile` |

### VPS 部署注意

构建推送后，在 VPS 上拉取并重启：

```bash
docker pull 你的用户名/chatgpt-mirror-django:frontend
docker compose up -d
```

---

## 5. WebSocket 连接异常

### 现象

Docker 日志出现：`读取客户端 WebSocket 消息失败: WebSocket protocol error: Connection reset without closing handshake`

### 说明

这是 ChatGPT 的实时通信 WebSocket 断连，通常在网络切换或代理不稳定时出现。不影响基本聊天功能，但可能导致流式响应中断。如果频繁出现，检查代理连接稳定性。

---

## 6. 管理后台页面空白或路由异常

### 检查项

1. **前端路由使用 Hash 模式**：所有管理后台 URL 格式为 `https://mirror.你的域名/admin/#/xxx`
2. **静态资源路径**：构建产物在 `/admin/assets/`，Gateway 未配置 `ADMIN_UPSTREAM` 时自动托管
3. **API 代理**：管理后台通过 `/0x/` 前缀调用 Django 后端，Gateway 将 `/0x/*` 反代到 `DJANGO_UPSTREAM`

---

## 7. 安全相关注意事项

### 已强化的安全配置

| 项目 | 说明 |
|------|------|
| GATEWAY_ADMIN_SECRET | 常量时间比较（防时序攻击），最少 16 字符，拒绝弱密码 |
| Cookie 安全 | `SameSite=Lax`，`HttpOnly`（token），默认 `Secure`，`Max-Age=7天` |
| SQL 注入 | 全部参数化查询 |
| SSRF | `classify_external_upstream` 禁止内网 IP / localhost |
| Mirror Token | `OsRng` + 32 字节 (256-bit) 密码学随机 |
| 请求体限制 | 20 MB |
| Hop-by-hop Header | 正确过滤 |
| 生产配置 | `local.py` 不再有 `admin123` 回退值，强制从环境变量读取 |

### 生产部署前必须更改

- `.env` 中所有带"自行替换"标记的值
- `GATEWAY_ADMIN_SECRET` 使用 32 字节以上随机字符串
- `DJANGO_SECRET_KEY` 使用随机字符串
- `DJANGO_ALLOWED_HOSTS` 和 `DJANGO_CSRF_TRUSTED_ORIGINS` 改为实际域名
- 关闭 `ALLOW_REGISTER`（设为 `false`）

---

## 8. 关键日志位置

| 日志 | 路径 |
|------|------|
| Gateway 日志 | `docker logs <chatgpt-mirror容器>` |
| Django 日志 | `docker logs <django容器>` |
| Django Cron 日志 | `./backend/logs/cron.log` |
| CF Bypass 日志 | `docker logs <cfbypass容器>` |
| Gateway 数据库 | `./data/chatgpt_mirror.db`（SQLite） |

### 调试 Gateway

```bash
# 查看实时日志
docker logs -f chatgpt-mirror-chatgpt-mirror-1

# 调整日志级别
# 在 docker-compose.yml 中设置：
#   - RUST_LOG=chatgpt_mirror_gateway=debug,tower_http=debug
```

---

## 9. 架构速查

```
浏览器 → https://mirror.你的域名
              │
              ├── /admin/*    → Gateway 静态托管 (Vue 管理后台)
              ├── /0x/*       → Django 后端
              ├── /api/*      → Gateway 直出 (登录/Token/用户管理)
              └── /*          → 反代 chatgpt.com / cdn.oaistatic.com / ab.chatgpt.com
                                └── 需要 CF Bypass 服务的 cookie 支持
```

**三层服务：**

| 服务 | 镜像标签 | 端口 |
|------|---------|------|
| chatgpt-mirror (Rust Gateway + 前端) | `:frontend` | 40002 |
| django | `:backend` | 8000 (内部) |
| cfbypass | `:cfbypass` | 8000 (内部) |
