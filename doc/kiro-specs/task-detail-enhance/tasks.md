# 任务详情展示增强 + 用户统计图表 — 实施任务分解

> **版本**: 1.1.0  
> **日期**: 2026-03-18  
> **状态**: 待审阅  
> **关联需求**: [requirements.md](file:///f:/Ones-AI专项开发/.kiro/specs/task-detail-enhance/requirements.md)  
> **关联设计**: [design.md](file:///f:/Ones-AI专项开发/.kiro/specs/task-detail-enhance/design.md)

---

## Task 1: 数据库迁移 — 新增 result_analysis 列

> 关联: [FR-018] → [design.md §2]

- [ ] 1.1 在 `database.py` 的 `MIGRATION_SQL` 中追加 `ALTER TABLE task_tickets ADD COLUMN IF NOT EXISTS result_analysis TEXT DEFAULT '';`
- [ ] 1.2 在 `INIT_SQL` 的 `task_tickets` 建表 DDL 中追加 `result_analysis TEXT DEFAULT ''` 列定义（确保新环境直接建表也包含该列）

**预期结果**: 服务启动后自动迁移，`task_tickets` 表多出 `result_analysis` 列，所有旧记录该列值为空字符串。

---

## Task 2: 后端 — 修改 task_executor.py 数据解析逻辑

> 关联: [FR-018, FR-019] → [design.md §3.1]

- [ ] 2.1 移除 `analysis` 追加到 `summary` 的逻辑（L227-231），`analysis` 改为独立存储到 `result_analysis`
- [ ] 2.2 修改 `UPDATE task_tickets` SQL 语句，新增 `result_analysis=$7` 参数绑定
- [ ] 2.3 在 JSON 结果行解析完成后，将日志输出替换为可读摘要（如 `✅ 任务成功: ONES-404174 (耗时 146.6s)`），不再将原始 JSON 存入日志表
- [ ] 2.4 JSON 结果行解析末尾加 `continue`，跳过通用日志保存逻辑
- [ ] 2.5 额外广播 `{type: "progress"}` 消息，触发前端实时刷新工单结果区

**预期结果**: runner 输出的 JSON 行被结构化存储到各列，日志中仅留精炼摘要，前端日志查看器不再显示大段 JSON。

---

## Task 3: 后端 — 扩展 tasks.py API 响应

> 关联: [FR-021] → [design.md §3.2]

- [ ] 3.1 `TicketResult` Pydantic 模型新增 `result_analysis: str = ""` 字段
- [ ] 3.2 `get_task()` 函数中 `TicketResult` 构造新增 `result_analysis` 字段映射
- [ ] 3.3 `get_ticket_report()` 函数返回值新增 `analysis` 字段

**预期结果**: `GET /api/tasks/:id` 响应中每个工单对象包含 `result_analysis` 字段；`GET /api/tasks/:id/tickets/:tid/report` 响应中包含 `analysis` 字段。

---

## Task 4: 前端 — 重新设计工单结果卡片

> 关联: [FR-020] → [design.md §4.1]

- [ ] 4.1 在工单卡片中新增"处理详情"折叠区域
  - 使用 `t._showAnalysis` 状态变量控制展开/折叠
  - 内容：将 `t.result_analysis` 通过 `renderMd()` 渲染为 Markdown 富文本
  - 折叠触发按钮：`▶ AI 处理详情`（折叠态）/ `▼ AI 处理详情`（展开态）
- [ ] 4.2 重新组织信息层次
  - 头部：工单号 + 状态 + 耗时 + 评价
  - 中部：AI 结论条（`result_conclusion`）
  - 展开区 1：处理详情（`result_analysis`）
  - 展开区 2 / 弹窗：完整报告（`result_report`）
- [ ] 4.3 报告路径提示
  - 当 `result_report` 为空且 `report_path` 有值时，显示 `⚠️ 报告路径: {path}（未能获取内容）`
- [ ] 4.4 处理详情区域样式
  - 背景色: `var(--bg-surface)`
  - 边框: `1px solid var(--border)`
  - 圆角: `var(--radius-sm)`
  - 内边距: `16px`
  - 最大高度: `500px`，超出滚动
- [ ] 4.5 向后兼容
  - 当 `result_analysis` 为空时，不显示"AI 处理详情"折叠区域
  - 当 `result_report` 为空且 `report_path` 也为空时，不显示报告相关按钮

**预期结果**: 工单结果卡片呈现为：头部摘要 → AI 结论 → 可折叠的分析详情 → 报告按钮。旧数据正常显示不报错。

---

## Task 5: 前端 — 日志查看器优化

> 关联: [FR-019]

- [ ] 5.1 确认 WebSocket 日志接收逻辑无需修改（后端已在 Task 2 中完成 JSON 行替换）
- [ ] 5.2 验证日志中是否还有残留 JSON 文本（处理 `log_type: "system"` 行的特殊颜色样式已存在）

**预期结果**: 日志查看器中工单结果行显示为蓝色 `SYS` 标签 + 可读摘要文本，不再显示 JSON 大文本。

---

## Task 6: 部署验证

> 关联: 全部 FR

- [ ] 6.1 构建新的 Docker 镜像（前端 + 后端）
- [ ] 6.2 部署到 172.60.1.35 测试服务器
- [ ] 6.3 验证数据库迁移：确认 `result_analysis` 列已创建
- [ ] 6.4 提交一个新的测试任务，验证以下内容：
  - 日志中不显示 JSON 大文本
  - 工单结果卡片有"AI 处理详情"折叠区域
  - 展开后显示 Markdown 渲染的分析内容
  - "查看详细报告"弹窗正常展示
- [ ] 6.5 验证历史任务（旧数据）是否正常显示

**预期结果**: 新任务完整展示所有结构化信息；旧任务正常但详情区域不显示（因无数据）。

---

## Task 7: 用户使用频次统计图表

> 关联: [FR-022] → [design.md section 5.5]

- [ ] 7.1 后端 `admin.py` 新增 `GET /api/admin/users/{user_id}/trends` API
  - 参数: `days`（默认90）、`granularity`（day/week/month）
  - SQL: `SELECT DATE_TRUNC('{trunc}', created_at)::DATE, COUNT(*), SUM(ticket_count) FROM tasks WHERE user_id=$1 ... GROUP BY dt ORDER BY dt`
  - 返回格式: `[{date, task_count, ticket_count}]`
- [ ] 7.2 前端 `api/index.js` 新增 `getUserTrends(userId, days, granularity)` 方法
- [ ] 7.3 改造 `AdminUserDetail.vue`
  - 添加 ECharts 图表区域（400px 高度，暗色主题）
  - 添加时间粒度切换器：按日 / 按周 / 按月（radio-button）
  - 添加时间范围选择器：近30天 / 近90天 / 近180天
  - 折线图展示任务数 + 柱状图展示工单数（复用 AdminTrend.vue 的配色）
  - 图表下方保留现有任务列表
- [ ] 7.4 空数据处理：用户无任务数据时显示"暂无使用记录"

**预期结果**: 管理员进入用户明细页，顶部看到使用频次趋势图表，可切换日/周/月粒度和时间范围。下方仍展示任务历史列表。

---

## 任务依赖关系

```
Task 1 (数据库) ──┐
                   ├──→ Task 2 (后端解析) ──→ Task 3 (API扩展) ──→ Task 4 (前端卡片) ──┐
                   │                                                   │                │
                   │                                      Task 5 (日志优化) ──┘          │
                   │                                                                    ├──→ Task 8 (部署)
Task 7 (用户统计图表 — 独立，可并行) ────────────────────────────────────────────────────┘
```

## 预估工时

| Task | 预估 | 说明 |
|------|------|------|
| Task 1 | 10 min | 加两行 SQL |
| Task 2 | 30 min | 核心逻辑修改，需谨慎处理 |
| Task 3 | 15 min | 模型和映射扩展 |
| Task 4 | 60 min | 前端主要工作量 |
| Task 5 | 10 min | 确认验证 |
| Task 6 | 30 min | 构建部署验证 |
| Task 7 | 45 min | 后端API + 前端ECharts图表 |
| **合计** | **~3.5h** | |
