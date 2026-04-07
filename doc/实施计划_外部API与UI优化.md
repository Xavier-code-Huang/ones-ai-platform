# 外部团队日志上报 API + 全平台 UI 优化

## 背景

1. **外部团队日志 API**：其他团队有自己的类似 ones-AI 的工单处理系统，需要一个开放接口上报使用日志（团队名称、成员、使用次数等），统计数据向我们现有的管理统计看齐。
2. **UI 全面优化**：现有 UI 配色偏"AI 感"（紫蓝渐变），需要去 AI 化，采用更专业、更现代的企业级配色。所有页面的动效、交互体验需要提升。

---

## 一、外部团队日志上报 API

### 数据库设计

```sql
-- 外部团队注册表
CREATE TABLE IF NOT EXISTS external_teams (
    id SERIAL PRIMARY KEY,
    team_name VARCHAR(100) UNIQUE NOT NULL,      -- 团队名称
    api_key VARCHAR(64) UNIQUE NOT NULL,          -- API Key（认证用）
    description TEXT DEFAULT '',
    contact_email VARCHAR(200) DEFAULT '',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 外部团队成员表
CREATE TABLE IF NOT EXISTS external_team_members (
    id SERIAL PRIMARY KEY,
    team_id INT NOT NULL REFERENCES external_teams(id),
    member_name VARCHAR(100) NOT NULL,
    member_email VARCHAR(200) DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(team_id, member_name)
);

-- 外部日志上报表（核心）
CREATE TABLE IF NOT EXISTS external_logs (
    id SERIAL PRIMARY KEY,
    team_id INT NOT NULL REFERENCES external_teams(id),
    member_name VARCHAR(100) NOT NULL,            -- 操作人
    ticket_id VARCHAR(50) DEFAULT '',             -- 工单号（可选）
    action_type VARCHAR(50) DEFAULT 'process',    -- 操作类型（process/review/fix等）
    status VARCHAR(20) DEFAULT 'completed',       -- completed/failed
    duration FLOAT DEFAULT 0,                     -- 耗时(秒)
    summary TEXT DEFAULT '',                      -- 摘要
    extra_data JSONB DEFAULT '{}',                -- 扩展字段
    reported_at TIMESTAMPTZ DEFAULT NOW()         -- 上报时间
);
```

### 后端 API

#### [NEW] [external.py](file:///f:/Ones-AI专项开发/ones-ai-platform/backend/external.py)

| 端点 | 方法 | 认证 | 说明 |
|------|------|------|------|
| `POST /api/external/report` | POST | API Key | 批量上报日志 |
| `GET /api/external/stats` | GET | Admin | 查看外部团队统计 |
| `POST /api/admin/external-teams` | POST | Admin | 注册新团队（生成 API Key）|
| `GET /api/admin/external-teams` | GET | Admin | 团队列表 |
| `DELETE /api/admin/external-teams/{id}` | DELETE | Admin | 注销团队 |

**上报接口请求体：**
```json
{
  "logs": [
    {
      "member_name": "张三",
      "ticket_id": "ONES-12345",
      "action_type": "process",
      "status": "completed",
      "duration": 120.5,
      "summary": "修复了xxx问题"
    }
  ]
}
```
Header: `X-API-Key: <team_api_key>`

---

## 二、UI/配色/动效 全面优化

### 配色方案：去 AI 化 → 专业企业级

| 元素 | 现有（AI 感） | 新方案（专业商务） |
|------|----------|------------|
| 主色 | `#6366f1` 紫 + `#3b82f6` 蓝渐变 | `#2563eb` 企业蓝单色 + `#0ea5e9` 辅助天蓝 |
| 背景 | `#0a0e1a` 极深黑蓝 | `#0f172a` Slate 900 |
| 卡片 | `#151d2e` + 玻璃态 | `#1e293b` Slate 800 + 微妙边框 |
| 强调梯度 | 紫→蓝渐变 | 单色蓝 + 白色文字，去掉 gradient text |
| 成功色 | 保持 `#22c55e` | 不变 |
| 语义 | 保持 | 不变 |

