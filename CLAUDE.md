# Ones-AI 专项开发工作区

## 项目概述

这是 **ones-AI** 的完整工作区，包含：
1. **ones-ai-platform** — Web 管理平台（前端 Vue3 + 后端 Flask），运行在 172.60.1.35
2. **ones-ai-deploy** — CLI 工具的独立安装包（ones-AI.sh + ones_task_runner.py）

ones-AI 是协助开发者在下班/休息时间自动处理 ONES 工单赚取绩效的平台。

## 目录结构

```
Ones-AI专项开发/
├── ones-ai-platform/            ← Web 管理平台
│   ├── frontend/                ← Vue3 前端 (Element Plus)
│   │   ├── src/views/           ← 页面组件
│   │   ├── src/components/      ← 通用组件 (WebTerminal 等)
│   │   └── src/api/index.js     ← API 接口定义
│   ├── backend/                 ← Flask 后端
│   │   ├── app.py               ← 入口 + 路由注册
│   │   ├── tasks.py             ← 任务 CRUD API
│   │   ├── task_executor.py     ← 核心调度引擎（SSH远程执行）
│   │   ├── external.py          ← 外部团队管理 API
│   │   └── onesai.db            ← SQLite 数据库
│   └── deploy_full.py           ← 一键部署脚本（前端构建+后端推送）
│
├── ones-ai-deploy/              ← CLI 独立安装包
│   ├── ones-AI.sh               ← Shell 入口脚本
│   ├── ones_task_runner.py      ← AI 执行引擎（调用 Claude CLI）
│   ├── config.yaml              ← 运行配置
│   ├── commands/execute-task.md  ← Claude skill 文件
│   ├── version                  ← 版本号（如 1.5.0）
│   ├── install-ones-ai.sh       ← 独立安装器
│   └── pack.sh                  ← 打包脚本
│
├── ones_task_runner.py          ← runner 开发副本（编辑后复制到 ones-ai-deploy/）
├── ones-AI.sh                   ← shell 开发副本（编辑后复制到 ones-ai-deploy/）
└── doc/                         ← 项目文档
```

## 部署流程

### 1. 部署 Web 平台（ones-ai-platform）

平台直接部署到 172.60.1.35，不经过部署器：

```bash
python deploy_full.py
```

该脚本会：
- `npm run build` 构建前端
- SCP 上传到 35 服务器的 `/opt/onesai-platform/`
- 重启 `onesai-backend` 和 nginx

**平台访问地址**：http://172.60.1.35:9600

### 2. 部署 CLI 工具（ones-ai-deploy）

CLI 工具通过 Web 部署器分发到各服务器：

**Step 1: 打包**
```bash
cd ones-ai-deploy
# WSL 中执行
bash pack.sh
# 产出: ones-ai-deploy-v1.5.0.tar.gz
```

**Step 2: 上传到部署器**
1. 打开 http://172.60.1.35:9680
2. 左侧上传区 → 选 `📦 部署包` → 拖入 tar.gz
3. 选目标服务器

**Step 3: 部署**
底部 **🟢 ones-AI** 区域 → `🚀 部署ones-AI`

**Step 4: 如需回滚**
底部 **🟢 ones-AI** 区域 → `⏪ 回滚`

### 3. 服务器上的安装结果

```
/opt/lango/ones_task_runner/
├── ones_task_runner.py    ← AI 执行引擎
├── config.yaml            ← 配置
├── version                ← 版本号
└── backup/                ← 自动备份（每次安装前备份上一版）

/usr/local/bin/ones-AI     ← 入口命令
/opt/lango/commands/execute-task.md  ← Claude skill
```

## 服务器信息

| 服务 | 地址 | 说明 |
|------|------|------|
| ones-AI 平台 | http://172.60.1.35:9600 | Web 管理界面 |
| 部署器 | http://172.60.1.35:9680 | lango-AI / ones-AI 部署工具 |
| API Key 网关 | http://172.60.1.35:9601 | Claude API Key 分发 |
| SSH | 172.60.1.35 | 用户: ops |

## 核心架构

```
用户提交工单列表
    ↓
ones-ai-platform (Flask)
    ↓ SSH
task_executor.py → 远程服务器执行 ones-AI 命令
    ↓
ones-AI.sh → Docker 容器 (lango-claude:latest)
    ↓
ones_task_runner.py → Claude CLI → 分析代码 → JSON 结果
    ↓
task_executor.py ← 收集结果 → WebSocket 推送 → 前端实时展示
```

## 开发注意事项

- `ones_task_runner.py` 和 `ones-AI.sh` 的**唯一源**在 `ones-ai-deploy/` 目录
- 根目录的副本是开发时的方便入口，修改后需手动复制到 `ones-ai-deploy/`
- Docker 镜像 `lango-claude:latest` 与 lango-AI 共享，由 `F:\Claude\lango-claude-deploy` 管理
- 数据库 `onesai.db` 在 35 服务器的 `/opt/onesai-platform/backend/`

## 相关项目

| 项目 | 路径 | 说明 |
|------|------|------|
| lango-AI 部署包 | `F:\Claude\lango-claude-deploy` | lango-AI CLI 工具 |
| 部署器 | `F:\Claude\lango-deploy-tool` | Web 部署工具源码 |
