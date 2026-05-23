
# ChatGPT Mirror

ChatGPT Mirror 是一个由 Vue 管理后台、Django 后台服务、Cloudflare Bypass 辅助服务和 Docker 编排组成的镜像站管理项目。

> 维护完成。
>
> 说明：`Gateway/` 目录在本文档中声明为空目录/预留目录，不包含在本 README 的目录结构、功能说明和使用说明中。


## 功能概览

- 管理后台：基于 Vue 3、Vite、Pinia、Vue Router 和 TDesign Vue Next。
- 用户管理：支持用户列表、注册配置、免费账号登录、用户过期时间、模型限制和备注管理。
- ChatGPT 账号管理：支持账号登录、账号枚举、Token 有效性诊断、Token 过期检查和账号备注。
- 号池管理：支持 ChatGPT 账号分组、用户绑定号池和号池枚举。
- 访问日志：记录用户、ChatGPT 账号、登录类型、IP、User-Agent 和访问时间。
- 代理配置：支持代理配置读取、保存和测试。
- 自定义脚本配置：支持后台接口维护脚本配置。
- Cloudflare Bypass：提供基于 FastAPI、DrissionPage 和 Chromium 的可选辅助服务。
- Docker 部署：提供 `docker-compose.yml` 和 `vps-docker-compose.yml` 编排文件。

## 项目结构

```text
.
├── backend/                 # Django 后台服务
│   ├── app/
│   │   ├── accounts/        # 用户、登录、配置、日志相关接口
│   │   ├── chatgpt/         # ChatGPT 账号和号池相关接口
│   │   ├── config/          # local / production 配置
│   │   ├── cron.py          # 定时任务
│   │   ├── settings.py      # Django 主配置
│   │   └── urls.py          # 后台路由入口
│   ├── cli/                 # 初始化用户、更新 token 等命令
│   ├── db/                  # SQLite 数据目录
│   ├── logs/                # 日志目录
│   ├── Dockerfile
│   ├── entrypoint.sh
│   ├── manage.py
│   └── requirements.txt
├── cfbypass/                # Cloudflare Bypass 辅助服务
│   ├── app.py
│   ├── Dockerfile
│   └── requirements.txt
├── debug/                   # 调试页面或临时调试资源
├── frontend/                # Vue 管理后台
│   ├── public/
│   ├── src/
│   │   ├── api/
│   │   ├── layouts/
│   │   ├── pages/
│   │   ├── router/
│   │   └── store/
│   ├── package.json
│   └── vite.config.ts
├── Dockerfile
├── docker-compose.yml
└── vps-docker-compose.yml
```

## 技术栈

### 前端

- Vue 3
- Vite 5
- TypeScript
- Pinia
- Vue Router
- TDesign Vue Next
- Day.js
- js-cookie

### 后端

- Python 3.12
- Django 5.1
- Django REST Framework
- django-crontab
- SQLite
- requests
- PyJWT

### Cloudflare Bypass

- FastAPI
- Uvicorn
- DrissionPage
- Chromium
- pyvirtualdisplay

## 后台接口

后台服务统一挂载在 `/0x` 路径下。

### 用户相关

```text
/0x/user/
/0x/user/version-cfg
/0x/user/get-mirror-token
/0x/user/register
/0x/user/login-free
/0x/user/chatgpt-list
/0x/user/batch-model-limit
/0x/user/proxy-config
/0x/user/proxy-config/test
/0x/user/custom-scripts
/0x/user/relat-gptcar
/0x/user/login
/0x/user/visit-log
```

### ChatGPT 账号相关

```text
/0x/chatgpt/
/0x/chatgpt/enum
/0x/chatgpt/token-expiry
/0x/chatgpt/login
/0x/chatgpt/car
/0x/chatgpt/car-enum
```

## 前端页面

管理后台使用 `/admin/` 作为构建基路径，路由使用 hash 模式。

主要页面包括：

- `/admin/#/login`：后台登录
- `/admin/#/register`：注册入口
- `/admin/#/login-chatgpt`：ChatGPT 登录页
- `/admin/#/account/user`：用户管理
- `/admin/#/account/chatgpt`：ChatGPT 账号管理
- `/admin/#/account/gptcar`：号池管理
- `/admin/#/account/logs`：访问日志
- `/admin/#/account/proxy`：代理配置
- `/admin/#/account/scripts`：脚本配置

## 本地开发

### 前端

```bash
cd frontend
npm install
npm run dev
```

默认开发端口：

```text
http://localhost:40003/admin/
```

前端开发环境会将 `/0x` 请求代理到：

```text
http://localhost:40002
```

### Django 后台

```bash
cd backend
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

### Cloudflare Bypass

```bash
cd cfbypass
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```

## Docker 部署

项目提供 Docker Compose 编排：

```bash
docker-compose up -d
```

默认服务包括：

- `chatgpt-mirror`
- `django`
- `cfbypass`

其中 Django 服务默认绑定到本机：

```text
127.0.0.1:18000
```

Cloudflare Bypass 服务默认绑定到本机：

```text
127.0.0.1:18001
```

## 关键环境变量

### 通用配置

```text
ADMIN_USERNAME
ADMIN_PASSWORD
GATEWAY_ADMIN_SECRET
ALLOW_REGISTER
FREE_ACCOUNT_USERNAME
SHOW_GITHUB
```

### Django 配置

```text
DJANGO_ENV
DJANGO_DEBUG
DJANGO_SECRET_KEY
DJANGO_ALLOWED_HOSTS
DJANGO_CSRF_TRUSTED_ORIGINS
DJANGO_SECURE_SSL_REDIRECT
DJANGO_SESSION_COOKIE_SECURE
DJANGO_CSRF_COOKIE_SECURE
CHATGPT_GATEWAY_URL
```

### Cloudflare Bypass 配置

```text
CF_BYPASS_HEADLESS
CF_BYPASS_MAX_WAIT_SECONDS
CF_BYPASS_PARTIAL_COOKIE_GRACE_SECONDS
CF_BYPASS_NAVIGATION_RETRIES
CF_BYPASS_USER_AGENT
CF_BYPASS_PROXY_SERVER
CF_BYPASS_BROWSER_PATH
CF_BYPASS_DISPLAY_SIZE
```

## 数据与日志

Django 默认使用 SQLite：

```text
backend/db/db.sqlite3
```

日志目录：

```text
backend/logs/
```

主要日志文件：

```text
backend/logs/default.log
backend/logs/errors.log
backend/logs/cron.log
```

## 定时任务

项目使用 `django-crontab` 维护定时任务。

本地环境默认每分钟执行：

```text
app.cron.check_access_token
app.cron.update_access_token
```

生产环境默认每 5 分钟执行：

```text
app.cron.check_access_token
app.cron.update_access_token
```

## 维护状态

本项目正在维护中。后续维护重点包括：

- 后台接口稳定性
- ChatGPT 账号与 Token 状态诊断
- 前端管理体验
- Docker 部署流程
- Cloudflare Bypass 辅助能力
- 日志与定时任务可靠性

## 许可证



本项目仅允许用于个人学习、研究和非商业用途。

未经项目作者明确书面授权，禁止将本项目或其衍生版本用于任何商业用途，包括但不限于：

- 商业部署
- 付费服务
- SaaS 服务
- 转售、转租或二次销售
- 商业集成或商业分发

如需商业授权，请先联系项目作者取得许可。
