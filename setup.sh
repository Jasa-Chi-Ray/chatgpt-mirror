#!/usr/bin/env bash
set -e

# ============================================================
# ChatGPT Mirror — 一键部署脚本
# ============================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${CYAN}[INFO]${NC} $*"; }
ok()   { echo -e "${GREEN}[OK]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }

# ---------- 随机密钥 ----------
gen_secret() {
    local len=${1:-32}
    openssl rand -hex "$len" 2>/dev/null || cat /dev/urandom 2>/dev/null | tr -dc 'a-zA-Z0-9' | head -c "$len"
}

# ---------- 检查 Docker ----------
check_deps() {
    if command -v docker &>/dev/null; then
        if docker compose version &>/dev/null; then
            DOCKER_COMPOSE="docker compose"
        elif command -v docker-compose &>/dev/null; then
            DOCKER_COMPOSE="docker-compose"
        else
            echo -e "${RED}[ERROR]${NC} 未找到 docker compose 插件"
            exit 1
        fi
        return
    fi

    echo -e "${YELLOW}============================================${NC}"
    echo -e "${YELLOW}  未检测到 Docker${NC}"
    echo -e "${YELLOW}============================================${NC}"
    echo ""
    read -rp "是否现在安装 Docker？[Y/n]: " install_docker
    case "$install_docker" in
        [Nn]|[Nn][Oo])
            echo -e "${RED}[ERROR]${NC} Docker 是必须的依赖，已退出"
            exit 1
            ;;
    esac

    log "正在通过官方脚本安装 Docker..."
    if command -v curl &>/dev/null; then
        curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
    elif command -v wget &>/dev/null; then
        wget -q https://get.docker.com -O /tmp/get-docker.sh
    else
        echo -e "${RED}[ERROR]${NC} 需要 curl 或 wget 来下载安装脚本"
        exit 1
    fi

    sudo sh /tmp/get-docker.sh
    rm -f /tmp/get-docker.sh

    # 启动 Docker
    if command -v systemctl &>/dev/null; then
        sudo systemctl enable docker --now
    fi

    # 将当前用户加入 docker 组
    if ! groups "$USER" | grep -q docker; then
        sudo usermod -aG docker "$USER" 2>/dev/null || true
        echo -e "${YELLOW}[WARN]${NC} 已将用户加入 docker 组，请注销后重新登录以使权限生效"
        echo -e "${YELLOW}[WARN]${NC} 重新登录后运行: ./setup.sh${NC}"
        exit 0
    fi

    DOCKER_COMPOSE="docker compose"
    ok "Docker 安装完成"
}

# ============================================================
# 第一部分：.env 配置
# ============================================================
setup_env() {
    echo ""
    echo -e "${CYAN}============================================${NC}"
    echo -e "${CYAN}       ChatGPT Mirror — 环境配置${NC}"
    echo -e "${CYAN}============================================${NC}"
    echo ""

    # 检测 .env 是否存在
    if [ -f ".env" ]; then
        warn "检测到已存在 .env 文件"
        read -rp "是否覆盖？[y/N]: " overwrite
        case "$overwrite" in
            [Yy]|[Yy][Ee][Ss])
                log "将覆盖现有 .env"
                ;;
            *)
                log "保留现有 .env，跳转到部署步骤"
                return 1
                ;;
        esac
    fi

    # ADMIN_USERNAME 默认值
    ADMIN_USERNAME="admin"

    # 询问 ADMIN_PASSWORD
    while true; do
        read -rp "请输入管理员密码 (ADMIN_PASSWORD): " ADMIN_PASSWORD
        if [ -n "$ADMIN_PASSWORD" ]; then
            break
        fi
        warn "密码不能为空"
    done

    # 询问域名（用于 DJANGO_ALLOWED_HOSTS）
    read -rp "请输入你的镜像站域名（如 mirror.example.com）: " DOMAIN
    if [ -z "$DOMAIN" ]; then
        DOMAIN="mirror.example.com"
        warn "未输入域名，使用默认值: $DOMAIN"
    fi

    # DJANGO_ALLOWED_HOSTS = 默认值 + 用户域名
    DJANGO_ALLOWED_HOSTS="django,localhost,127.0.0.1,${DOMAIN}"

    # DJANGO_CSRF_TRUSTED_ORIGINS = 仅用户域名
    DJANGO_CSRF_TRUSTED_ORIGINS="https://${DOMAIN}"

    # 随机密钥
    DJANGO_SECRET_KEY=$(gen_secret 32)
    GATEWAY_ADMIN_SECRET=$(gen_secret 32)

    # 输出 .env
    cat > .env <<EOF

