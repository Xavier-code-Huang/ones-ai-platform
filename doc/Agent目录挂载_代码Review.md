# Code Review 报告

审查范围: Agent 目录 + 挂载路径 + 敏感路径过滤功能
审查时间: 2026-03-18

---

## 🔴 需修复 (3 个)

### 1. 前端 `_showMounts` 内部字段会被提交到后端

[TaskView.vue:184](file:///F:/Ones-AI专项开发/ones-ai-platform/frontend/src/views/TaskView.vue#L184)

每个 ticket 对象包含 `_showMounts: false`，这个 UI 内部状态字段会随表单一起提交到后端。后端虽然不使用它，但不干净。

```diff
 // previewTickets 已正确过滤了 _showMounts ✅
 // 但 submitTask 使用的是 previewTickets，所以实际OK
```

> **结论**：`submitTask` 使用 `previewTickets`（已过滤），实际无问题。~~标记为已处理~~

### 2. 前端 `mountErrors` key 拼接存在 bug

[TaskView.vue:83](file:///F:/Ones-AI专项开发/ones-ai-platform/frontend/src/views/TaskView.vue#L83)

```javascript
:class="{'input-error': m && mountErrors[i+'_'+mi]}"
```

模板里用 `i`（来自外层 `v-for`），但 `validateMountPath` 里用 `form.tickets.indexOf(ticket)`。当用户删除中间行后，`indexOf` 返回的 index 和 `i` 会不一致，导致错误提示错位。

**修复**：统一使用 `i` 传入 `validateMountPath`：

```diff
-@blur="validateMountPath(t, mi)"
+@blur="validateMountPath(i, mi)"
 
-function validateMountPath(ticket, mi) {
-  const key = form.tickets.indexOf(ticket) + '_' + mi
+function validateMountPath(ticketIdx, mi) {
+  const key = ticketIdx + '_' + mi
+  const ticket = form.tickets[ticketIdx]
```

### 3. 后端 `validate_path` 对 `/` 本身的处理

[tasks.py:86](file:///F:/Ones-AI专项开发/ones-ai-platform/backend/tasks.py#L86)

```python
p = path.rstrip('/')
```

当 `path = "/"` 时，`rstrip('/')` 返回空字符串 `""`，然后 `p.startswith('/')` 为 `False`，报 "必须为绝对路径"。
验证里也看到了：`/ 拦截: ✅ HTTP 400 Agent 目录必须为绝对路径`

**问题**：错误信息不准确，应该说"不允许挂载根目录"而不是"必须为绝对路径"。

**修复**：

```diff
 def validate_path(path: str, field_name: str = "路径"):
     p = path.rstrip('/')
+    if not p:  # path was "/" after stripping
+        raise HTTPException(400, f"不允许挂载根目录")
     if not p.startswith('/'):
         raise HTTPException(400, f"{field_name}必须为绝对路径")
```

---

## 🟡 建议优化 (2 个)

### 4. 前端 `extra_mounts` 的空值计数问题

[TaskView.vue:78](file:///F:/Ones-AI专项开发/ones-ai-platform/frontend/src/views/TaskView.vue#L78)

```html
<span v-if="t.extra_mounts?.length" class="mount-count">{{ t.extra_mounts.length }}</span>
```

如果用户添加了 3 个路径但只填了 1 个（其余 2 个为空），badge 显示 3 而非 1。建议过滤空值：

```diff
-t.extra_mounts?.length
+t.extra_mounts?.filter(Boolean).length
```

### 5. `normalizeId` 函数无操作

[TaskView.vue:241-243](file:///F:/Ones-AI专项开发/ones-ai-platform/frontend/src/views/TaskView.vue#L241-L243)

```javascript
function normalizeId(id) {
  id = id.trim()
  return /^\d+$/.test(id) ? id : id  // 两个分支返回同一个值??
}
```

这是原有代码的问题，没有实际效果。应该移除或补全逻辑（如加 `ONES-` 前缀）。

---

## ✅ 整体评价

| 方面 | 评分 | 说明 |
|------|------|------|
| 功能完整性 | ⭐⭐⭐⭐ | 前后端字段对齐，校验链完整 |
| 安全性 | ⭐⭐⭐⭐ | 前后端双重校验，BLOCKED_PATHS 覆盖全 |
| 代码风格 | ⭐⭐⭐⭐ | 与现有代码一致 |
| 可维护性 | ⭐⭐⭐ | `mountErrors` key 拼接方式较脆弱 |
| 测试覆盖 | ⭐⭐⭐ | API 自动验证脚本做了基本覆盖 |
