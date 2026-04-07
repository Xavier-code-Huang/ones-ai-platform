# ONES API 网关接口管理文档

> **v3 网关地址**: `http://172.60.1.103:10076`（业务数据接口）  
> **旧网关地址**: `http://172.60.1.103:9006`（旧 `/api-ones/proxy` 路径，**登录接口已不可用**）  
> **ONES 直连地址**: `http://10.10.10.113:30011`（登录认证专用）  
> **API 前缀**: `/api/ones/v3`  
> **连通性状态**: ✅ 2026-03-28 测试全部正常  
> **来源**: `F:\Agent仓库\dev-agent-teams\kb\api-center\api-ones\`  
> **在线文档**: http://172.60.1.103:10076/api/ones/v3/doc.html#/home

---

## 1. 接口清单（ones-AI 平台需要使用的）

| 序号 | 接口名称 | 方法 | 路径 | 用途 |
|------|----------|------|------|------|
| ①  | **Task 列表查询** | POST | `/api/ones/v3/ones/task/list` | 按工单号批量查询工单详情 |
| ②  | **Task 分页查询** | POST | `/api/ones/v3/ones/task/page` | 大量工单分页查询 |
| ③  | **Task 更新** | POST | `/api/ones/v3/ones/task/update` | AI 处理完毕后回写工单状态/结果 |
| ④  | **Task 发送消息** | POST | `/api/ones/v3/ones/task/message/send` | 在工单评论区发送 AI 分析报告 |

> **注意**: 该网关已封装了 ONES 原生 GraphQL/REST API 的鉴权，无需额外传 ONES Token。

---

## 2. 认证说明

该 API 网关内部已集成 ONES 系统认证（Token 自动刷新、Redis 缓存 7 天），调用方**无需传递 ONES 认证头**。

> [!IMPORTANT]
> **平台用户登录验证**必须直连 ONES，不走网关：  
> `POST http://10.10.10.113:30011/project/api/project/auth/login`  
> 两个网关（10076/9006）均**不提供**登录接口。

- ~~方案 B: 通过网关转发~~ — **已验证不可用**（10076 返回 404，9006 返回 500）
- ✅ **方案 A (当前使用)**: 直连 ONES 原生 API `POST http://10.10.10.113:30011/project/api/project/auth/login`

---

## 3. 接口详情

### 3.1 Task 列表查询

**路径**: `POST /api/ones/v3/ones/task/list`  
**最大返回**: 200 条  
**用途**: 根据工单号查询工单详细信息

**核心请求参数**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `number` | Integer | 工单编号（精确，单个） |
| `numbers` | List\<Integer\> | 工单编号列表（批量查询） |
| `name` | String | 任务名称（模糊匹配） |
| `status` | String | 状态名称 |
| `project` | String | 项目名称 |
| `assign` | String | 负责人名称 |
| `limit` | Integer | 返回数量限制（默认 50，最大 200） |
| `returnCustomFields` | List\<String\> | 需返回的自定义字段名称 |

**ones-AI 典型调用（按工单号批量查询）**:
```bash
curl -X POST 'http://172.60.1.103:10076/api/ones/v3/ones/task/list' \
  -H 'Content-Type: application/json' \
  -d '{ "numbers": [668380, 668381, 668382] }'
```

**返回核心字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `uuid` | String | 任务 UUID |
| `number` | Integer | 工单编号 |
| `name` | String | 工单标题 |
| `description` | String | 描述（纯文本） |
| `descriptionText` | String | 描述（HTML） |
| `status.name` | String | 状态名称 |
| `assign.name` | String | 负责人 |
| `project.name` | String | 项目名称 |
| `priority.value` | String | 优先级 |
| `createTime` | String | 创建时间 |
| `customFields` | Array | 自定义字段列表 |

---

### 3.2 Task 更新

**路径**: `POST /api/ones/v3/ones/task/update`  
**用途**: AI 处理完毕后更新工单状态、回写分析结果

