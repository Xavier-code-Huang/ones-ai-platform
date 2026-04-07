# 分离 ones-AI 实施计划

## 概览：三个仓库各改什么

```
仓库 1: lango-claude-deploy       → 删除 ones-AI 相关内容
仓库 2: Ones-AI专项开发           → 新增独立安装包
仓库 3: lango-deploy-tool (9680)  → 前端分区，支持双产品部署
```

---

## 仓库 1: lango-claude-deploy（删减）

### 删除
- `ones_task_runner/` 整个目录

### 修改 pack.sh
- 删除 `ONES_FILES` 数组（71-81行）
- 删除 `bin/ones-AI` `bin/ones_task_runner` 引用（31行）

### 修改 install-lango-init.sh  
- 删除 170-201行（ones_task_runner 安装逻辑）
- 删除 38行 `/usr/local/bin/ones-AI` 备份
- 删除 58行 `ones-AI` 清理

---

## 仓库 2: Ones-AI专项开发（新增独立安装包）

### 新建 `ones-ai-deploy/` 目录

```
Ones-AI专项开发/
├── ones-ai-deploy/              ← 新建
│   ├── ones-AI.sh               ← shell 入口（从工作区根目录移入）
│   ├── ones_task_runner.py      ← runner（从工作区根目录移入）
│   ├── commands/
│   │   └── execute-task.md      ← 技能文件
│   ├── config.yaml              ← 运行配置
│   ├── version                  ← "1.5.0"
│   ├── install-ones-ai.sh       ← 独立安装器（新写）
│   └── pack.sh                  ← 打包脚本（新写）
├── ones-ai-platform/            ← 平台（不动）
└── ...
```

### install-ones-ai.sh 核心逻辑（~50行）

```bash
#!/usr/bin/env bash
# ones-AI 独立安装器（不动 lango-AI 的任何文件）
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NEW_VER=$(cat "$SCRIPT_DIR/version" 2>/dev/null || echo "未知")
OLD_VER=$(cat /opt/lango/ones_task_runner/version 2>/dev/null || echo "未安装")

echo "ones-AI 安装: $OLD_VER → $NEW_VER"

# 备份旧版
if [[ -d "/opt/lango/ones_task_runner" ]]; then
    BACKUP="/opt/lango/ones_task_runner/backup/$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$BACKUP"
    cp -a /opt/lango/ones_task_runner/*.py "$BACKUP/" 2>/dev/null || true
    cp -a /usr/local/bin/ones-AI "$BACKUP/" 2>/dev/null || true
fi

# 安装
mkdir -p /opt/lango/ones_task_runner /opt/lango/commands
cp -f "$SCRIPT_DIR/ones_task_runner.py" /opt/lango/ones_task_runner/
cp -f "$SCRIPT_DIR/config.yaml" /opt/lango/ones_task_runner/
cp -f "$SCRIPT_DIR/ones-AI.sh" /usr/local/bin/ones-AI
chmod +x /usr/local/bin/ones-AI
cp -f "$SCRIPT_DIR/commands/execute-task.md" /opt/lango/commands/ 2>/dev/null || true
cp -f "$SCRIPT_DIR/version" /opt/lango/ones_task_runner/

echo "✅ ones-AI v$NEW_VER 安装完成"
echo "   命令: ones-AI --help"
```

### pack.sh（~10行）

```bash
#!/usr/bin/env bash
VERSION=$(cat version 2>/dev/null || echo "1.0.0")
tar -czf "ones-ai-deploy-v${VERSION}.tar.gz" \
    ones-AI.sh ones_task_runner.py config.yaml version \
    commands/ install-ones-ai.sh
echo "✅ ones-ai-deploy-v${VERSION}.tar.gz"
```

---

## 仓库 3: lango-deploy-tool (9680 Web UI)

### 前端改造：底部操作栏分成两区

当前（所有按钮混在一起）：
```
[上传文件] [执行部署] [重新部署] [⚙️Auth-Claude] [📄CLAUDE.md] [📋ones-AI配置] [⏪回滚]
```

改造后（分区清晰）：
```
━━━ lango-AI ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[📤 上传包] [🚀 执行部署] [🔄 重新部署] [⚙️ Auth-Claude] [📄 CLAUDE.md] [⏪ 回滚]

━━━ ones-AI ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[📤 上传ones包] [🚀 部署ones-AI] [⚙️ ones-AI配置]

━━━ 进度 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[▓▓▓▓▓▓▓▓░░░░░░░░░░] 完成 3/5
```

### 后端改造：

新增 action `ones-deploy`:
```python
elif action == 'ones-deploy':
    # 类似 deploy，但用 ones-ai-deploy 目录下的包
    service.action_deploy_ones(valid_ips, package_name, remote_path)
```

新增 `DeployService.action_deploy_ones()`:
```python
def action_deploy_ones(self, selected_ips, package_name, remote_path):
    """独立部署 ones-AI（不动 lango-AI）"""
    # 1. SCP 上传 ones-ai-deploy-vX.tar.gz
    # 2. SSH: tar xzf + bash install-ones-ai.sh
    # 3. 验证: ones-AI --version
```

---

## 执行顺序

| 步骤 | 仓库 | 内容 | 风险 |
|------|------|------|------|
| 1 | Ones-AI专项开发 | 创建 `ones-ai-deploy/` 安装包 | 无（纯新增） |
| 2 | lango-deploy-tool | 前端分区 + 后端 ones-deploy action | 低（增量改） |
| 3 | lango-claude-deploy | 删除 ones_task_runner/ + 精简脚本 | 中（下次发 lango 包才生效） |

> 步骤 1+2 做完后 ones-AI 就能独立发布了。步骤 3 不急，下次发 lango-AI 包顺便清。
