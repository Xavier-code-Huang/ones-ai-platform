# 任务执行流水线重构 — 任务分解（v2）

> **功能名称**: task-execution-pipeline  
> **日期**: 2026-03-26  
> **版本**: v2（新增 Task 12~17）  
> **状态**: 待审阅

---

## Task 1: 数据库迁移
> 关联: [FR-101, FR-103, FR-107] → [design.md §2]

- [ ] 1.1 `database.py` 添加 `task_ticket_phases` 建表
- [ ] 1.2 `database.py` 添加 `user_code_paths` 建表
- [ ] 1.3 `task_logs` 表添加 `phase_name` 字段
- [ ] 1.4 部署到服务器验证

**预期结果**: 新表存在，字段完整  
**验证**: `\dt task_ticket_phases` + `\dt user_code_paths` 返回结果

---

## Task 2: 后端阶段模块 (`phases.py`)
> 关联: [FR-101, FR-104] → [design.md §3.1]

- [ ] 2.1 创建 `phases.py`，定义 `PIPELINE_PHASES`
- [ ] 2.2 实现 `init_phases()`, `advance_phase()`, `get_phases()`

**预期结果**: 调用 `init_phases(42)` 后数据库出现 8 条记录  
**验证**: SQL 查询确认记录数

---

## Task 3: WebSocket 协议扩展
> 关联: [FR-103] → [design.md §3.3]

- [ ] 3.1 `task_executor.py` 新增 `_broadcast_phase()`
- [ ] 3.2 `log_streamer.py` 连接时推送历史 phase 数据

**预期结果**: 浏览器 WS 面板可见 `phase_change` 消息  
**验证**: 开发者工具 Network > WS

---

## Task 4: task_executor 阶段集成
> 关联: [FR-103, FR-105] → [design.md §3.2]

- [ ] 4.1 执行流中调用 `init_phases()` 和 `advance_phase()`
- [ ] 4.2 解析 `[PHASE]` 标记行
- [ ] 4.3 保持现有日志/JSON 解析不变

**预期结果**: 执行任务后 phases 记录依次更新  
**验证**: SQL 查询阶段状态变化

---

## Task 5: 阶段查询 + 工单编辑 API
> 关联: [FR-101, FR-108] → [design.md §3.4]

- [ ] 5.1 `GET /tasks/:id/tickets/:tid/phases` 阶段查询
- [ ] 5.2 `PUT /tasks/:id/tickets/:tid` 编辑 pending 工单
- [ ] 5.3 编辑校验（仅允许 pending 状态）

**预期结果**: curl 请求返回正确数据  
**验证**: `curl -X PUT` 修改 pending 工单的 note 字段

---

## Task 6: 代码目录历史路径 API
> 关联: [FR-107] → [design.md §3.4]

- [ ] 6.1 创建任务时自动保存路径到 `user_code_paths`
- [ ] 6.2 `GET /users/me/code-paths?server_id=X` 查询
- [ ] 6.3 `DELETE /users/me/code-paths/:id` 删除

**预期结果**: 创建任务后路径被保存，下次查询可返回  
**验证**: 创建任务 → 查询路径列表 → 确认存在

---

## Task 7: 前端 CSS 设计系统扩展
> 关联: [FR-106] → [design.md §4.4]

- [ ] 7.1 `index.css` 添加 phase 相关变量
- [ ] 7.2 时间线基础样式（连线、圆点、动画）

**预期结果**: CSS 变量可用，时间线基础视觉正确  
**验证**: 浏览器检查元素

---

## Task 8: PhaseTimeline 组件
> 关联: [FR-101, FR-102] → [design.md §4.2]

- [ ] 8.1 创建 `PhaseTimeline.vue`
- [ ] 8.2 节点渲染（icon + label + status + duration）
- [ ] 8.3 状态动画（pending=灰、active=脉冲蓝、completed=绿✓、failed=红✗）
- [ ] 8.4 节点展开/收起 + 入场动画

**预期结果**: 组件渲染完整时间线  
**验证**: Mock 数据测试各状态视觉表现

---

## Task 9: TicketCard 组件
> 关联: [FR-100, FR-108] → [design.md §4.2]

- [ ] 9.1 创建 `TicketCard.vue`（工单号、状态、摘要）
- [ ] 9.2 pending 状态显示编辑按钮
- [ ] 9.3 编辑弹窗（修改 note、code_directory）
- [ ] 9.4 点击切换右侧时间线

**预期结果**: 卡片可点击切换，pending 卡片可编辑  
**验证**: 浏览器交互测试

---

