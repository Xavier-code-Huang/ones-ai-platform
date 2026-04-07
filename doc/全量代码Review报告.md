# ones-AI 全量代码深度 Review

> 生成时间: 2026-03-17 09:31:34

# Round 1: Python 后端 AST 深度检查


## admin.py (342 lines)
  - 函数: 8, 类: 5, 导入: 10

## auth.py (184 lines)
  - 函数: 6, 类: 3, 导入: 10
  [WARNING] auth.py:112: 函数 `login` 过长 (65 行)

## config.py (80 lines)
  - 函数: 0, 类: 2, 导入: 2

## crypto.py (62 lines)
  - 函数: 3, 类: 0, 导入: 4

## database.py (233 lines)
  - 函数: 5, 类: 0, 导入: 3

## evaluations.py (85 lines)
  - 函数: 2, 类: 2, 导入: 6

## log_streamer.py (78 lines)
  - 函数: 1, 类: 0, 导入: 6

## main.py (159 lines)
  - 函数: 4, 类: 0, 导入: 16

## notifications.py (130 lines)
  - 函数: 3, 类: 0, 导入: 4

## ones_client.py (129 lines)
  - 函数: 4, 类: 1, 导入: 3

## servers.py (238 lines)
  - 函数: 6, 类: 4, 导入: 11

## ssh_pool.py (111 lines)
  - 函数: 4, 类: 0, 导入: 5

## task_executor.py (301 lines)
  - 函数: 8, 类: 0, 导入: 10
  [WARNING] task_executor.py:107: 函数 `_execute_task` 过长 (179 行)

## tasks.py (243 lines)
  - 函数: 5, 类: 5, 导入: 8

**后端统计**: 14 文件, 2375 行, 59 函数, 22 类, 98 导入


# Round 2: Runner 代码检查

## ones_task_runner.py (976 lines)
  - 类: ['Config', 'ClaudeExecutor', 'ExcelManager', 'ProcessLogger', 'UsageTracker', 'TaskRunner']
  - 函数: 34
  - ✅ --code-dirs 参数已接入
  - ✅ codeDirectory 字段已添加
  - ✅ 提示词含代码位置指引
  [INFO] ones_task_runner.py: nargs='+' 出现 3 次
  [INFO] ones_task_runner.py: 使用 shell=True 执行命令（注意命令注入风险）
  - ✅ 有超时控制


# Round 3: 前端 Vue 组件检查


## App.vue (68 lines)
  - IDs: ['app-sidebar']

## index.js (52 lines)
  [INFO] index.js: 密码字段缺少 autocomplete 属性

## main.js (28 lines)

## index.js (29 lines)

## auth.js (29 lines)
  [INFO] auth.js: 密码字段缺少 autocomplete 属性

## AdminConfigs.vue (71 lines)
  [INFO] AdminConfigs.vue: 密码字段缺少 autocomplete 属性
  - IDs: ['admin-configs', 'save-configs']

## AdminEval.vue (54 lines)
  - IDs: ['admin-eval']

## AdminTrend.vue (48 lines)
  - IDs: ['admin-trends']

## AdminUserDetail.vue (37 lines)
  - IDs: ['admin-user-detail']

## AdminUsers.vue (28 lines)
  - IDs: ['admin-users']

## AdminView.vue (69 lines)
  - IDs: ['admin-overview']

## DashboardView.vue (146 lines)
  - IDs: ['dashboard-page', "'server-'+s.id", "'go-task-'+s.id", "'verify-'+s.id", 'verify-dialog']...

## LoginView.vue (78 lines)
  [INFO] LoginView.vue: 密码字段缺少 autocomplete 属性
  - IDs: ['login-page', 'login-card', 'login-email', 'login-password', 'login-submit']

## TaskDetailView.vue (156 lines)
  [WARNING] TaskDetailView.vue: 使用 v-html — 注意 XSS 风险
  - IDs: ['task-detail-page', 'log-viewer']

## TaskView.vue (244 lines)
  - IDs: ['task-create-page', 'select-server', 'select-credential', 'add-row-btn', 'preview-btn']...


# Round 4: 部署与配置检查

## docker-compose.yml
  - ✅ 容器重启策略已配置
  [INFO] docker-compose.yml: 缺少容器健康检查
  - ✅ 持久化卷已配置

## .env
  [WARNING] .env: JWT_SECRET_KEY 使用的是默认值 — 生产环境必须更换
  [WARNING] .env: CRYPTO_KEY 使用的是默认值 — 生产环境必须更换
  [WARNING] .env: DEBUG=true — 生产环境应设为 false

## .gitignore
  - ✅ .env 已排除
  - ✅ node_modules 已排除


# Round 5: 跨模块一致性检查

## 前端 API 路径 (0 个)

## 后端路由前缀 (5 个)
  - /api/admin
  - /api/auth
  - /api/evaluations
  - /api/servers
  - /api/tasks

## DB 表 (9 张): users, servers, user_server_credentials, tasks, task_tickets, task_evaluations, task_logs, notification_logs, external_configs

## Runner CLI 参数: ['--code-dirs', '--config', '--create-template', '--excel', '--json-output', '--notes', '--tickets']
## Executor 使用的参数: ['--code-dirs', '--json-output', '--notes', '--tickets']
  - ✅ 参数一致


# Round 6: 安全审计

  ✅ JWT 认证
  ✅ AES-256 加密
  ✅ CORS 控制
  ✅ 管理员权限
  ✅ Token 校验
  ✅ 密码加密存储
  ✅ SSH 凭证验证
  ✅ SQL 参数化
  ✅ 输入校验 (Pydantic)
  ✅ 日志脱敏


# 汇总

- **严重问题 (CRITICAL)**: 0
- **警告 (WARNING)**: 6
- **信息 (INFO)**: 7
- **代码规模**: 后端 2375 行 / Runner 976 行 / 前端 15 文件

## 警告清单

- [WARNING] auth.py:112: 函数 `login` 过长 (65 行)
- [WARNING] task_executor.py:107: 函数 `_execute_task` 过长 (179 行)
- [WARNING] TaskDetailView.vue: 使用 v-html — 注意 XSS 风险
- [WARNING] .env: JWT_SECRET_KEY 使用的是默认值 — 生产环境必须更换
- [WARNING] .env: CRYPTO_KEY 使用的是默认值 — 生产环境必须更换
- [WARNING] .env: DEBUG=true — 生产环境应设为 false

## 信息清单

- [INFO] ones_task_runner.py: nargs='+' 出现 3 次
- [INFO] ones_task_runner.py: 使用 shell=True 执行命令（注意命令注入风险）
- [INFO] index.js: 密码字段缺少 autocomplete 属性
- [INFO] auth.js: 密码字段缺少 autocomplete 属性
- [INFO] AdminConfigs.vue: 密码字段缺少 autocomplete 属性
- [INFO] LoginView.vue: 密码字段缺少 autocomplete 属性
- [INFO] docker-compose.yml: 缺少容器健康检查