> **理念**：参考 Vercel Dashboard / Linear App 的暗色风格——干净、克制、专业，避免花哨渐变。

### 动效增强

| 组件 | 优化内容 |
|------|---------|
| 页面切换 | Vue `<transition>` 路由动画（slide-fade） |
| 卡片 | hover 微浮起 + 边框发光（柔和，不刺眼） |
| 数字统计 | 保留 counter 动画，加入 `counter-increment` CSS |
| 表格行 | hover 行高亮 + 左侧色条指示 |
| 按钮 | hover scale(1.02) + 阴影加深 |
| 侧边栏 | 导航项 hover 背景色块平滑过渡 |
| 图表 | ECharts 动画保留，配色跟随新方案 |

### 各页面优化计划

#### [MODIFY] [index.css](file:///f:/Ones-AI专项开发/ones-ai-platform/frontend/src/styles/index.css)
- 更新全部 CSS 变量为新配色
- 去掉 `--accent-gradient` 渐变文字效果
- 新增路由过渡动画 CSS
- 优化 glass-card 边框和阴影
- 新增 hover 微交互类

#### [MODIFY] [App.vue](file:///f:/Ones-AI专项开发/ones-ai-platform/frontend/src/App.vue)
- 侧边栏 logo 区域样式优化
- 新增侧边栏折叠功能
- 路由 `<transition>` 过渡效果
- 底部版本信息区域

#### [MODIFY] [LoginView.vue](file:///f:/Ones-AI专项开发/ones-ai-platform/frontend/src/views/LoginView.vue)
- 品牌 logo 区域替换为公司标识风格
- 登录表单卡片优化（毛玻璃+阴影）
- 背景去掉紫色光晕，改为深色网格/点阵

#### [MODIFY] [DashboardView.vue](file:///f:/Ones-AI专项开发/ones-ai-platform/frontend/src/views/DashboardView.vue)
- 欢迎横幅改为简洁版（去渐变文字）
- 服务器卡片添加状态指示条动画
- 任务列表行添加 hover 交互

#### [MODIFY] [AdminView.vue](file:///f:/Ones-AI专项开发/ones-ai-platform/frontend/src/views/AdminView.vue)
- 6 个统计卡加图标+小趋势线（sparkline）
- 新增"外部团队"统计卡片区域
- 底部加快速入口链接

#### [MODIFY] [AdminTrend.vue](file:///f:/Ones-AI专项开发/ones-ai-platform/frontend/src/views/AdminTrend.vue)
- ECharts 配色跟随新方案
- 新增外部团队趋势对比线

#### [MODIFY] [AdminUsers.vue](file:///f:/Ones-AI专项开发/ones-ai-platform/frontend/src/views/AdminUsers.vue)
- 表格行样式优化
- 添加搜索/筛选
- 活跃度小图标

#### [NEW] [AdminExternalTeams.vue](file:///f:/Ones-AI专项开发/ones-ai-platform/frontend/src/views/AdminExternalTeams.vue)
- 外部团队管理页面
- 团队列表 + 成员展开 + 使用统计
- 注册新团队弹窗

#### [MODIFY] [router/index.js](file:///f:/Ones-AI专项开发/ones-ai-platform/frontend/src/router/index.js)
- 新增 `/admin/external` 路由

#### [MODIFY] [api/index.js](file:///f:/Ones-AI专项开发/ones-ai-platform/frontend/src/api/index.js)
- 新增外部团队相关 API 方法

#### [MODIFY] [database.py](file:///f:/Ones-AI专项开发/ones-ai-platform/backend/database.py)
- 新增 3 张表的 DDL

---

## 验证计划

### 自动化
- 后端：curl 测试外部上报 API（正确 key / 错误 key / 批量上报）
- 前端：构建 `npm run build` 通过

### 手动
- 浏览器访问每个页面确认新配色和动效
- 外部团队管理页面的 CRUD 流程
- 管理统计页面同时展示内部+外部数据
