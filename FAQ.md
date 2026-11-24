# 常见问题

这里整理一些部署和使用时比较常见的问题。遇到问题前请先确认已经更新镜像，再仔细检查对应配置；需要反馈时，把具体操作、发生时间和已经隐藏敏感值的错误信息一起提供。

## 部署与更新

### 现在还在更新吗？

已经恢复更新。这次重点是性能和界面，也同步处理了新版 ChatGPT 的回答加载、文件隔离、退出登录和套餐识别等兼容问题。具体内容见 [README](./README.md#更新日志)。

### 需要自己构建吗？

不需要。直接使用项目提供的 [docker-compose.yml](./docker-compose.yml)，三个服务都从云端拉取镜像，Docker 会自动选择 AMD64 或 ARM64。

| 服务 | 镜像 |
| --- | --- |
| 网关与管理前端 | `lisa666520/chatgpt-mirror:latest` |
| 管理服务 | `lisa666520/chatgpt-mirror:backend` |
| CF 辅助 | `lisa666520/chatgpt-mirror:cfbypass` |

这三个标签属于同一个仓库。`backend`、`cfbypass` 用于区分服务，不是版本编号。旧的 allinone 镜像目前不更新。

### 第一次部署要改哪些值？

先复制 `.env.example` 为 `.env`，填写管理员密码及三个独立密钥，再按访问方式选择 `LOCAL_NETWORK_ACCESS`。

```bash
cp .env.example .env
```

每个随机值分别执行一次：

```bash
openssl rand -hex 32
```

然后检查并启动：

```bash
docker compose config --quiet
docker compose pull
docker compose up -d
docker compose ps
```

默认访问 `http://localhost:40002/`。管理后台使用同一站点的 `/admin/` 路径，管理员账号与密码填写在 `.env` 中。

### CREDENTIAL_ENCRYPTION_KEY 是随机值吗？更新时要换吗？

是，首次部署时自己生成，至少 32 个字符，和其他密钥分开填写。它用于加密数据库里的上游凭据。

**更新时不要换。** 数据库和这个密钥要一起保留，换成新值后，已有的加密凭据无法用新密钥解密。`GATEWAY_ADMIN_SECRET` 用于服务间鉴权，`DJANGO_SECRET_KEY` 用于管理服务签名，也应沿用原配置。

### 更新后账号和配置会丢吗？

保留原目录和 `.env`，执行下面两条即可：

```bash
docker compose pull
docker compose up -d
```

`data/` 是网关数据，`backend/db/` 是管理服务数据，`backend/logs/` 是日志。更新前备份数据和密钥；复制 SQLite 文件时先停止服务，完成后再启动。不要只备份其中一个数据库。

## Linux DO 登录

### 怎么开启？本地能不能测试？

默认关闭，必须在 `.env` 中手动设置 `LINUXDO_OAUTH_ENABLED=enable` 才启用，仅填写客户端凭据不会自动开启。先到 [Linux DO Connect](https://connect.linux.do/) 申请应用，把 Client ID、Client Secret 和登记的回调地址填入部署目录的 `.env`。对应配置已经放在 `.env.example` 和 Compose 的管理服务环境变量里。

```env
LINUXDO_OAUTH_ENABLED=enable
LINUXDO_CLIENT_ID=你的 Client ID
LINUXDO_CLIENT_SECRET=你的 Client Secret
LINUXDO_REDIRECT_URI=http://127.0.0.1:40002/0x/user/oauth/linuxdo/callback
LINUXDO_MIN_TRUST_LEVEL=0
LOCAL_NETWORK_ACCESS=enable
```

上面是本地 HTTP 测试的写法，回调地址还需要被 Linux DO Connect 的应用配置接受。浏览器访问的主机和端口必须与回调一致，`localhost` 和 `127.0.0.1` 不要混用。正式部署使用 `https://你的域名/0x/user/oauth/linuxdo/callback`，并按前面的 HTTPS 部署说明关闭本地网络模式。修改后重新创建管理服务容器；首次使用还需要包含此功能的前端与管理服务版本。

`LINUXDO_MIN_TRUST_LEVEL` 支持 0 到 4。Client Secret 只放管理服务的环境变量，不要填进前端、截图或公开反馈里。接入方式参考 [Linux DO Connect 文档](https://wiki.linux.do/Community/LinuxDoConnect)。

### 是直接注册，还是绑定现有账号？

由 `ALLOW_REGISTER` 决定。

- `false`：第一次授权后，输入现有镜像账号的用户名和密码，完成绑定并登录。普通用户和管理员都支持。
- `true`：未绑定的 Linux DO 账号会自动创建普通镜像用户并绑定，后续直接登录。不会因为论坛用户名与本站管理员重名而获得管理权限。

已经绑定的账号按原镜像账号登录，原有权限、配额、号池和隔离配置继续生效。自动注册的新用户也默认开启隔离，管理员仍需要为其分配可用号池。系统通过论坛不可变的用户 ID 识别绑定，论坛改名不会创建另一个镜像账号，也不会按邮箱或同名账号自动关联。

### 普通用户和管理员在哪里绑定？

登录后进入自己的「账户中心」，在「Linux DO 登录」卡片操作即可。管理员可以从右上角账号菜单进入同一个账户中心。每个镜像账号只绑定一个 Linux DO 账号，同一个 Linux DO 账号也只能绑定一个镜像账号。

卡片向本人显示绑定的论坛用户名，不在其他用户的列表里公开展示。解绑后使用本地密码登录。通过 Linux DO 自动注册的账号没有初始本地密码，需要先由管理员设置本地密码，再解除绑定，避免解绑后无法登录。统一备份会保留已完成的绑定，不包含临时授权凭证。

## 网络与反向代理

### 如何让局域网里的设备访问？

使用：

```env
BIND_ADDRESS=0.0.0.0
LOCAL_NETWORK_ACCESS=enable
```

然后访问 `http://192.168.x.x:40002`，IP 替换成部署主机的地址，并确认防火墙放行该端口。`0.0.0.0` 是监听地址，不是浏览器里的访问地址。

### 通过域名和 HTTPS 访问要怎么改？

把 `LOCAL_NETWORK_ACCESS` 改成 `disable`，并填写自己的域名：

```env
LOCAL_NETWORK_ACCESS=disable
DJANGO_ALLOW_ALL_ORIGINS=disable
DJANGO_ALLOWED_HOSTS=example.com,django,localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=https://example.com
DJANGO_SESSION_COOKIE_SECURE=true
DJANGO_CSRF_COOKIE_SECURE=true
COOKIE_SECURE=true
```

反向代理指向网关的 `40002` 端口。NGINX Proxy Manager 开启 WebSocket Support，并正确传递 `Host` 和 `X-Forwarded-Proto`。不要把代理指向 Django 的 `8000` 端口。

### Docker 后面还能记录真实 IP 吗？

可以，但要把代理链配置完整。直连时使用连接来源；经过 NGINX Proxy Manager 时，在 `TRUSTED_PROXY_IPS` 中填写网关实际看到的代理 IP，并透传 `X-Forwarded-For`。Cloudflare 网段已内置。

看到容器或网桥 IP 时，先检查请求经过了哪几层，再填写实际代理地址。不要直接填 `0.0.0.0/0` 或整个私有网段。NGINX 的相关配置见 [来源 IP](https://nginx.org/en/docs/http/ngx_http_realip_module.html) 和 [代理请求头](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_set_header)。

### 为什么回答会卡住，或者最后一起出现？

先检查代理缓冲和超时。NGINX 需要 `proxy_buffering off;`，并为较长的流式回答设置足够的读取超时。再检查 WebSocket 支持是否开启，以及代理日志有没有中断或超时。

这次已经修复部分“无法加载回复”和刷新历史内容的兼容问题。仍有问题时，请提供具体会话、操作步骤和错误时间，便于区分页面加载问题与上游请求失败。

### 出现请求头或 Cookie 过大的错误怎么办？

在 NGINX 中检查以下配置，NGINX Proxy Manager 可按对应配置位置填写：

```nginx
proxy_buffer_size 128k;
proxy_buffers 8 128k;
proxy_busy_buffers_size 256k;
large_client_header_buffers 8 64k;
client_header_buffer_size 64k;
```

修改后先检查 NGINX 配置，再重新加载。完整的 NGINX 与 NGINX Proxy Manager 配置位置不同，不要把整份 server 配置直接放进 Advanced。

## 功能与账号

### 怎么禁止访问 Dot？

进入“访问与安全”，开启“禁止访问 Dot”并保存。默认开启，对所有账号生效，和上游设置开关分开控制。

网关会拦截 Dot 页面、消息、审批和管理接口，并隐藏入口。共享消息房间会根据归属判断是否属于 Dot，普通消息房间仍然可以使用。

### Library 隔离是把资料库关掉吗？

不是。文件按镜像站用户记录归属，同一个上游账号分配给多个用户时，每个用户只能查看和操作自己的文件，上传、预览、下载、删除及搜索都使用这一归属。

是否隐藏 Library 入口是单独的界面选项。入口本身也会受到上游套餐和功能开放情况影响，开启隔离不会额外获得上游功能。

### 删除聊天时，文件会一起删吗？

删除确认中的“删除聊天同时删除已上传或已创建的文件”默认勾选。提交前可以看到当前选择，删除操作仍会检查文件归属。

### 登录失败后为什么有 120 秒倒计时？

同一账号连续输错 3 次会记录到管理员可查看的登录日志中；连续 5 次进入 120 秒冷却，页面显示剩余时间。冷却以浏览器渲染指纹识别，不按 IP 封禁，缺少指纹的登录请求也不会直接放行。

**已经登录且会话有效的用户继续正常使用。** 同一个 NAT 下，不会只因为 IP 相同就一起进入冷却。

### 页面提示初始化数据无法隔离怎么办？

当前版本会显示 5 秒倒计时，清理镜像站 Cookie 后自动刷新。等待页面完成恢复，再重新登录。退出登录也已经增加多处请求捕捉，首次退出请求就会处理镜像会话。

### 性能提升主要体现在哪里？

这次减少了浏览器重复启动、资源重复获取和首次请求的同步等待，也调整了日志输出。README 中的约 214 毫秒保留为单次运行记录，部署时可以结合自己的网络和机器查看实际耗时。

### CF 辅助为什么偶尔还会等比较久？

轻量请求没有得到所需结果时，会进入浏览器处理流程，因此两次请求的耗时可能不同。先检查 `CF_BYPASS_PROXY_SERVER`、网络和代理是否正常，代理用户名与密码需要进行 URL 编码。

当前镜像固定使用 Chrome 146 身份，不要随意更改 User-Agent；浏览器和请求内核需要使用一致的配置。
