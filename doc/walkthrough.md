# ones-AI 平台开发 Walkthrough

更新时间: 2026-03-17 21:07

## 本次会话完成的工作

### 1. 通知系统实现
- 实现双通道通知：Webhook（企微）+ Email（SMTP）
- 独立开关 `NOTIFY_WEBHOOK_ENABLED` / `NOTIFY_EMAIL_ENABLED`
- 管理界面 UI 配置
- 已部署到 172.60.1.35:9625/9626

### 2. Runner 执行方式改造

**问题链**（逐步排查修复）：

| 问题 | 根因 | 修复 |
|------|------|------|
| 任务 #1 失败 | `ssh_pool.py` 中 `is_closed()` asyncssh 版本不兼容 | 新增 `_is_alive()` 兼容函数 |
| 任务 #2 秒退 exit 1 | SSH 命令未 cd 到 runner 目录，找不到 `config.yaml` | 改用 `--config` 绝对路径 |
| 看不到报错 | `task_executor.py` stderr 协程未 await | 加 `await` |
| 任务 #3 秒退 exit 1 | **宿主机 Python 3.6** 不支持 `shlex.join`（3.8+ API） | 改用 `ones-AI` 脚本走 Docker |
| 任务 #4 秒退 | `ones-AI` 写死路径 `/opt/lango/...`，实际在 PATH 中 | 改用 `ones-AI`（不带路径） |
| 任务 #5 卡 24 分钟 | 中文 notes 通过 `printf '%q'` 被乱码化，Claude 收到乱码 prompt | SSH 命令前 `export LANG=C.UTF-8` |

### 3. 数据库修复
- 通知模块 `notifications.py` 查询列名 `summary` → `result_summary as summary`
- 手动修复任务 #5 状态 running → failed

### 4. 关键发现
- 38 服务器 Python 版本为 **3.6.9**，不能直接运行 runner
- `ones-AI` 脚本通过 Docker 容器执行，容器内 Python 版本正确
- `ones-AI` 已安装在 PATH 中（非 `/opt/lango/ones_task_runner/`）
- 从 Windows 无法直接 SSH 到 38，需通过 35 跳板
- WSL `/tmp` 会因崩溃丢失，部署镜像需保存到 Windows 路径

## 下一步工作

1. **验证中文编码修复**（UTF-8 locale）
2. **Runner 产出展示增强**（参考 `doc/runner产出展示增强方案.md`）
3. **邮件通知整合**（参考 `doc/流水线` Jenkins 邮件逻辑）
4. **任务超时处理**（SSH stdout 读取超时机制）
