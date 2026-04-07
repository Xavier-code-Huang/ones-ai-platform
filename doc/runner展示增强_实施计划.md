# Runner 产出展示增强 — 实施计划

更新时间: 2026-03-17 21:15

## 背景

当前 Runner `--json-output` 仅输出简单结果（`ticket_id`, `status`, `duration`, `summary`），但 Claude 处理工单后的 stdout 实际包含丰富的结构化信息。本次改造目标是在**后端、前端、邮件通知**三端完整展示 AI 分析产出。

> **注意**: Runner 脚本（`ones_task_runner.py`）位于服务器端（35机 Docker 容器内），本地未找到源码副本。后端先做好兼容。

---

## 改造范围

### 1. 数据库 (database.py)

`task_tickets` 表新增 3 列：
- `ticket_title`: 工单标题
- `result_conclusion`: AI 处理结论
- `report_path`: 远程报告文件路径

### 2. 任务执行引擎 (task_executor.py)

- 解析 Runner 新增 JSON 字段
- 完成后通过 SSH 下载 `1.md` 报告存入 `result_report`

### 3. API (tasks.py)

- `TicketResult` 模型新增 3 个字段
- 新增 `GET /api/tasks/{id}/tickets/{ticket_id}/report` 接口

### 4. 前端 (TaskDetailView.vue)

- 工单卡片结构化展示：标题、结论、分析摘要、报告入口
- API 模块新增 `getTicketReport`

### 5. 通知 (notifications.py)

- Webhook 摘要增加工单标题
- 邮件 HTML 新增标题列、结论列、报告内嵌

## 验证方案

- 数据库迁移验证脚本
- API 端点验证
- 前端 UI 验证
- 旧数据兼容性验证
