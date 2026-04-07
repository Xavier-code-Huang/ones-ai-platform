# ones-AI 准确度评测系统

## Phase 1: Gerrit 对接模块
- [x] 验证 Gerrit 连通性 (182:8081 ✅, Basic Auth)
- [x] 确认工单号映射关系 (ONES-xxx = STORY-xxx / BUG-xxx)
- [x] 验证匹配率 (20个工单中15%有Gerrit提交)
- [ ] 编写 `gerrit_client.py` — Gerrit REST API 客户端
- [ ] 新建 `accuracy_evaluations` 数据库表

## Phase 2: 评测引擎
- [ ] 编写 `accuracy_engine.py` — 五维度评分引擎
  - [ ] 文件定位匹配 (从报告提取文件名 vs Gerrit修改文件)
  - [ ] 根因定位 (函数级匹配)
  - [ ] 方案相似度 (LLM 语义对比)
  - [ ] 可操作性 (报告结构化程度)
  - [ ] 整体一致性 (LLM 综合判断)
- [ ] 集成到后端 API

## Phase 3: API + 前端
- [ ] 评测 API 端点
- [ ] 前端展示页面
- [ ] 部署验证
