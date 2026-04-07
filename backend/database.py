# -*- coding: utf-8 -*-
"""
@Description: ones-AI 平台 — PostgreSQL 数据库初始化与连接管理
@Version: 1.0.0
@Date: 2026-03-17

关联设计文档: §3 数据库设计
关联需求: FR-001~FR-017 全部数据需求
"""

import asyncpg
import logging
from config import settings

logger = logging.getLogger("ones-ai.db")

# 全局连接池
_pool: asyncpg.Pool = None


async def get_pool() -> asyncpg.Pool:
    """获取数据库连接池"""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=settings.DATABASE_URL,
            min_size=settings.DB_POOL_MIN,
            max_size=settings.DB_POOL_MAX,
        )
    return _pool


async def close_pool():
    """关闭数据库连接池"""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def get_db() -> asyncpg.Connection:
    """获取一个数据库连接（从池中）"""
    pool = await get_pool()
    return await pool.acquire()


async def release_db(conn: asyncpg.Connection):
    """释放连接回池"""
    pool = await get_pool()
    await pool.release(conn)


# ============================================================
#  数据库初始化 — 建表 DDL
#  严格遵循 design.md §3.2
# ============================================================

INIT_SQL = """
-- ============================================================
--  users  用户表 [FR-001]
-- ============================================================
CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    ones_email      VARCHAR(255) UNIQUE NOT NULL,
    display_name    VARCHAR(255) DEFAULT '',
    role            VARCHAR(20) DEFAULT 'user',
    is_active       BOOLEAN DEFAULT TRUE,
    last_login_at   TIMESTAMP,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);
COMMENT ON TABLE users IS '平台用户表，通过 ONES 邮箱认证，不存储密码';

-- ============================================================
--  servers  服务器表 [FR-002]
-- ============================================================
CREATE TABLE IF NOT EXISTS servers (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(255) NOT NULL,
    host            VARCHAR(255) NOT NULL,
    ssh_port        INTEGER DEFAULT 22,
    description     TEXT DEFAULT '',
    status          VARCHAR(20) DEFAULT 'unknown',
    has_ones_ai     BOOLEAN DEFAULT TRUE,
    is_enabled      BOOLEAN DEFAULT TRUE,
    last_health_at  TIMESTAMP,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);
COMMENT ON TABLE servers IS '可用服务器列表，由管理员维护';

-- ============================================================
--  user_server_credentials  用户-服务器凭证表 [FR-003]
-- ============================================================
CREATE TABLE IF NOT EXISTS user_server_credentials (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    server_id       INTEGER NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
    ssh_username    VARCHAR(255) NOT NULL,
    ssh_password_encrypted TEXT NOT NULL,
    is_verified     BOOLEAN DEFAULT FALSE,
    verified_at     TIMESTAMP,
    alias           VARCHAR(255) DEFAULT '',
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_usc_user ON user_server_credentials(user_id);
CREATE INDEX IF NOT EXISTS idx_usc_server ON user_server_credentials(server_id);
COMMENT ON TABLE user_server_credentials IS '用户在每台服务器上的 SSH 凭证';

-- ============================================================
--  tasks  任务表 [FR-004, FR-005, FR-007]
-- ============================================================
CREATE TABLE IF NOT EXISTS tasks (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    server_id       INTEGER NOT NULL REFERENCES servers(id),
    credential_id   INTEGER REFERENCES user_server_credentials(id),
    status          VARCHAR(20) DEFAULT 'pending',
    ticket_count    INTEGER DEFAULT 0,
    success_count   INTEGER DEFAULT 0,
    failed_count    INTEGER DEFAULT 0,
    total_duration  REAL DEFAULT 0,
    agent_dir       TEXT DEFAULT '',
    task_mode       TEXT DEFAULT 'fix',
    submitted_at    TIMESTAMP DEFAULT NOW(),
    started_at      TIMESTAMP,
    completed_at    TIMESTAMP,
    notification_sent BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tasks_user ON tasks(user_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at);
COMMENT ON TABLE tasks IS '任务记录，一个任务可包含多个工单';

-- ============================================================
--  task_tickets  任务工单明细表 [FR-004, FR-007]
-- ============================================================
CREATE TABLE IF NOT EXISTS task_tickets (
    id              SERIAL PRIMARY KEY,
    task_id         INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    ticket_id       VARCHAR(50) NOT NULL,
    note            TEXT DEFAULT '',
    code_directory  TEXT DEFAULT '',
    container_name  VARCHAR(255) DEFAULT '',
    extra_mounts    TEXT DEFAULT '',
    compile_command TEXT DEFAULT '',
    run_tests       BOOLEAN DEFAULT FALSE,
    status          VARCHAR(20) DEFAULT 'pending',
    result_summary  TEXT DEFAULT '',
    result_report   TEXT DEFAULT '',
    error_message   TEXT DEFAULT '',
    ticket_title    TEXT DEFAULT '',
    result_conclusion TEXT DEFAULT '',
    report_path     TEXT DEFAULT '',
    result_analysis TEXT DEFAULT '',
    duration        REAL DEFAULT 0,
    started_at      TIMESTAMP,
    completed_at    TIMESTAMP,
    seq_order       INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_tt_task ON task_tickets(task_id);
CREATE INDEX IF NOT EXISTS idx_tt_ticket ON task_tickets(ticket_id);
COMMENT ON TABLE task_tickets IS '任务中每个工单的详细信息和执行结果';

-- ============================================================
--  task_evaluations  用户评价表 [FR-008]
-- ============================================================
CREATE TABLE IF NOT EXISTS task_evaluations (
    id              SERIAL PRIMARY KEY,
    task_ticket_id  INTEGER UNIQUE NOT NULL REFERENCES task_tickets(id) ON DELETE CASCADE,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    passed          BOOLEAN NOT NULL,
    reason          TEXT DEFAULT '',
    evaluated_at    TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_eval_user ON task_evaluations(user_id);
CREATE INDEX IF NOT EXISTS idx_eval_passed ON task_evaluations(passed);
COMMENT ON TABLE task_evaluations IS '用户对 AI 处理结果的评价记录';

-- ============================================================
--  task_logs  执行日志表 [FR-006]
-- ============================================================
CREATE TABLE IF NOT EXISTS task_logs (
    id              SERIAL PRIMARY KEY,
    task_id         INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    task_ticket_id  INTEGER REFERENCES task_tickets(id),
    log_type        VARCHAR(20) DEFAULT 'stdout',
    content         TEXT NOT NULL,
    timestamp       TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_logs_task ON task_logs(task_id);
CREATE INDEX IF NOT EXISTS idx_logs_time ON task_logs(timestamp);
COMMENT ON TABLE task_logs IS '任务执行过程的输出日志';

-- ============================================================
--  notification_logs  通知记录表 [FR-009]
-- ============================================================
CREATE TABLE IF NOT EXISTS notification_logs (
    id              SERIAL PRIMARY KEY,
    task_id         INTEGER NOT NULL REFERENCES tasks(id),
    user_id         INTEGER NOT NULL REFERENCES users(id),
    channel         VARCHAR(50) DEFAULT 'wecom',
    status          VARCHAR(20) DEFAULT 'pending',
    content         TEXT DEFAULT '',
    error_message   TEXT DEFAULT '',
    sent_at         TIMESTAMP,
    created_at      TIMESTAMP DEFAULT NOW()
);
COMMENT ON TABLE notification_logs IS '企微消息通知的发送记录';

-- ============================================================
--  external_configs  外部服务配置表 [FR-014]
-- ============================================================
CREATE TABLE IF NOT EXISTS external_configs (
    id              SERIAL PRIMARY KEY,
    config_key      VARCHAR(100) UNIQUE NOT NULL,
    config_value    TEXT DEFAULT '',
    is_encrypted    BOOLEAN DEFAULT FALSE,
    description     TEXT DEFAULT '',
    updated_by      INTEGER REFERENCES users(id),
    updated_at      TIMESTAMP DEFAULT NOW()
);
COMMENT ON TABLE external_configs IS '外部服务配置（ONES/Gerrit/企微等）';

-- ============================================================
--  创建默认管理员
-- ============================================================
INSERT INTO users (ones_email, display_name, role)
VALUES ('admin@ones-ai.local', '管理员', 'admin')
ON CONFLICT (ones_email) DO NOTHING;

-- ============================================================
--  user_agent_dirs  用户 Agent 目录记忆表
-- ============================================================
CREATE TABLE IF NOT EXISTS user_agent_dirs (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    server_id       INTEGER NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
    credential_id   INTEGER NOT NULL REFERENCES user_server_credentials(id) ON DELETE CASCADE,
    agent_dir       TEXT NOT NULL,
    updated_at      TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, server_id, credential_id)
);
COMMENT ON TABLE user_agent_dirs IS '用户在每台服务器每组凭证上的 Agent Teams 目录记忆';

-- ============================================================
--  external_teams  外部团队注册表
-- ============================================================
CREATE TABLE IF NOT EXISTS external_teams (
    id              SERIAL PRIMARY KEY,
    team_name       VARCHAR(100) UNIQUE NOT NULL,
    api_key         VARCHAR(64) UNIQUE NOT NULL,
    description     TEXT DEFAULT '',
    contact_email   VARCHAR(200) DEFAULT '',
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
COMMENT ON TABLE external_teams IS '外部团队注册表，每个团队一个API Key';

-- ============================================================
--  external_team_members  外部团队成员表
-- ============================================================
CREATE TABLE IF NOT EXISTS external_team_members (
    id              SERIAL PRIMARY KEY,
    team_id         INTEGER NOT NULL REFERENCES external_teams(id) ON DELETE CASCADE,
    member_name     VARCHAR(100) NOT NULL,
    member_email    VARCHAR(200) DEFAULT '',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(team_id, member_name)
);
COMMENT ON TABLE external_team_members IS '外部团队成员表';

-- ============================================================
--  external_logs  外部日志上报表
-- ============================================================
CREATE TABLE IF NOT EXISTS external_logs (
    id              SERIAL PRIMARY KEY,
    team_id         INTEGER NOT NULL REFERENCES external_teams(id) ON DELETE CASCADE,
    member_name     VARCHAR(100) NOT NULL,
    ticket_id       VARCHAR(50) DEFAULT '',
    action_type     VARCHAR(50) DEFAULT 'process',
    status          VARCHAR(20) DEFAULT 'completed',
    duration        FLOAT DEFAULT 0,
    summary         TEXT DEFAULT '',
    extra_data      JSONB DEFAULT '{}',
    reported_at     TIMESTAMPTZ DEFAULT NOW()
);
COMMENT ON TABLE external_logs IS '外部团队日志上报记录';
CREATE INDEX IF NOT EXISTS idx_external_logs_team_id ON external_logs(team_id);
CREATE INDEX IF NOT EXISTS idx_external_logs_reported_at ON external_logs(reported_at);

-- ============================================================
--  task_ticket_phases  工单处理阶段表 [FR-101, FR-103]
-- ============================================================
CREATE TABLE IF NOT EXISTS task_ticket_phases (
    id              SERIAL PRIMARY KEY,
    task_ticket_id  INTEGER NOT NULL REFERENCES task_tickets(id) ON DELETE CASCADE,
    phase_name      VARCHAR(50) NOT NULL,
    phase_label     VARCHAR(100) NOT NULL,
    phase_order     INTEGER NOT NULL DEFAULT 0,
    status          VARCHAR(20) NOT NULL DEFAULT 'pending',
    message         TEXT DEFAULT '',
    started_at      TIMESTAMP WITH TIME ZONE,
    completed_at    TIMESTAMP WITH TIME ZONE,
    duration_ms     INTEGER,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ttp_ticket ON task_ticket_phases(task_ticket_id);
COMMENT ON TABLE task_ticket_phases IS '工单处理阶段记录，用于前端时间线展示';

-- ============================================================
--  user_code_paths  用户代码目录历史记忆表 [FR-107]
-- ============================================================
CREATE TABLE IF NOT EXISTS user_code_paths (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    server_id       INTEGER NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
    path            VARCHAR(500) NOT NULL,
    use_count       INTEGER DEFAULT 1,
    last_used_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, server_id, path)
);
COMMENT ON TABLE user_code_paths IS '用户在每台服务器上使用过的代码目录历史';

-- ============================================================
--  accuracy_evaluations  准确度评测结果表 [FR-200]
-- ============================================================
CREATE TABLE IF NOT EXISTS accuracy_evaluations (
    id              SERIAL PRIMARY KEY,
    task_ticket_id  INTEGER UNIQUE NOT NULL REFERENCES task_tickets(id) ON DELETE CASCADE,
    ticket_id       VARCHAR(50) NOT NULL,
    gerrit_change_id    VARCHAR(100) DEFAULT '',
    gerrit_change_url   TEXT DEFAULT '',
    gerrit_files        JSONB DEFAULT '[]',
    gerrit_diff_summary TEXT DEFAULT '',
    gerrit_commit_msg   TEXT DEFAULT '',
    score_file_match    INTEGER DEFAULT 0,
    score_root_cause    INTEGER DEFAULT 0,
    score_fix_similar   INTEGER DEFAULT 0,
    score_actionable    INTEGER DEFAULT 0,
    score_consistency   INTEGER DEFAULT 0,
    total_score         INTEGER DEFAULT 0,
    is_effective        BOOLEAN DEFAULT FALSE,
    llm_reasoning       TEXT DEFAULT '',
    skip_reason         TEXT DEFAULT '',
    eval_version        VARCHAR(20) DEFAULT 'v1',
    evaluated_at        TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ae_ticket ON accuracy_evaluations(ticket_id);
CREATE INDEX IF NOT EXISTS idx_ae_effective ON accuracy_evaluations(is_effective);
COMMENT ON TABLE accuracy_evaluations IS '准确度评测结果：五维度评分 + Gerrit 关联数据';
"""


