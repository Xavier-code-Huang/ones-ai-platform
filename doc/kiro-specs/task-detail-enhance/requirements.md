# 任务详情展示增强 + 用户统计图表 — 需求规格文档

> **版本**: 1.1.0  
> **日期**: 2026-03-18  
> **状态**: 待审阅  
> **关联设计文档**: [design.md](file:///f:/Ones-AI专项开发/.kiro/specs/task-detail-enhance/design.md)  
> **关联任务文档**: [tasks.md](file:///f:/Ones-AI专项开发/.kiro/specs/task-detail-enhance/tasks.md)  
> **关联已有需求**: [requirements.md](file:///f:/Ones-AI专项开发/.kiro/specs/requirements.md) FR-007, FR-012  

---

## 1. 问题陈述

### 1.1 现状

当前平台存在以下核心问题：

| # | 问题描述 | 影响 |
|---|---------|------|
| P1 | **执行日志中直接显示 runner 输出的原始 JSON 大文本**，包含 `ticket_id`、`status`、`analysis` 等所有字段的 JSON 一行式输出，用户观感极差 | 非技术用户完全无法阅读 |
| P2 | **runner 输出中的报告路径（如 `workspace/doc/ONES-404174/report/1.md`）在前端没有展示入口**，用户不知道有详细报告 | 有价值的信息被埋没 |
| P3 | **"工单处理结果"区域仅显示一行摘要文本**，看不到 AI 的思考过程、分析内容和完整结论 | 开发者无法获取有效参考信息 |
| P4 | **数据不持久化**：工单处理的详细结果（analysis、conclusion 等）仅存在于远程服务器的 runner 日志中。一旦容器销毁或日志清理，所有结果信息丢失不可恢复 | 关键业务数据丢失风险 |
| P5 | **用户明细页缺少使用频次统计图表**：管理员进入单个用户明细只能看到任务列表，无法直观感知该用户每天/每周/每月的使用频次变化趋势 | 管理层无法评估单个用户的 AI 工具采纳程度 |

### 1.2 用户故事

**US-1（开发者）**:  
**AS** 一个使用 ones-AI 平台提交工单任务的开发者  
**I WANT** 在任务完成后清晰、结构化地查看每个工单的处理详情，包括 AI 的分析思路、技术方案、修改确认表和完整报告  
**SO THAT** 我可以快速判断 AI 处理是否正确，决定是否采纳修改，无需 SSH 到远程服务器查看原始文件

**US-2（管理员）**:  
**AS** ones-AI 平台的管理员  
**I WANT** 在用户明细页面看到某个用户按天/周/月维度的使用频次折线图或柱状图  
**SO THAT** 我可以评估该用户的 AI 工具采纳程度，发现使用波动并及时跟进

---

## 2. 功能需求（EARS 标注法）

### FR-018 工单结果结构化存储与持久化

> 扩展 FR-007，解决 P4 问题

**WHEN** runner 执行完成并输出工单结果 JSON  
**THE SYSTEM SHALL** 解析 JSON 中的所有结构化字段（`analysis`、`conclusion`、`title`、`report_path`、`duration`、`summary`），将它们分别持久化存储到数据库中对应的列。

**验收标准**:
1. `task_tickets` 表新增 `result_analysis` 列（TEXT），存储 runner 输出的 `analysis` 字段完整内容
2. 现有 `result_conclusion` 列存储 `conclusion` 字段（简短结论）
3. 现有 `result_summary` 列存储 `summary` 字段（一行摘要）
4. 现有 `result_report` 列存储从远程服务器下载的完整 `1.md` 报告内容
5. 后端 `task_executor.py` 在解析 runner JSON 输出时，不再将 `analysis` 追加到 `summary`，而是独立存储
6. 数据一旦写入数据库，即使远程服务器容器重建、日志清空，ones-AI 平台仍可完整展示所有历史结果

---

### FR-019 执行日志中的 JSON 智能处理

> 解决 P1 问题

**WHEN** 执行日志中出现 runner 输出的工单结果 JSON 行（以 `{` 开头且包含 `"ticket_id"` 的行）  
**THE SYSTEM SHALL** 不将该行以原始文本形式存入日志，而是存储一条可读的状态摘要行。

**验收标准**:
1. 后端在收到 runner 的 JSON 结果行时，保存到日志表的内容替换为可读摘要，例如：`✅ 任务成功: ONES-404174 (耗时 146.6s)` 或 `❌ 任务失败: ONES-404174`
2. 原始 JSON 数据已通过 FR-018 持久化到 `task_tickets` 表结构化列中，日志中无需重复保存
3. 前端日志查看器中不再显示大段 JSON 文本

---

### FR-020 工单处理结果详情展示

> 解决 P2、P3 问题

**WHEN** 用户查看已完成任务的工单处理结果  
**THE SYSTEM SHALL** 以结构化、分区域的方式展示工单的完整处理信息，包括：处理详情、AI 思考内容、技术方案、以及完整报告。

**验收标准**:

#### 20.1 结果卡片区域重新设计

1. 每个工单结果卡片包含以下可视区，按顺序展示：
   - **头部信息栏**: 工单号、状态标签（成功/失败）、用时、评价按钮
   - **AI 结论条**: 一句话结论（`result_conclusion`），使用醒目样式
   - **处理详情区（可折叠）**: 将 `result_analysis`（Markdown 格式） 渲染为富文本展示，包含 AI 的分析过程、修改确认表格、技术方案等
   - **详细报告区（可折叠/对话框）**: 展示 `result_report`（完整 `1.md` 报告内容），Markdown 渲染

2. 默认状态：
   - 展开：头部信息栏 + AI 结论条
   - 折叠：处理详情区、详细报告区（点击展开）

3. Markdown 渲染支持：标题层级、表格、代码块、列表、加粗/斜体

#### 20.2 详细报告展示

4. **WHEN** 工单的 `result_report` 字段有内容（即 `1.md` 报告已成功下载入库）  
   **THE SYSTEM SHALL** 在卡片底部显示"📄 查看详细报告"按钮，点击弹出对话框渲染完整报告

5. **WHEN** 工单的 `result_report` 为空但 `report_path` 有值  
   **THE SYSTEM SHALL** 显示"⚠️ 报告文件路径: {path}（未能获取内容）"的提示文字

6. **WHEN** 用户点击"查看详细报告"按钮  
   **THE SYSTEM SHALL** 首先尝试从本地数据库读取报告内容；如数据库无内容则通过 API 触发后端重新从远程服务器下载

---

### FR-021 API 接口增强

> 支撑 FR-018 ~ FR-020 的后端数据供给

**WHEN** 前端请求任务详情 API（`GET /api/tasks/:id`）  
**THE SYSTEM SHALL** 在工单结果数据中返回新增的 `result_analysis` 字段。

**验收标准**:
1. `GET /api/tasks/:id` 响应中每个工单对象新增 `result_analysis` 字段（string, 可为空）
2. `GET /api/tasks/:id/tickets/:tid/report` 响应中新增 `analysis` 字段
3. 所有新增字段在 API 文档（Swagger）中有描述

---

### FR-022 用户使用频次统计图表

> 扩展 FR-012（用户明细），解决 P5 问题

**WHEN** 管理员进入某个用户的使用明细页（`/admin/users/:id`）  
**THE SYSTEM SHALL** 在页面顶部展示该用户按日/周/月维度的使用频次趋势图表。

**验收标准**:

1. 页面顶部新增趋势图表区域，使用 ECharts 绘制
2. 支持三种时间粒度切换：按日 / 按周 / 按月（与全局趋势分析页一致的 radio-button 切换器）
3. 图表展示两条数据线：
   - **任务数**（折线图）：该用户在每个时间单位创建的任务数
   - **工单数**（柱状图）：该用户在每个时间单位处理的工单总数
4. 支持时间范围选择器：近 30 天 / 近 90 天 / 近 180 天（默认 90 天）
5. 鼠标悬停显示 tooltip：日期、任务数、工单数
6. 图表下方保留现有的任务列表（历史记录）
7. 新增后端 API：`GET /api/admin/users/{user_id}/trends?days=90&granularity=day`
   - 返回格式：`[{date, task_count, ticket_count}]`
   - 数据基于 `tasks` 表按 `user_id` + `DATE_TRUNC` 聚合

---

## 3. 非功能需求

### NFR-020 数据完整性
- 所有工单结果数据必须在 runner 执行完成后 **即时** 持久化到数据库
- 数据库中的分析与报告字段支持大文本（TEXT 类型，无长度限制）

### NFR-021 展示性能
- analysis 和 report 的 Markdown 渲染不应导致页面卡顿
- 大文本内容（>50KB）使用懒加载或虚拟滚动
- 用户趋势图表数据量合理（最多 365 天），不卡顿

### NFR-022 向后兼容
- 已有的历史任务数据（`result_analysis` 为空的旧记录）可正常展示，不报错
- 新增数据库列使用 `ADD COLUMN IF NOT EXISTS` + `DEFAULT ''` 确保无破坏性迁移
- 用户无任务数据时，图表区域显示"暂无数据"提示，不报错

---

## 4. 范围说明

### 本次范围内（In Scope）
| 项 | 描述 |
|----|------|
| 数据层 | 新增 `result_analysis` 列，调整数据存储逻辑 |
| 后端 | 修改 `task_executor.py` 解析逻辑、`tasks.py` API 响应 |
| 后端 | 新增 `admin.py` 用户趋势聚合 API |
| 前端 | 重新设计 `TaskDetailView.vue` 工单结果卡片 |
| 前端 | 增强 `AdminUserDetail.vue` 增加 ECharts 趋势图表 |
| 数据库迁移 | `database.py` MIGRATION_SQL 新增列 |

### 本次范围外（Out of Scope）
| 项 | 说明 |
|----|------|
| Runner 端代码修改 | runner 输出格式已满足需求，无需修改 |
| 移动端适配 | 仅桌面端（最小 1280px） |
