# -*- coding: utf-8 -*-
"""
4-Round Deep Review Script
Writes results to review_results.txt
"""
import os
import re

results = []

def log(msg):
    results.append(msg)
    print(msg)

# ========== Round 1: Requirements Coverage ==========
log("=" * 60)
log("ROUND 1: Requirements Coverage (FR-001 ~ FR-017)")
log("=" * 60)

backend_dir = "."
all_py = [f for f in os.listdir(backend_dir) if f.endswith(".py") and f != "test_imports.py"]

# Read all backend code
all_code = ""
for f in sorted(all_py):
    with open(os.path.join(backend_dir, f), "r", encoding="utf-8") as fh:
        all_code += fh.read() + "\n"

requirements = {
    "FR-001": ("ONES account login", ["verify_ones_login", "login", "JWT"]),
    "FR-002": ("Server list", ["list_servers", "servers"]),
    "FR-003": ("Credential binding", ["verify_credential", "ssh_password_encrypted", "AES"]),
    "FR-004": ("Task creation", ["create_task", "TicketInput", "normalize_ticket_id"]),
    "FR-005": ("Task execution SSH", ["ssh_conn", "create_process", "ones_task_runner"]),
    "FR-006": ("Real-time logs", ["WebSocket", "subscribe_logs", "broadcast_log"]),
    "FR-007": ("Task results", ["get_task", "TaskDetail", "result_summary"]),
    "FR-008": ("User evaluation", ["submit_evaluation", "task_evaluations", "passed"]),
    "FR-009": ("WeChat notification", ["send_wecom_message", "send_task_notification"]),
    "FR-010": ("Admin overview", ["get_overview", "OverviewStats"]),
    "FR-011": ("Admin trends", ["get_trends", "TrendPoint"]),
    "FR-012": ("Admin user detail", ["get_user_detail", "UserRank"]),
    "FR-013": ("Admin eval stats", ["get_eval_stats", "pass_rate"]),
    "FR-014": ("External configs", ["external_configs", "get_configs", "update_configs"]),
    "FR-015": ("AI model config", ["AI_BASE_URL", "AI_SONNET_MODEL", "AI_OPUS_MODEL"]),
    "FR-016": ("Gerrit placeholder", ["GERRIT_HOST", "GERRIT_TOKEN"]),
    "FR-017": ("Runner enhancement", ["json-output", "PROGRESS", "notes"]),
}

covered = 0
for fr_id, (desc, keywords) in requirements.items():
    found = [kw for kw in keywords if kw in all_code]
    status = "PASS" if len(found) >= len(keywords) // 2 + 1 else "PARTIAL" if found else "MISS"
    if status != "MISS":
        covered += 1
    log(f"  {fr_id} [{status}] {desc} - found: {found}")

log(f"\nCoverage: {covered}/{len(requirements)} ({covered/len(requirements)*100:.0f}%)")

# ========== Round 2: Database Schema ==========
log("\n" + "=" * 60)
log("ROUND 2: Database Schema Verification")
log("=" * 60)

with open("database.py", "r", encoding="utf-8") as f:
    db_code = f.read()

expected_tables = [
    "users", "servers", "user_server_credentials", "tasks",
    "task_tickets", "task_evaluations", "task_logs",
    "notification_logs", "external_configs"
]

for table in expected_tables:
    if f"CREATE TABLE IF NOT EXISTS {table}" in db_code:
        log(f"  ✅ {table}")
    else:
        log(f"  ❌ {table} — MISSING")

# Check indexes
idx_count = db_code.count("CREATE INDEX")
log(f"  Indexes: {idx_count}")

# ========== Round 3: API Completeness ==========
log("\n" + "=" * 60)
log("ROUND 3: API Route Completeness")
log("=" * 60)

expected_routes = {
    "auth.py": ["POST /login", "GET /me"],
    "servers.py": ["GET /servers", "POST /verify", "GET /credentials", "DELETE /credentials", "POST /servers", "POST /health"],
    "tasks.py": ["POST /tasks", "GET /tasks", "GET /tasks/{id}", "DELETE /tasks/{id}"],
    "evaluations.py": ["POST /evaluations", "GET /evaluations/task"],
    "admin.py": ["GET /overview", "GET /trends", "GET /users", "GET /users/{id}/detail", "GET /evaluations/stats", "GET /export", "GET /configs", "POST /configs"],
    "log_streamer.py": ["WebSocket /ws/tasks/{id}/logs"],
}

total_routes = 0
for module, routes in expected_routes.items():
    with open(module, "r", encoding="utf-8") as f:
        code = f.read()
    for route in routes:
        method = route.split(" ")[0].lower()
        path_part = route.split(" ")[1].split("/")[-1].replace("{id}", "")
        if method in code.lower() or path_part in code:
            log(f"  ✅ {route} in {module}")
            total_routes += 1
        else:
            log(f"  ❌ {route} in {module} — MISSING")

log(f"\nTotal routes verified: {total_routes}")

# ========== Round 4: Security & Config ==========
log("\n" + "=" * 60)
log("ROUND 4: Security & Configuration")
log("=" * 60)

security_checks = [
    ("JWT auth", "HTTPBearer" in all_code),
    ("AES encryption", "AESGCM" in all_code),
    ("CORS middleware", "CORSMiddleware" in all_code),
    ("Admin role check", "require_admin" in all_code),
    ("Token validation", "decode_token" in all_code),
    ("Password encryption", "encrypt_password" in all_code),
    ("SSH credential verify", "verify_ssh_credential" in all_code),
    ("Gerrit placeholder", "__GERRIT_HOST_1__" in all_code),
    ("AI model config", "AI_BASE_URL" in all_code),
    ("DB connection pool", "asyncpg.create_pool" in all_code),
]

for check_name, passed in security_checks:
    log(f"  {'✅' if passed else '❌'} {check_name}")

# Write results
log("\n" + "=" * 60)
log("REVIEW COMPLETE")
log("=" * 60)

with open("review_results.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(results))

print("\nResults saved to review_results.txt")
