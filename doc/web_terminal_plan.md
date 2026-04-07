# Web Terminal — 浏览器容器交互 实现计划

## 架构

```
浏览器 xterm.js ←→ WebSocket ←→ FastAPI ←→ asyncssh PTY ←→ 目标服务器 Shell
```

> Web Terminal 连接的是**目标服务器 shell**，用户登录后可自行 `docker ps` + `docker exec` 进入容器。

## 文件清单

### 后端
- **[新建] terminal_ws.py** — WS 端点 → asyncssh PTY 双向代理
- **[修改] main.py** — 注册路由

### 前端
- **[新建] WebTerminal.vue** — xterm.js 5 + FitAddon
- **[修改] TaskDetailView.vue** — "进入服务器"按钮

## 防 Bug 要点

| 风险 | 措施 |
|------|------|
| SSH 泄漏 | WS disconnect 时 conn.close() + finally 兜底 |
| 编码 | WS binary 帧传输，不做 JSON |
| resize race | 前端 debounce 200ms |
| 多标签 | 每次新建独立 SSH，关闭即释放 |
