# UI 重构 — 遗留项修复任务清单

## 1. 全局设计系统修复
- [x] 在 `index.css` 中补全缺失的 CSS 变量（`--accent-indigo`、`--accent-blue`、`--glass-bg`、`--glass-border`、`--accent-subtle`）

## 2. 硬编码紫色清除
- [x] `TaskDetailView.vue` — 1 处 `rgba(99,102,241,...)` + 进度条 `#6366f1`
- [x] `AdminUserDetail.vue` — 4 处 `rgba(99,102,241,...)` + `#6366f1` + `rgba(139,92,246,...)`
- [x] `AdminEval.vue` — 2 处 `rgba(99,102,241,...)`

## 3. ECharts 主题修复
- [x] `AdminUserDetail.vue` — 移除 `'dark'` 主题 + 适配白色系配色
- [x] `AdminEval.vue` — 同上

## 4. 页面美化
- [x] `AdminConfigs.vue` — page-header + 分组图标/描述 + scoped 样式
- [x] `AdminServers.vue` — page-header + 统计概览卡片 + 状态指示器
- [x] `AdminEval.vue` — page-header 统一
- [x] `AdminUserDetail.vue` — page-header 统一
- [x] `TaskView.vue` — 暗色边框 `rgba(255,255,255,0.03)` 修复
- [x] `TaskDetailView.vue` — 硬编码颜色修复

## 5. 构建验证
- [x] `npm run build` 本地验证通过（0 错误，2236 模块，39.11s）
