# 构建前端
FROM node:18-alpine AS frontend-builder

WORKDIR /app

# 创建 gateway 目录结构，因为 vite 输出到 ../gateway/static
RUN mkdir -p gateway

COPY frontend/package*.json ./frontend/
WORKDIR /app/frontend
RUN npm config set registry https://registry.npmjs.org/ \
 && npm config set foreground-scripts true \
 && npm ci --no-audit --verbose

COPY frontend/ ./
RUN npm run build

# 构建 Rust 后端
FROM rust:1.88-slim AS backend-builder

RUN apt-get update && apt-get install -y \
    pkg-config \
    libssl-dev \
    libsqlite3-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*
    
WORKDIR /app/gateway

# 直接复制完整 Rust 项目，避免占位二进制被错误复用
COPY gateway/ ./

# 构建实际应用
RUN --mount=type=cache,target=/usr/local/cargo/registry \
    --mount=type=cache,target=/app/target \
    cargo build --release

# 最终镜像
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y \
    ca-certificates \
    tzdata \
    libsqlite3-0 \
    libssl3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=backend-builder /app/gateway/target/release/chatgpt-mirror-gateway .
# 前端构建输出到 /app/gateway/static（由 vite.config.ts 配置）
COPY --from=frontend-builder /app/gateway/static ./static

RUN mkdir -p /app/data

# 设置时区
ENV TZ=Asia/Shanghai

# 默认端口（可通过环境变量 PORT 覆盖）
ENV PORT=40002

# 暴露端口（文档性质，实际端口由 PORT 环境变量控制）
EXPOSE ${PORT}

CMD ["./chatgpt-mirror-gateway"]
