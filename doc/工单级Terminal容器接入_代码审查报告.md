# 工单级 Terminal 容器接入 — 深度代码审查报告

> 审查时间: 2026-03-28 09:15  
> 审查范围: 7 个被修改文件  
> 审查结论: **发现 3 个必须修复的阻断级问题 + 4 个重要风险 + 3 个建议**

---

## 🚨 必须修复的阻断级问题 (BLOCKER)

### B1. `TaskDetailView.vue` 缺少 `watch` 导入 — **会导致页面崩溃白屏**

> [!CAUTION]
> **这是最严重的问题。** 第 277 行 import 缺少 `watch`，但第 378 行使用了 `watch(selectedTicketId, ...)`。部署后**一旦用户进入任务详情页就会白屏报错**。

```diff
- import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
+ import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
```

**文件**: [TaskDetailView.vue](file:///f:/Ones-AI专项开发/ones-ai-platform/frontend/src/views/TaskDetailView.vue#L277)  
**影响**: 🔴 生产页面直接崩溃

---

### B2. 数据库 Schema 变更没有在线迁移 — **首次启动后端必 crash**

> [!CAUTION]
> `database.py` 的 `CREATE TABLE IF NOT EXISTS` 中添加了 `container_name` 列，但这个 DDL **仅在表不存在时执行**。生产环境 `task_tickets` 表已存在，因此新列不会被添加。后续 `task_executor.py` 执行 `UPDATE task_tickets SET container_name=$1` 时会报列不存在的 SQL 错误导致工单执行失败。

**修复方案**: 需要在 `init_db()` 中增加 `ALTER TABLE` 迁移语句：
```sql
ALTER TABLE task_tickets ADD COLUMN IF NOT EXISTS container_name VARCHAR(255) DEFAULT '';
```

**文件**: [database.py](file:///f:/Ones-AI专项开发/ones-ai-platform/backend/database.py#L146)  
**影响**: 🔴 所有工单执行中断

---

### B3. `container_name` 用户可控，直接拼入 shell 命令 — **命令注入漏洞**

> [!WARNING]
> `container_name` 来自 `ones-AI` 脚本的 stdout 用正则解析，正则 `r'(ones-ai-[\w-]+)'` 限制了字符集（字母/数字/下划线/连字符），风险较低。但在 `tasks.py` 的 `start_ticket_container` 中直接拼进了 `f"docker start {container_name}"`，以及 `terminal_ws.py` 中拼进了 `f"docker attach --sig-proxy=false {container_name}"`。

虽然正则的 `\w` 和 `-` 限制了大部分注入，但最安全的做法是在使用前做一次**显式校验**：
```python
import re
if not re.fullmatch(r'ones-ai-[\w-]+', container_name):
    raise HTTPException(400, "非法容器名")
```

**影响**: 🟡 低概率但高危

---

## ⚠️ 重要风险 (WARNING)

### W1. `docker attach` 无法交互式干预 — **功能设计理解偏差**

`docker attach` 会附加到容器的**主进程 (PID 1)** 的 stdin/stdout。对于 ones-AI 容器：
- 主进程是 `claude` CLI 或 `ones_task_runner`，它们在全自动运行
- attach 后用户看到的是主进程的输出流，**无法输入交互命令**（包括 `/resume`）
- `/resume` 命令只在 claude CLI 交互 prompt 下才有意义

**实际效果**: 用户能**看到**实时输出（观测功能 OK），但**无法交互干预**。如果需要干预，应该用 `docker exec -it {container_name} /bin/bash` 而非 `docker attach`。

> [!IMPORTANT]
> 建议明确定位：目前版本仅支持**观测**，干预功能后续迭代。或者改回 `docker exec` 方案。

---

### W2. `auto_resume` 发送 `/resume\n` 到 attach 流 — **可能产生乱码或无效**

第 124-125 行：
```python
if auto_resume:
    ssh_process.stdin.write(b"/resume\n")
```

由于 `docker attach` 连接的是容器主进程的标准输入，如果主进程不在等待 stdin 输入，这串字节会被忽略或产生不可预期效果。配合 W1，这个功能基本无效。

**建议**: 注释掉 `auto_resume` 的实际写入逻辑，仅保留 UI 提示。

---

### W3. `get_ssh_connection` 函数签名可能不匹配

`tasks.py` 第 682-684 行：
```python
ssh_conn = await get_ssh_connection(
    record["host"], record["ssh_port"],
    record["ssh_username"], ssh_password
)
```

需要确认 `ssh_pool.py` 中 `get_ssh_connection` 的参数签名是否是 `(host, port, username, password)`。如果签名不匹配会导致 API 调用失败。

---

### W4. Nginx WebSocket 超时配置缺失

当前 nginx.conf 的 `/ws/` 代理没有设置超时时间：
```nginx
location /ws/ {
    proxy_pass http://127.0.0.1:9625;
    # 缺少以下配置
    # proxy_read_timeout 3600s;
    # proxy_send_timeout 3600s;
}
```
默认 60 秒超时，终端空闲超过 1 分钟就会被 Nginx 强制断开。

---

## 💡 建议 (SUGGESTION)

### S1. `terminal_ws.py` 中 `record.get("container_name")` 应改为 `record["container_name"]`

`asyncpg.Record` 支持字典式 `[]` 访问但可能不支持 `.get()` 方法。建议统一用 `record["container_name"]` 并在访问前做 `if record["container_name"]` 判断。

### S2. WebTerminal.vue 中 ResizeObserver 未在 unmount 时 disconnect

第 90-105 行创建了 `new ResizeObserver(...)` 但未保存引用，在 `onBeforeUnmount` 中没有 `observer.disconnect()`，可能导致内存泄漏。

### S3. 前端切换工单时应 `term.dispose()` 后重建

当前切换工单时只做 `term.clear()` + 重连，但旧的 Terminal 实例仍然存在。如果频繁切换工单，xterm.js 实例不会被释放。

---

## ✅ 审查通过的部分

| 文件 | 结论 |
|------|------|
| `api/index.js` | ✅ 新增 2 个 API 封装，路径正确 |
| `database.py` DDL 定义 | ✅ 新列位置合理 (需配合迁移) |
| `task_executor.py` 容器名捕获 | ✅ 正则合理，DB 写入逻辑正确 |
| `terminal_ws.py` SSH/WS 桥接 | ✅ 双向代理结构合理，清理逻辑完善 |
| `WebTerminal.vue` 组件 | ✅ 生命周期管理得当，事件机制合理 |
| Nginx `/ws/` 路由 | ✅ 新路径 `/ws/tickets/...` 已被 `/ws/` 前缀匹配覆盖 |

---

## 🔧 修复优先级

| 优先级 | 编号 | 问题 | 修复难度 |
|--------|------|------|----------|
| P0 | B1 | `watch` 未导入 → 白屏 | 1 行 |
| P0 | B2 | DB 迁移缺失 → 工单失败 | 3 行 |
| P1 | B3 | 容器名校验 | 5 行 |
| P1 | W4 | Nginx WS 超时 | 2 行 |
| P2 | W1/W2 | attach vs exec 语义 | 设计决策 |
| P3 | S1-S3 | 代码健壮性 | 可后续迭代 |

> [!IMPORTANT]
> **结论：B1 和 B2 是必须修复后才能部署的，否则会导致生产页面崩溃和工单执行中断。** 建议修复后重新 build 再部署。
