# 深度代码审查报告

> **日期**: 2026-03-18  
> **审查范围**: Task 1-7 所有代码变更（7 个文件）

## 发现的问题

### 🔴 Bug 1 — 严重 | `task_executor.py`

**问题**: 可读摘要代码（L249-262）位于 `try-except json.JSONDecodeError` 块**外面**，但引用了 `ticket_id_str`、`ticket_status`、`duration` 等仅在 `try` 块内赋值的变量。

**影响**: 当 Runner 输出的行以 `{` 开头且包含 `"ticket_id"` 但不是合法 JSON 时，`JSONDecodeError` 被捕获后继续执行到 L249，触发 `UnboundLocalError` → **整个任务执行失败**。

**修复**: 将可读摘要和进度广播代码移入 `try` 块内（成功分支），在 `except` 中将原始行作为普通日志保存作为 fallback。

render_diffs(file:///f:/Ones-AI专项开发/ones-ai-platform/backend/task_executor.py)

---

### 🟡 Bug 2 — 中等 | `tasks.py`

**问题**: `get_ticket_report()` 的 SQL `SELECT` 未包含 `tt.result_analysis` 列，但返回值 L276 使用 `row["result_analysis"]`。

**影响**: 前端调用报告 API 时，**KeyError** 异常导致 500 错误。虽然现有前端代码未直接使用此字段（报告弹窗不显示 analysis），但存在隐患。

**修复**: 在 SELECT 中添加 `tt.result_analysis`。

render_diffs(file:///f:/Ones-AI专项开发/ones-ai-platform/backend/tasks.py)

---

### 🟢 Bug 3 — 轻微 | `TaskDetailView.vue`

**问题**: 模板中 `@click="t._showAnalysis = !t._showAnalysis"` 直接给对象添加动态属性，Vue 3 的 Proxy 响应式系统可以检测到新属性添加，但初始值为 `undefined`，首次取反时的显示行为不稳定（`!undefined = true`，功能上可用但不规范）。

**修复**: 在 `loadTask()` 中预初始化 `_showAnalysis = false` 和 `_showReport = false`。

render_diffs(file:///f:/Ones-AI专项开发/ones-ai-platform/frontend/src/views/TaskDetailView.vue)

---

### 🟢 Bug 4 — 轻微 | `AdminUserDetail.vue`

**问题**: 缺少 `window.resize` 事件监听，浏览器窗口大小变化时 ECharts 图表不会自适应。

**修复**: 添加 `resize` 监听器 + `onUnmounted` 时清理。

render_diffs(file:///f:/Ones-AI专项开发/ones-ai-platform/frontend/src/views/AdminUserDetail.vue)

---

## 安全检查

| 检查项 | 结果 |
|--------|------|
| SQL 注入 (`admin.py` L219) | ✅ `trunc` 通过白名单字典过滤，仅 `day/week/month` |
| XSS (`v-html` Markdown 渲染) | ⚠️ 已有 `renderMd()` 过滤 `<script>` 和 `<iframe>`，可接受 |
| 权限控制 | ✅ 新 API 使用 `Depends(require_admin)` |
| 输入校验 | ✅ `days: Query(90, ge=1, le=365)` |

## 审查结论

**4 个问题已全部修复**，代码质量达到部署标准。
