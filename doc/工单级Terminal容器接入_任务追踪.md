# 工单级 Web Terminal 容器接入 — 任务追踪

## 规划阶段
- [x] 探索 ones-AI 工作区全貌
- [x] 研究 lango-remote 容器接入实现
- [x] 对比两个系统的终端实现差异
- [x] 撰写实施计划
- [ ] 用户审批实施计划

## 后端实施
- [x] 重构 `terminal_ws.py` — 工单级 WebSocket 端点
  - [x] 新端点 `/ws/tickets/{ticket_db_id}/terminal`
  - [x] 移植 docker attach --sig-proxy=false
  - [x] 移植 Docker API resize
  - [x] 环形缓冲区回放（可选）
- [x] 新增容器管理 API
  - [x] `GET /api/tasks/{id}/tickets/{tid}/container` — 容器状态
  - [x] `POST /api/tasks/{id}/tickets/{tid}/container/start` — 启动容器
- [x] 任务执行器适配 — 记录容器名到数据库

## 前端实施
- [x] 升级 `WebTerminal.vue` — 支持工单级多实例
  - [x] 支持接收 `ticketDbId` 参数
  - [x] 连接及重连逻辑适配新的 WebSocket URL
  - [x] 增加自动写入 `/resume` 指令的能力
- [x] 重构 `TaskDetailView.vue`
  - [x] 移除顶层公共 Terminal，将会话转移至工单粒度
  - [x] 获取所选工单的容器状态，根据状态展示不同的控制按钮（呼出终端 / 唤醒容器 / 暂未分配）
  - [x] 点击“唤醒干预”触发 POST 请求，成功后自动连接 Web Terminal
- [ ] 修改 `TicketCard.vue` — 增加终端/重启按钮
- [ ] 更新 `api/index.js` — 新增 API 封装

## 验证与部署
- [ ] 本地前端构建验证
- [ ] 后端导入验证
- [ ] 部署到 35 服务器
- [ ] 浏览器功能测试
