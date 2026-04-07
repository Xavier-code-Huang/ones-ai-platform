# ones-AI 平台部署 Walkthrough

## 部署概要

| 项目 | 说明 |
|------|------|
| **目标服务器** | 172.60.1.35 |
| **前端地址** | http://172.60.1.35:9621 |
| **后端 API** | http://172.60.1.35:9620 |
| **PostgreSQL** | 172.60.1.35:9622 |
| **部署方式** | Docker Compose (镜像传输) |
| **部署时间** | 2026-03-17 11:36 |

## 部署流程

1. **本机 Docker 停掉** — `docker compose down` 释放资源
2. **35 服务器检查** — SSH 连接确认端口 9620/9621/9622 可用
3. **本地 WSL 构建镜像** — `docker compose -f docker-compose.prod.yml build`
4. **镜像导出** — `docker save | gzip` → 194MB tar.gz
5. **SCP 传输** — paramiko sftp 上传到 35 服务器
6. **远程 docker load** — 加载 3 个镜像
7. **docker compose up -d** — 启动 3 容器

## 遇到的问题及解决

### 问题 1：Docker Hub 超时
35 服务器位于国内网络，`docker pull` 无法访问 Docker Hub。
**解决**：本地 WSL 构建 → docker save → SCP → docker load

### 问题 2：后端 502 Bad Gateway
**根因**：Dockerfile 硬编码 `--port 9610`，但 docker-compose 映射 `9620:9620`
**解决**：改为 `9620:9610`（主机端口:容器端口），nginx 代理指向 `backend:9610`

## 验证截图

### 登录页面
![ones-AI 登录页面](file:///C:/Users/HuangYixiang/.gemini/antigravity/brain/4e95e145-694d-4d75-b7ec-a0f59a2460ca/ones_ai_login_initial_1773718658984.png)

### 登录表单测试
![登录表单填写](file:///C:/Users/HuangYixiang/.gemini/antigravity/brain/4e95e145-694d-4d75-b7ec-a0f59a2460ca/ones_ai_login_attempt_result_v2_1773718739544.png)

### 验证结果

| 检查项 | 结果 |
|--------|------|
| 前端页面加载 | ✅ HTTP 200 |
| 登录表单可交互 | ✅ 可填写邮箱/密码 |
| 后端 API 响应 | ✅ `{"detail":"Not authenticated"}` (401) |
| 容器全部运行 | ✅ onesai-db / onesai-backend / onesai-frontend |

## 端口分配总览 (172.60.1.35)

| 端口 | 服务 | 状态 |
|------|------|------|
| 9500 | AI Gateway | ✅ |
| 9601 | Key Gateway (lango-AI) | ✅ |
| 9602 | Engineer DNA | ✅ |
| 9603 | Tracking | ✅ |
| 9610 | lango-pro Gateway | ✅ |
| 9611 | lango-pro API Proxy | ✅ |
| 9612 | lango-pro Deploy | ✅ |
| **9620** | **ones-AI 后端 API** | ✅ 新部署 |
| **9621** | **ones-AI 前端** | ✅ 新部署 |
| **9622** | **ones-AI PostgreSQL** | ✅ 新部署 |
