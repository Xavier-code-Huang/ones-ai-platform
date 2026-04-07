# 任务模式 + Patch 回收 — 实施计划

## 背景

AI 执行工单时只输出分析报告，不产出代码 patch。根本原因是 `execute-task.md` 模板对执行深度没有强制约束。用户要求**所有改动集中在平台和 runner**，不改 Agent Teams 目录。

## 设计方案

### 数据流

```
前端选择 task_mode → API 存入 tasks 表 → task_executor 传参 --task-mode
  → ones-AI 透传 → runner 根据 mode 注入不同系统提示词
  → Claude 执行 → runner 收集 git diff → JSON 输出中包含 patch
```

### 任务模式定义

| mode | 前端标签 | AI 行为 |
|------|---------|---------|
| `analysis` | 🔍 分析模式 | 只分析不改代码，输出分析报告和方案 |
| `fix` | 🔧 修复模式 | **必须修改代码**，产出 patch + 报告 |
| `auto` | 🤖 全自动模式 | AI 自行判断，能修的直接修，不确定的给方案 |

---

## Proposed Changes

### 前端

#### [MODIFY] [TaskView.vue](file:///F:/Ones-AI专项开发/ones-ai-platform/frontend/src/views/TaskView.vue)

在 Agent 目录下方、工单列表上方新增**任务模式选择器**（radio button group）：

```html
<div style="margin-bottom:20px;">
  <label class="field-label">任务模式</label>
  <el-radio-group v-model="form.task_mode" id="task-mode-select">
    <el-radio-button value="fix">🔧 修复模式</el-radio-button>
    <el-radio-button value="analysis">🔍 分析模式</el-radio-button>
    <el-radio-button value="auto">🤖 全自动</el-radio-button>
  </el-radio-group>
  <div class="field-hint">{{ modeHints[form.task_mode] }}</div>
</div>
```

`form` 初始值加 `task_mode: 'fix'`（默认修复模式），`submitTask` payload 加 `task_mode`。

---

### 后端 API

#### [MODIFY] [tasks.py](file:///F:/Ones-AI专项开发/ones-ai-platform/backend/tasks.py)

- `CreateTaskRequest` 新增 `task_mode: str = "fix"` 字段
- `create_task()` 写入 `tasks` 表
- 校验 `task_mode in ("analysis", "fix", "auto")`

#### [MODIFY] [database.py](file:///F:/Ones-AI专项开发/ones-ai-platform/backend/database.py)

- `tasks` 表新增 `task_mode TEXT DEFAULT 'fix'`
- 部署脚本加 `ALTER TABLE tasks ADD COLUMN IF NOT EXISTS task_mode TEXT DEFAULT 'fix'`

#### [MODIFY] [task_executor.py](file:///F:/Ones-AI专项开发/ones-ai-platform/backend/task_executor.py)

- `_build_remote_command()` 新增 `--task-mode` 参数
- 从 `task` 行中读取 `task_mode` 传给命令

---

### ones-AI 脚本

#### [MODIFY] [ones-AI](file:///F:/Claude/lango-claude-deploy/ones_task_runner/ones-AI)

- 解析 `--task-mode` 参数（与 `--agent-dir` 同理），透传给容器内 runner
- **不需要额外挂载逻辑**，只是参数透传

---

### Runner（核心改动）

#### [MODIFY] [ones_task_runner.py](file:///F:/Claude/lango-claude-deploy/ones_task_runner/ones_task_runner.py)

**改动 1**: argparse 新增 `--task-mode`

**改动 2**: `ClaudeExecutor` 新增模式提示词字典（内置在代码中）

```python
MODE_PROMPTS = {
    "analysis": (
        "## 任务模式：分析模式\n\n"
        "你的职责是**仅分析不修改代码**：\n"
        "1. 阅读工单信息和相关代码\n"
        "2. 输出根因分析、影响范围、解决方案建议\n"
        "3. **不要修改任何源代码文件**\n"
        "4. 在报告中列出建议的修改方案和具体步骤\n"
    ),
    "fix": (
        "## 任务模式：修复模式\n\n"
        "你的职责是**必须产出代码修改**：\n"
        "1. 阅读工单信息，定位问题代码\n"
        "2. **直接修改源代码文件**，不要只写方案让人去改\n"
        "3. 对于 CTS 豁免类问题，直接修改对应的 Java 文件添加豁免\n"
        "4. 对于 Bug 修复，直接编辑源码修复\n"
        "5. 修改完成后用 `git diff` 确认所有改动\n"
        "6. 在报告中列出所有修改的文件和 diff\n\n"
        "**禁止**：只输出分析报告而不修改代码。"
        "如果确实无法修改（如缺少权限），必须在报告中明确说明原因。\n"
    ),
    "auto": (
        "## 任务模式：全自动模式\n\n"
        "你自行判断最佳方案：\n"
        "1. 如果能确定修复方案，**直接修改代码**\n"
        "2. 如果不确定，创建 `.patch` 文件供人工 review\n"
        "3. 如果问题太复杂无法直接修复，输出详细分析报告\n"
        "4. 在报告中标注你的判断结论和理由\n"
    ),
}
```

**改动 3**: `execute()` 中， mode prompt 注入到 skill 模板**之后**（让它覆盖模板中的"保守方案"指引）

```python
prompt = self._load_skill_template(params_json)

# 注入 Agent Teams 提示词（如有）
if agent_prompts:
    prompt = f"# Agent Teams 提示词\n\n{agent_prompts}\n\n---\n\n{prompt}"

# 注入任务模式指令（放在最后，优先级最高）
if task_mode and task_mode in MODE_PROMPTS:
    prompt = f"{prompt}\n\n---\n\n{MODE_PROMPTS[task_mode]}"
```

**改动 4**: 任务执行完成后收集 `git diff`

在 `execute()` 返回之前，如果 mode 是 `fix` 或 `auto`，额外执行 `git diff` 收集 patch：

```python
if task_mode in ("fix", "auto") and code_dir:
    try:
        diff_result = subprocess.run(
            f"cd {code_dir} && git diff",
            shell=True, capture_output=True, text=True, timeout=30
        )
        result['patch'] = diff_result.stdout or ""
    except:
        result['patch'] = ""
```

---

## 改动范围总结

| 文件 | 改动 | 行数估计 |
|------|------|---------|
| `TaskView.vue` | 任务模式选择器 + hints | ~20 行 |
| `tasks.py` | `task_mode` 字段和校验 | ~8 行 |
| `database.py` | schema 加列 | ~2 行 |
| `task_executor.py` | 传参 `--task-mode` | ~5 行 |
| `ones-AI` | 透传 `--task-mode` | ~0 行（已自动透传） |
| `ones_task_runner.py` | 模式提示词 + git diff 回收 | ~60 行 |
| `deploy_now.py` | ALTER TABLE | ~1 行 |

## Verification Plan

1. 提交 `fix` 模式任务，验证 AI 是否直接修改代码
2. 提交 `analysis` 模式任务，验证 AI 只分析不改代码
3. 验证 JSON 输出中是否包含 `patch` 字段