ADMIN_USERNAME=${ADMIN_USERNAME}
ADMIN_PASSWORD=${ADMIN_PASSWORD}
GATEWAY_ADMIN_SECRET=${GATEWAY_ADMIN_SECRET}
DJANGO_SECRET_KEY=${DJANGO_SECRET_KEY}

DJANGO_ALLOWED_HOSTS=${DJANGO_ALLOWED_HOSTS}
DJANGO_CSRF_TRUSTED_ORIGINS=${DJANGO_CSRF_TRUSTED_ORIGINS}

PORT=40002
COOKIE_SECURE=true
ALLOW_REGISTER=false
DJANGO_DEBUG=false
DJANGO_SESSION_COOKIE_SECURE=true
DJANGO_CSRF_COOKIE_SECURE=true
RUST_LOG=info
EOF

    ok ".env 已生成"
    return 0
}

# ============================================================
# 第二部分：Docker 操作
# ============================================================
docker_ops() {
    echo ""
    echo -e "${CYAN}============================================${NC}"
    echo -e "${CYAN}       ChatGPT Mirror — Docker 部署${NC}"
    echo -e "${CYAN}============================================${NC}"
    echo ""

    # 下载 docker-compose.yml
    COMPOSE_URL="https://raw.githubusercontent.com/Jasa-Chi-Ray/chatgpt-mirror/refs/heads/main/docker-compose.yml"
    log "下载 docker-compose.yml ..."
    if command -v curl &>/dev/null; then
        curl -fsSL "$COMPOSE_URL" -o docker-compose.yml
    elif command -v wget &>/dev/null; then
        wget -q "$COMPOSE_URL" -O docker-compose.yml
    else
        echo -e "${RED}[ERROR]${NC} 需要 curl 或 wget"
        exit 1
    fi
    ok "docker-compose.yml 下载完成"

    echo ""
    echo "  1) 🐳 拉取镜像并启动"
    echo "  2) 🛑 结束/卸载"
    echo ""
    read -rp "请选择 [1-2]: " choice

    case "$choice" in
        1)
            log "拉取镜像并启动..."
            $DOCKER_COMPOSE pull
            $DOCKER_COMPOSE up -d
            ok "服务已启动"

            # 输出管理员信息
            echo ""
            echo -e "${GREEN}============================================${NC}"
            echo -e "${GREEN}  部署完成！管理员登录信息：${NC}"
            echo -e "${GREEN}============================================${NC}"
            echo ""
            # 从 .env 读取
            if [ -f ".env" ]; then
                ADMIN_USER=$(grep "^ADMIN_USERNAME=" .env | cut -d'=' -f2)
                ADMIN_PASS=$(grep "^ADMIN_PASSWORD=" .env | cut -d'=' -f2)
                echo -e "  ${CYAN}ADMIN_USERNAME${NC} = ${ADMIN_USER:-admin}"
                echo -e "  ${CYAN}ADMIN_PASSWORD${NC} = ${ADMIN_PASS:-未设置}"
            fi
            echo ""
            echo -e "  登录地址: ${CYAN}https://${DOMAIN:-你的域名}/admin/#/login${NC}"
            echo ""

            # 初始化管理员
            log "初始化管理员账户..."
            sleep 3
            $DOCKER_COMPOSE exec -T django python manage.py create_init_user 2>/dev/null || true
            ok "初始化完成"
            ;;
        2)
            log "停止并移除服务..."
            $DOCKER_COMPOSE down
            ok "服务已停止"
            ;;
        *)
            warn "无效选项，退出"
            exit 1
            ;;
    esac
}

# ============================================================
# 主流程
# ============================================================
main() {
    # 确保在 ChatGPT-mirror 目录
    TARGET_DIR="${1:-ChatGPT-mirror}"
    if [ ! -d "$TARGET_DIR" ]; then
        mkdir -p "$TARGET_DIR"
        log "已创建目录: $TARGET_DIR"
    fi
    cd "$TARGET_DIR"

    check_deps

    if setup_env; then
        # .env 已创建或覆盖，继续部署
        docker_ops
    else
        # 用户选择不覆盖，直接部署
        docker_ops
    fi
}

main "$@"