## Task 10: TaskDetailView 页面重构
> 关联: [FR-106, FR-100, FR-102] → [design.md §4.1]

- [ ] 10.1 双栏布局（工单列表 + 时间线）
- [ ] 10.2 集成 PhaseTimeline + TicketCard
- [ ] 10.3 WS 接收 `phase_change` 实时更新
- [ ] 10.4 兼容模式（历史任务无 phase）
- [ ] 10.5 保留评价/打回/报告/日志功能
- [ ] 10.6 移动端适配

**预期结果**: 完整的双栏任务详情页  
**验证**: 历史任务兼容 + 新任务时间线推进 + 移动端布局

---

## Task 11: CodePathSelect 组件
> 关联: [FR-107] → [design.md §4.3]

- [ ] 11.1 创建 `CodePathSelect.vue`
- [ ] 11.2 下拉显示历史路径（按频率排序）
- [ ] 11.3 支持自由输入新路径
- [ ] 11.4 支持删除历史路径

**预期结果**: 代码目录输入支持下拉选择  
**验证**: 浏览器交互测试

---

## Task 12: TaskView 任务提交页重构
> 关联: [FR-109] → [design.md §4.2]

- [ ] 12.1 全新布局设计（参考 GitHub Actions dispatch UI）
- [ ] 12.2 服务器/凭证/Agent 选择器现代化
- [ ] 12.3 工单输入区支持拖拽排序
- [ ] 12.4 集成 CodePathSelect 组件
- [ ] 12.5 提交后平滑过渡到详情页

**预期结果**: 任务提交页视觉质量达到 GitHub Actions 水准  
**验证**: 浏览器端到端提交测试

---

## Task 13: AI 预分析（讨论项，优先级低）
> 关联: [FR-110] → [design.md §3.5]

- [ ] 13.1 后端 `POST /tasks/preview` API
- [ ] 13.2 调用 ONES API 获取工单标题/描述
- [ ] 13.3 前端"AI 预分析"按钮 + 结果展示
- [ ] 13.4 生成推荐提示词供用户修改

**预期结果**: 用户输入工单号后可获取 AI 建议的提示词  
**验证**: 输入真实工单号，确认返回的标题和建议准确

---

## Task 14: 工单卡死防护
> 关联: [FR-111] → [design.md §3.2]

- [ ] 14.1 工单提交去重检查（同 task_id 不允许重复 ticket_id）
- [ ] 14.2 单工单心跳超时机制（N 分钟无输出 → kill + failed）
- [ ] 14.3 `process.wait()` 超时保护
- [ ] 14.4 全局定时扫描，清理孤立 running 工单
- [ ] 14.5 清理现有数据库中的孤立工单

**预期结果**: runner 无响应或 SSH 断连后，后续工单正常继续  
**验证**: 模拟超时场景，确认后续工单不被卡住

---

## Task 15: Subagent 管线实现
> 关联: [FR-104, FR-105] → [design.md §5]

- [ ] 15.1 编写 4 个 subagent 定义文件（`analyzer.md`, `modifier.md`, `verifier.md`, `reporter.md`）
- [ ] 15.2 部署到服务器 `/opt/lango/subagents/` 目录
- [ ] 15.3 修改 `ones_task_runner.py`，主 prompt 指导 Claude 使用 subagent 管线
- [ ] 15.4 增加 `--max-turns 100` 以支持多 subagent 调用
- [ ] 15.5 添加 `[PHASE]` 标记输出
- [ ] 15.6 确保用户 agent-teams 内容注入到每个 subagent prompt

**预期结果**: runner 执行时 Claude 自动依次委派 4 个 subagent，每个阶段生成对应的 .md 文件  
**验证**: SSH 执行 ones-AI 命令，观察 stdout 中 subagent 委派日志和 workspace/ 下的文件生成

---

## Task 16: 构建与部署
> 关联: 全部 FR

- [ ] 16.1 `npm run build` 通过
- [ ] 16.2 部署前端 + 后端 + runner
- [ ] 16.3 数据库迁移执行

**预期结果**: 构建 0 错误，部署成功  
**验证**: `http://172.60.1.35:9621` 页面可访问

---

## Task 17: 端到端验证
> 关联: 全部 FR

- [ ] 17.1 创建测试任务 → 时间线实时推进
- [ ] 17.2 历史任务兼容展示
- [ ] 17.3 排队工单编辑
- [ ] 17.4 代码目录历史选择
- [ ] 17.5 移动端响应式

**预期结果**: 全链路可用  
**验证**: 浏览器完整走通流程
