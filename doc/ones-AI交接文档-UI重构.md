# ones-AI 平台 — 新窗口交接文档

> **交接日期**: 2026-03-26 | **交接目的**: UI/交互全面重构 | **交接人**: 上一窗口 AI

---

## 1. 项目概述

ones-AI 是一个**智能工单处理平台**，用户提交 ONES 工单号后，平台通过 SSH 连接远程服务器，调用 AI Agent 自动分析和修复代码缺陷，并生成报告。

**生产地址**: `http://172.60.1.35:9621`

---

## 2. 两个工作区的关系

| 工作区 | 路径 | 内容 | 说明 |
|--------|------|------|------|
| **ones-AI 平台** | `f:\Ones-AI专项开发\ones-ai-platform\` | 前端 + 后端源码 | **主开发区**，所有代码修改在这里 |
| **lango-claude-deploy** | 远程服务器上的部署包 | Runner、Docker compose、部署脚本 | 需要同步过去的产物 |

**同步关系**：在 `ones-ai-platform` 修改代码 → 本地构建 → 部署脚本推送到 `172.60.1.35` 服务器容器中。

---

## 3. 项目目录结构

```
f:\Ones-AI专项开发\ones-ai-platform\
├── frontend/                    # Vue 3 + Vite + Element Plus
│   ├── src/
│   │   ├── api/index.js         # Axios API 层（所有后端接口封装）
│   │   ├── router/index.js      # Vue Router（14 个路由）
│   │   ├── styles/index.css     # ⭐ 全局设计系统（CSS变量+动效+组件样式）
│   │   └── views/               # 13 个页面组件
│   │       ├── LoginView.vue         # 登录页
│   │       ├── DashboardView.vue     # 首页仪表盘
│   │       ├── TaskListView.vue      # 任务列表
│   │       ├── TaskView.vue          # 新建任务
│   │       ├── TaskDetailView.vue    # 任务详情+日志+报告
│   │       ├── AdminView.vue         # 管理概览
│   │       ├── AdminTrend.vue        # 趋势分析（ECharts）
│   │       ├── AdminUsers.vue        # 用户排行
│   │       ├── AdminUserDetail.vue   # 用户详情
│   │       ├── AdminEval.vue         # 评价统计
│   │       ├── AdminConfigs.vue      # 系统配置
│   │       ├── AdminServers.vue      # 服务器管理
│   │       └── AdminExternalTeams.vue # 外部团队管理（新增）
│   ├── nginx.conf               # Nginx 配置（前端+API代理）
│   └── dist/                    # 构建产物
│
├── backend/                     # FastAPI + PostgreSQL
│   ├── main.py                  # 入口（路由注册）
│   ├── config.py                # 配置管理（Pydantic Settings）
│   ├── auth.py                  # JWT 认证
│   ├── database.py              # 数据库初始化（12张表）
│   ├── task_executor.py         # 任务执行器（SSH+AI Agent调度）
│   ├── tasks.py                 # 任务 CRUD API
│   ├── servers.py               # 服务器管理 API
│   ├── admin.py                 # 管理统计 API
│   ├── external.py              # 外部团队日志上报 API（新增）
│   ├── evaluations.py           # 评价系统
│   ├── ones_client.py           # ONES API 客户端
│   ├── ssh_pool.py              # SSH 连接池
│   ├── log_streamer.py          # WebSocket 日志推送
│   ├── notifications.py         # 企微/邮件通知
│   └── crypto.py                # AES 加密
│
└── doc/                         # 项目文档
```

---

## 4. 技术栈

| 层 | 技术 |
|----|------|
| 前端框架 | Vue 3 (Composition API, `<script setup>`) |
| UI 组件库 | Element Plus |
| 图表 | ECharts 5 |
| 构建工具 | Vite |
| 后端框架 | FastAPI (Python 3.11) |
| 数据库 | PostgreSQL 15 (asyncpg) |
| 认证 | JWT (python-jose) |
| 部署 | Docker (host 网络模式) |

---

## 5. 当前设计系统（⭐ 重点）

上一轮已完成从「紫蓝AI暗色主题」到「白色企业级主题」的迁移。核心在 `frontend/src/styles/index.css`:

### 5.1 CSS 变量体系
```css
--accent: #1e40af;           /* 主色-深蓝 */
--accent-light: #3b82f6;     /* 主色-亮蓝 */
--accent-bg: rgba(30,64,175,0.06); /* 主色背景 */
--bg-body: #f1f5f9;          /* 页面背景-浅灰 */
--bg-card: #ffffff;          /* 卡片背景-白色 */
--text-primary: #0f172a;     /* 主文字-近黑 */
--text-secondary: #475569;   /* 次级文字 */
--text-muted: #94a3b8;       /* 弱文字 */
--border: #e2e8f0;           /* 边框色 */
--shadow: 0 1px 3px rgba(0,0,0,0.06); /* 阴影 */
```

### 5.2 动效系统
```css
--ease: cubic-bezier(.22,1,.36,1);  /* spring 弹性曲线 */
--transition: 0.2s var(--ease);
/* 路由过渡: name="page" （scale+fade） */
/* hover: translateY(-2px) + shadow 增强 */
```

### 5.3 日志查看器（独立配色，不跟随主题）
```css
.log-viewer { background: #0f172a; color: #e2e8f0; }
.log-system { color: #38bdf8; }  /* 天蓝 */
.log-stderr { color: #fb7185; }  /* 亮红 */
```

### 5.4 已知遗留问题
- `TaskDetailView.vue` 的 `.task-id-highlight` 仍用 `var(--accent-light)` — 可正常显示但可优化
- `AdminUserDetail.vue`、`AdminEval.vue`、`AdminConfigs.vue`、`AdminServers.vue` 未做专项美化
- 部分页面的 `rgba(99,102,241,...)` 硬编码紫色未清理（需全局搜索 `99,102,241`）

---

## 6. 部署方式

### 6.1 服务器信息
```
地址: 172.60.1.35
用户: ops
密码: 6&#re&#nv#yC9R^^4f32&2%osGA&X37^6@EM
```

### 6.2 Docker 容器
```
onesai-frontend  — Nginx (端口 9621)，serve 前端 dist + API 代理
onesai-backend   — FastAPI (端口 9625)，host 网络模式
PostgreSQL       — 端口 9622，用户 onesai/onesai123，数据库 ones_ai_platform
```

### 6.3 部署流程

**前端部署**（修改 Vue/CSS 后）：
```bash
# 1. 本地构建
cd f:\Ones-AI专项开发\ones-ai-platform\frontend
npm run build

# 2. 打包 dist 并上传到服务器
# 3. docker cp dist/. onesai-frontend:/usr/share/nginx/html/
# （无需重启 nginx）
```

**后端部署**（修改 Python 后）：
```bash
# 1. 上传 .py 文件到服务器 /tmp/
# 2. docker cp /tmp/xxx.py onesai-backend:/app/xxx.py
# 3. docker restart onesai-backend
```

### 6.4 一键部署脚本模板（Python + paramiko）
```python
import paramiko, os, io, tarfile
os.environ['NO_PROXY'] = '172.60.1.35'
PASS = "6&#re&#nv#yC9R^^4f32&2%osGA&X37^6@EM"

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('172.60.1.35', username='ops', password=PASS)
sftp = ssh.open_sftp()

def sudo(cmd):
    stdin, stdout, stderr = ssh.exec_command(
        f"echo '{PASS}' | sudo -S bash -c \"{cmd}\"", timeout=30)
    return stdout.read().decode() + stderr.read().decode()

# 上传后端文件
sftp.put('backend/xxx.py', '/tmp/_xxx.py')
sudo("docker cp /tmp/_xxx.py onesai-backend:/app/xxx.py")

# 上传前端 dist (tar)
buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode='w:gz') as tar:
    tar.add('frontend/dist', arcname='dist')
buf.seek(0)
with sftp.file('/tmp/fe.tar.gz', 'wb') as f:
    f.write(buf.read())
sudo("cd /tmp && tar xzf fe.tar.gz")
sudo("docker cp /tmp/dist/. onesai-frontend:/usr/share/nginx/html/")

# 重启后端
sudo("docker restart onesai-backend")
```

---

## 7. Nginx 配置（前端 → 后端代理）

```nginx
server {
    listen 9621;
    root /usr/share/nginx/html;
    
    location / { try_files $uri $uri/ /index.html; }          # SPA
    location /api/ { proxy_pass http://127.0.0.1:9625; }      # API 代理
    location /ws/ {                                             # WebSocket
        proxy_pass http://127.0.0.1:9625;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

---

## 8. JWT 认证

- 密钥（生产）: `please-change-this-to-a-random-string-in-production`
- 算法: `HS256`
- 有效期: 72 小时
- Payload 字段: `sub`(用户ID), `email`, `role`(user/admin), `exp`
- 前端存储: `localStorage.token` + `localStorage.user`

---

## 9. API 概览

前端 API 封装在 `frontend/src/api/index.js`，所有接口统一 `/api` 前缀：

| 模块 | 端点 | 说明 |
|------|------|------|
| 认证 | POST `/auth/login` | ONES 邮箱+密码登录 |
| 服务器 | GET `/servers` | 服务器列表 |
| 任务 | POST `/tasks` | 创建任务 |
| | GET `/tasks` | 任务列表 |
| | GET `/tasks/:id` | 任务详情 |
| | WS `/ws/tasks/:id/logs` | 实时日志 |
| 管理 | GET `/admin/overview` | 统计概览 |
| | GET `/admin/trends` | 趋势数据 |
| | GET `/admin/users` | 用户排行 |
| 外部 | POST `/external/report` | 外部团队日志上报（API Key） |
| | GET/POST/DELETE `/admin/external-teams` | 团队管理 |

---

## 10. 数据库表（12张）

`users`, `servers`, `server_credentials`, `tasks`, `task_tickets`, `task_logs`, `evaluations`, `configs`, `user_daily_stats`, `external_teams`, `external_team_members`, `external_logs`

---

## 11. 当前状态 & 待办

### ✅ 已完成
- 全局 CSS 变量设计系统（白色主题）
- LoginView、DashboardView、TaskListView、AdminView、AdminTrend、AdminUsers 白色主题适配
- App.vue 侧边栏重构（深色侧边栏+品牌色LOGO）
- 路由过渡动画（scale+fade）
- 外部团队 API（后端+前端+数据库）全链路已验证
- 执行日志高对比度终端风格

### 🔲 待重构（你的任务）
- `TaskView.vue` — 新建任务页，交互和表单体验
- `TaskDetailView.vue` — 任务详情页，卡片/报告展示优化
- `AdminUserDetail.vue` — 用户详情页
- `AdminEval.vue` — 评价统计页
- `AdminConfigs.vue` — 配置页面
- `AdminServers.vue` — 服务器管理页
- `AdminExternalTeams.vue` — 外部团队管理页（有基础UI，需要美化）
- 全局搜索清理硬编码颜色 `99,102,241`（旧紫色）
- 微交互和动效增强（hover、入场动画等）
- 侧边栏交互优化
- 移动端适配完善

---

## 12. 关键注意事项

1. **改完 CSS/Vue 后本地 `npm run build` 验证**，构建通过再部署
2. **所有新组件必须使用 `index.css` 中的 CSS 变量**，禁止硬编码颜色值
3. **后端修改需要 `docker restart onesai-backend`**，前端不需要重启
4. **ONES 登录依赖上游系统 (`172.60.1.103:9006`)**，该系统偶尔会 500，与我们代码无关
5. **数据库变更要在 `database.py` 的 `init_database()` 函数中添加迁移SQL**
6. **用户规则**: 回复用中文、脚本用UTF-8、不要用powershell内联python、命令结果输出到文件而非收集工具