**请求参数**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `uuid` | String | ✅ | 任务 UUID |
| `summary` | String | ❌ | 更新工单标题 |
| `desc` | String | ❌ | 更新描述（纯文本） |
| `descRich` | String | ❌ | 更新描述（HTML） |
| `assign` | String | ❌ | 更新负责人 UUID |
| `priority` | String | ❌ | 更新优先级 UUID |
| `fieldValues` | List | ❌ | 更新自定义字段 |

**ones-AI 典型调用（更新自定义字段）**:
```bash
curl -X POST 'http://172.60.1.103:10076/api/ones/v3/ones/task/update' \
  -H 'Content-Type: application/json' \
  -d '{
    "uuid": "DU6krHBNNKSnnHNI",
    "fieldValues": [
      { "fieldName": "AI处理结果", "type": 1, "value": "已完成" }
    ]
  }'
```

---

### 3.3 Task 发送消息

**路径**: `POST /api/ones/v3/ones/task/message/send`  
**用途**: 在工单评论区发送 AI 分析报告

**请求参数**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `taskUuid` | String | ✅ | 任务 UUID |
| `text` | String | ✅ | 消息内容（HTML） |

**ones-AI 典型调用（发送分析报告）**:
```bash
curl -X POST 'http://172.60.1.103:10076/api/ones/v3/ones/task/message/send' \
  -H 'Content-Type: application/json' \
  -d '{
    "taskUuid": "DU6krHBNNKSnnHNI",
    "text": "<h3>🤖 AI 分析报告</h3><p>已完成工单分析，修改了以下文件...</p>"
  }'
```

---

## 4. 连通性验证记录

| 时间 | 测试端点 | 结果 |
|------|----------|------|
| 2026-03-16 21:55 | GET `/` | ConnectionResetError |
| 2026-03-16 21:55 | GET `/health` | HTTP 502 Bad Gateway |
| 2026-03-16 21:55 | POST `/api/ones/v3/ones/task/list` | HTTP 502 Bad Gateway |
| **2026-03-28 10:26** | **POST `/api/ones/v3/ones/task/list` (10076)** | **✅ HTTP 200 OK，数据正常返回** |
| 2026-03-28 10:26 | POST `/api/ones/v3/ones/task/update` (10076) | ✅ HTTP 200 (可达) |
| 2026-03-28 10:26 | POST `/api/ones/v3/ones/task/message/send` (10076) | ✅ HTTP 200 (可达) |
| 2026-03-28 10:26 | POST 登录 `/api-ones/proxy/...` (9006) | ❌ HTTP 500 |
| 2026-03-28 10:26 | POST 登录 `/api-ones/proxy/...` (10076) | ❌ HTTP 404 |
| **2026-03-28 10:26** | **POST 直连 ONES 登录 (30011)** | **✅ HTTP 200 OK，鉴权正常** |

> ✅ **v3 业务接口(10076)已恢复正常**。登录认证必须走直连 ONES（30011）。

---

## 5. ONES 原生登录接口（**ones-AI 平台当前使用**）

> [!IMPORTANT]
> 这是 ones-AI 平台**唯一的登录认证方式**，直连 ONES 系统，不走 API 网关。

**地址**: `POST http://10.10.10.113:30011/project/api/project/auth/login`  
**代码位置**: `backend/ones_client.py` → `verify_ones_login()`  
**配置项**: `.env.prod` → `ONES_API_BASE_URL=http://10.10.10.113:30011`

**请求体**:
```json
{
  "email": "your_email@company.com",
  "password": "your_password"
}
```

**响应（成功）**:
```json
{
  "user": {
    "uuid": "87rvU9pH",
    "token": "xxxxxxxxxxxxxxxxxxxx",
    "name": "用户姓名"
  }
}
```

**响应（密码错误）**: `HTTP 401 {"errcode": "AuthFailure.InvalidPassword"}`  
**响应（账号不存在）**: `HTTP 404`

> ones-AI 平台登录流程：提交邮箱+密码 → 先查本地密码缓存 → 缓存未命中则调用此接口 → 成功则缓存密码 hash 到数据库。

---

## 6. 网关架构变更记录

| 时间 | 变更 |
|------|------|
| 2026-03-28 | 登录从旧网关 `/api-ones/proxy/...` (9006) 切换为直连 ONES (30011)，因旧网关登录接口返回 500 |