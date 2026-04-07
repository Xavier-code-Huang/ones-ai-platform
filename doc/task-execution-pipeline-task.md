# 任务执行流水线重构 — 实施进度

## Task 0: 数据库备份
- [x] 备份生产数据库到本地 `F:\Ones-AI专项开发\数据库备份\`

## Task 1: 数据库迁移
- [x] 1.1 `database.py` 添加 `task_ticket_phases` 建表
- [x] 1.2 `database.py` 添加 `user_code_paths` 建表
- [x] 1.3 `task_logs` 表添加 `phase_name` 字段
- [x] 1.4 部署到服务器验证

## Task 2: 后端阶段模块 (`phases.py`)
- [x] 2.1 创建 `phases.py`（206行）
- [x] 2.2 实现 `init_phases()`, `advance_phase()`, `get_phases()`, `complete_remaining_phases()`, `format_phase_for_ws()`

## Task 3: WebSocket 协议扩展
- [x] 3.1 `log_streamer.py` 推送 `phases_snapshot` 消息
- [x] 3.2 历史 phase + phase_name 日志数据推送

## Task 4: task_executor 阶段集成
- [x] 4.1 导入 phases 模块
- [x] 4.2 工单开始时 init 8 个阶段 + 推进前 4 个阶段
- [x] 4.3 解析 `[PHASE]` 标记行推进后续阶段
- [x] 4.4 `_save_log()` 增加 `phase_name` 参数
- [x] 4.5 工单完成后清理剩余阶段

## Task 5: API 扩展（阶段查询 + 工单编辑）
- [x] `GET /tasks/{id}/tickets/{id}/phases`
- [x] `PUT /tasks/{id}/tickets/{id}` (pending 工单编辑)
- [x] `tasks.py` 日志查询添加 `phase_name`

## Task 6: 代码目录历史路径 API
- [x] `GET /tasks/code-paths?server_id=`
- [x] `DELETE /tasks/code-paths/{id}`
- [x] 任务创建时自动 upsert 代码路径

## Task 7: 前端 CSS 扩展
- [x] 8 个 phase 相关 CSS 变量

## Task 8: PhaseTimeline 组件
- [x] 5 种状态（pending/active/completed/failed/skipped）
- [x] 入场动画、呼吸灯、持续时间

## Task 9: TicketCard 组件
- [x] 4 种状态卡片、active 高亮、hover 编辑按钮

## Task 10: TaskDetailView 重构
- [x] 双栏布局（左 280px TicketCard + 右 PhaseTimeline + 详情）
- [x] WS `phase_change`/`phases_snapshot` 消息处理
- [x] 编辑工单弹窗

## Task 11: CodePathSelect 组件
- [x] 历史下拉 + 自由输入 + 单项删除

## 前端构建验证
- [x] `npm run build` 成功（2240 模块，67秒）

## Task 12: TaskView 重构
- [ ] 任务提交页面 UI 优化

## Task 13: AI 预分析（讨论项）
- [ ] ONES 工单预解析

## Task 14: 工单卡死防护
- [ ] 超时降级 + 孤立工单清理

## Task 15: Subagent 管线实现
- [ ] 4 个 Subagent 定义文件 + executor 集成

## Task 16: 构建与部署
- [/] 前端构建完成，等待部署

## Task 17: 端到端验证
- [ ] WebSocket 阶段推送验证