# 数据库迁移：为已有表新增列（兼容旧版本）
MIGRATION_SQL = """
ALTER TABLE task_tickets ADD COLUMN IF NOT EXISTS ticket_title TEXT DEFAULT '';
ALTER TABLE task_tickets ADD COLUMN IF NOT EXISTS result_conclusion TEXT DEFAULT '';
ALTER TABLE task_tickets ADD COLUMN IF NOT EXISTS report_path TEXT DEFAULT '';
ALTER TABLE task_tickets ADD COLUMN IF NOT EXISTS result_analysis TEXT DEFAULT '';
ALTER TABLE task_tickets ADD COLUMN IF NOT EXISTS container_name VARCHAR(255) DEFAULT '';
ALTER TABLE task_tickets ADD COLUMN IF NOT EXISTS conversation_id VARCHAR(255) DEFAULT '';
ALTER TABLE servers ADD COLUMN IF NOT EXISTS is_enabled BOOLEAN DEFAULT TRUE;
ALTER TABLE task_logs ADD COLUMN IF NOT EXISTS phase_name VARCHAR(50) DEFAULT '';
"""


async def init_db():
    """初始化数据库表结构"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(INIT_SQL)
        # 执行迁移（新增列，兼容已有表）
        await conn.execute(MIGRATION_SQL)
    logger.info("数据库初始化完成（15 张表 + 迁移）")
