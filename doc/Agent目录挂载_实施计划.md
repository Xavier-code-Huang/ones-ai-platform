# Agent 目录 + 额外挂载路径 + 提示词注入

## 背景

1. Docker 容器只挂载 HOME 和工作目录，`--code-dirs` 中跨磁盘路径（如 disk4）不可见
2. 领导要求把 Agent Teams 中的提示词 MD 文件程序注入到 Claude 的 prompt
3. 用户可能需要挂载代码目录和 Agent 目录之外的路径

## 新增字段

| 字段 | 位置 | 必填 | 说明 |
|------|------|------|------|
| Agent Teams 目录 | 表单顶部（服务器下方） | ✅ | 服务器上的绝对路径 |
| 额外挂载路径 | 每工单行，可展开添加多个 | ❌ | 支持多行追加 |

## Proposed Changes

### 前端 TaskView.vue

#### [MODIFY] [TaskView.vue](file:///F:/Ones-AI专项开发/ones-ai-platform/frontend/src/views/TaskView.vue)

1. 服务器选择下方新增 **Agent Teams 目录** 输入框（必填）

```html
<div style="margin-bottom:28px;">
  <label class="field-label">Agent Teams 目录 <span class="required">*</span></label>
  <el-input v-model="form.agent_dir" placeholder="如 /home/disk3/user/Lango-Agent-Teams" />
</div>
```

2. 工单行中新增「额外挂载」展开按钮，点击展开多行路径输入

3. 前端路径校验函数，**禁止敏感路径**：

```javascript
const BLOCKED_PATHS = ['/', '/etc', '/sys', '/proc', '/dev', '/boot', '/root',
  '/var', '/usr', '/sbin', '/bin', '/lib', '/lib64', '/run', '/tmp']

function validatePath(path) {
  const p = path.replace(/\/+$/, '') // 去尾斜杠
  if (BLOCKED_PATHS.includes(p)) return '不允许挂载系统敏感路径'
  if (p.split('/').length < 3) return '路径层级过浅，至少需要 3 级'
  if (!p.startsWith('/')) return '必须为绝对路径'
  return null
}
```

---

### 后端 tasks.py

#### [MODIFY] [tasks.py](file:///F:/Ones-AI专项开发/ones-ai-platform/backend/tasks.py)

1. `CreateTask` 模型新增 `agent_dir: str` 字段
2. `TicketItem` 模型新增 `extra_mounts: list[str] = []` 字段
3. 后端也做一次敏感路径校验（防绕过前端）

---

### 后端 task_executor.py

#### [MODIFY] [task_executor.py](file:///F:/Ones-AI专项开发/ones-ai-platform/backend/task_executor.py)

`_build_remote_command()` 新增参数拼接：

```python
# 新增 --agent-dir 参数
cmd_parts.extend(['--agent-dir', agent_dir])

# 新增 --extra-mounts 参数（逗号分隔）
all_mounts = set()
for ticket in tickets:
    all_mounts.update(ticket.get('extra_mounts', []))
if all_mounts:
    cmd_parts.extend(['--extra-mounts', ','.join(all_mounts)])
```

---

### ones-AI 脚本

#### [MODIFY] [ones-AI](file:///F:/Claude/lango-claude-deploy/ones_task_runner/ones-AI)

1. 解析 `--agent-dir` 和 `--extra-mounts` 参数
2. 把 `--code-dirs`、`--agent-dir`、`--extra-mounts` 的路径都加到 `MOUNT_ARGS`
3. 去重后挂载

```bash
# 收集所有需要挂载的路径
EXTRA_PATHS=()
# 从 --code-dirs 提取
# 从 --agent-dir 提取
# 从 --extra-mounts 提取（逗号分隔）

for p in "${EXTRA_PATHS[@]}"; do
    # 跳过已在 HOME/WORKDIR 下的路径
    case "$p" in
        "${USER_HOME}"*|"${WORK_DIR}"*) continue ;;
    esac
    MOUNT_ARGS+=(-v "$p:$p")
done
```

---

### Runner ones_task_runner.py

#### [MODIFY] [ones_task_runner.py](file:///F:/Claude/lango-claude-deploy/ones_task_runner/ones_task_runner.py)

1. `argparse` 新增 `--agent-dir` 参数
2. 启动 Claude 前，扫描 `agent_dir` 下的 MD 文件并注入：

```python
def load_agent_prompts(agent_dir):
    """从 Agent Teams 目录加载提示词"""
    prompts = []
    for pattern in ['*.md', 'prompts/*.md', 'rules/*.md']:
        for f in glob.glob(os.path.join(agent_dir, pattern)):
            content = open(f, encoding='utf-8').read()
            prompts.append(f"## {os.path.basename(f)}\n{content}")
    return '\n\n'.join(prompts)
```

3. 注入到 Claude `-p` 的 prompt 中 

---

## 敏感路径过滤规则

**前后端统一**，禁止挂载：

| 路径 | 原因 |
|------|------|
| `/` | 根目录 |
| `/etc`, `/boot`, `/root` | 系统配置 |
| `/sys`, `/proc`, `/dev`, `/run` | 内核/硬件 |
| `/usr`, `/bin`, `/sbin`, `/lib*` | 系统程序 |
| `/var`, `/tmp` | 系统数据/临时 |
| 层级 < 3 级的路径 | 如 `/home` 太宽泛 |

## Verification Plan

### 自动验证
1. 前端：输入 `/etc`、`/`、`/home` 等路径，验证拦截
2. 后端：发送含敏感路径的 API 请求，验证 400 拒绝
3. 提交任务：验证 SSH 命令正确包含 `--agent-dir` 和 `--extra-mounts`

### 部署验证
1. 新建镜像 + `deploy_now.py` 部署
2. 前端填写 Agent 目录和额外挂载路径提交任务
3. 检查 Docker 容器内是否能看到所有挂载路径
