# ones-AI 脚本挂载 + Runner 提示词注入

## 背景

平台端已完成：前端传递 `--agent-dir` 和 `--extra-mounts` 参数。
现需要脚本端和 runner 端接收并处理这两个参数。

## 冲突检查

> [!NOTE]
> kiro spec (`task-detail-enhance/tasks.md`) 修改的是 `task_executor.py` 解析逻辑和 `TaskDetailView.vue` 前端展示，**与本次改动不冲突**。本次只改 `ones-AI` 脚本和 `ones_task_runner.py`。

---

## Proposed Changes

### ones-AI 脚本（Docker 挂载）

#### [MODIFY] [ones-AI](file:///F:/Claude/lango-claude-deploy/ones_task_runner/ones-AI)

**修改点 1**：在 `build_args()` 之后、Docker 挂载构建之前，解析 `--agent-dir` 和 `--extra-mounts`

```bash
# ---- 解析 --agent-dir 和 --extra-mounts 用于 Docker 挂载 ----
AGENT_DIR=""
EXTRA_MOUNTS=""
for i in "${!ARGS_ARRAY[@]}"; do
    case "${ARGS_ARRAY[$i]}" in
        --agent-dir) AGENT_DIR="${ARGS_ARRAY[$((i+1))]}" ;;
        --extra-mounts) EXTRA_MOUNTS="${ARGS_ARRAY[$((i+1))]}" ;;
    esac
done
```

**修改点 2**：在 L162（Excel 处理前），追加挂载逻辑

```bash
# ---- 额外挂载：Agent 目录 ----
if [[ -n "$AGENT_DIR" ]]; then
    case "$AGENT_DIR" in
        "${USER_HOME}"*|"${WORK_DIR}"*) ;;
        *) MOUNT_ARGS+=(-v "${AGENT_DIR}:${AGENT_DIR}:ro") ;;
    esac
fi

# ---- 额外挂载：--extra-mounts（逗号分隔） ----
if [[ -n "$EXTRA_MOUNTS" ]]; then
    IFS=',' read -ra MOUNT_LIST <<< "$EXTRA_MOUNTS"
    for mp in "${MOUNT_LIST[@]}"; do
        mp="${mp// /}"  # 去空格
        [[ -z "$mp" ]] && continue
        case "$mp" in
            "${USER_HOME}"*|"${WORK_DIR}"*) ;;
            *) MOUNT_ARGS+=(-v "${mp}:${mp}") ;;
        esac
    done
fi
```

---

### Runner（提示词注入）

#### [MODIFY] [ones_task_runner.py](file:///F:/Claude/lango-claude-deploy/ones_task_runner/ones_task_runner.py)

**修改点 1**：`parse_args()` 新增 `--agent-dir` 参数（L1020 处）

```python
parser.add_argument(
    '--agent-dir',
    help='Agent Teams 目录，从中加载 .md 提示词注入到 Claude prompt'
)
parser.add_argument(
    '--extra-mounts',
    help='额外挂载路径（逗号分隔），由 ones-AI 脚本处理，runner 不使用'
)
```

**修改点 2**：`main()` 中传递 `agent_dir` 给 `TaskRunner.run()`

**修改点 3**：`TaskRunner.run()` 签名新增 `agent_dir` 参数

**修改点 4**：`ClaudeExecutor` 新增提示词加载方法

```python
def load_agent_prompts(self, agent_dir: str) -> str:
    """从 Agent Teams 目录加载所有 .md 提示词"""
    if not agent_dir or not os.path.isdir(agent_dir):
        return ""
    prompts = []
    # 扫描目录及一级子目录
    patterns = [
        os.path.join(agent_dir, "*.md"),
        os.path.join(agent_dir, "*", "*.md"),
    ]
    import glob
    seen = set()
    for pattern in patterns:
        for f in sorted(glob.glob(pattern)):
            if f in seen:
                continue
            seen.add(f)
            try:
                content = open(f, encoding='utf-8').read().strip()
                if content:
                    name = os.path.relpath(f, agent_dir)
                    prompts.append(f"## [{name}]\n\n{content}")
            except Exception:
                pass
    if prompts:
        logger.info(f"📋 从 Agent 目录加载了 {len(prompts)} 个提示词")
    return "\n\n---\n\n".join(prompts)
```

**修改点 5**：`ClaudeExecutor.execute()` 中在 prompt 前追加 Agent 提示词

```python
# 在 prompt = self._load_skill_template(params_json) 之后
if agent_prompts:
    prompt = (
        "# Agent Teams 提示词\n\n"
        "以下是项目团队提供的提示词和规范，请在执行任务时严格遵循：\n\n"
        f"{agent_prompts}\n\n"
        "---\n\n"
        f"{prompt}"
    )
```

---

## Verification Plan

### 本地验证
1. 在 WSL 中运行 `ones-AI --tickets TEST-001 --code-dirs /tmp --agent-dir /tmp/test-agents --extra-mounts /opt/data,/home/share`，检查 Docker 命令是否包含对应 `-v` 参数
2. 创建测试 Agent 目录，放几个 `.md` 文件，验证 runner 能加载并注入

### 服务器部署
1. 更新 `/opt/lango/ones_task_runner/` 下的脚本和 runner
2. 从平台前端提交任务，验证 agent 目录挂载和提示词注入
