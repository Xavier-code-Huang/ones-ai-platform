# Runner 产出展示增强方案

同步中文文档 — 更新时间: 2026-03-17 20:43

## 现状

Runner `--json-output` 当前只输出简单文本（"执行成功/失败"），但 Claude 实际产出包含丰富结构化信息：
- 工单标题、处理结论、原因分析、关联修复代码、报告文件路径

## 改造目标

| 展示端 | 内容 |
|--------|------|
| 前端-任务详情 | 工单卡片显示标题、结论、分析摘要、报告链接 |
| 邮件通知 | HTML 包含完整分析报告 + 1.md 内嵌 |
| Webhook | 摘要含工单标题和结论 |

## 改造范围

### 1. Runner (ones_task_runner.py)
- 增强 JSON 输出：从 Claude stdout 解析结构化字段
- 新增字段: title, conclusion, analysis, related_code, report_path

### 2. 后端 (task_executor.py + database.py)
- 解析新 JSON 字段存入数据库
- 新增 DB 列: ticket_title, result_conclusion, report_path
- 完成后通过 SSH 下载 1.md 报告内容存入 result_report

### 3. 前端 (TaskDetail.vue)
- 工单结果卡片改为结构化展示（标题、结论、分析、报告入口）

### 4. 邮件 (notifications.py)
- HTML 邮件包含完整工单结构化信息 + 1.md 报告内嵌

### 5. 新增 API (tasks.py)
- `GET /api/tasks/{id}/tickets/{ticket_id}/report` 返回报告内容
