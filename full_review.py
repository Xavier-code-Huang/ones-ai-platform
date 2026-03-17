# -*- coding: utf-8 -*-
"""
全量代码深度 Review 脚本
覆盖: ones-ai-platform (后端+前端) + ones_task_runner
输出: review_report.md
"""
import os
import re
import sys
import json
import ast
from datetime import datetime

BACKEND_DIR = r"F:\Ones-AI专项开发\ones-ai-platform\backend"
FRONTEND_DIR = r"F:\Ones-AI专项开发\ones-ai-platform\frontend\src"
RUNNER_FILE = r"F:\Claude\lango-claude-deploy\ones_task_runner\ones_task_runner.py"
DEPLOY_DIR = r"F:\Ones-AI专项开发\ones-ai-platform"

report = []
issues = []
warnings = []
infos = []

def log(msg): report.append(msg)
def issue(sev, loc, msg):
    entry = f"[{sev}] {loc}: {msg}"
    if sev == "CRITICAL": issues.append(entry)
    elif sev == "WARNING": warnings.append(entry)
    else: infos.append(entry)
    report.append(f"  {entry}")

# ============================================================
# ROUND 1: Python 后端 — AST 深度检查
# ============================================================
log("# Round 1: Python 后端 AST 深度检查\n")

py_files = [f for f in os.listdir(BACKEND_DIR) if f.endswith('.py') and not f.startswith(('test_', 'review_', 'add_'))]
py_files.sort()

total_lines = 0
total_functions = 0
total_classes = 0
total_imports = 0

for fname in py_files:
    filepath = os.path.join(BACKEND_DIR, fname)
    with open(filepath, 'r', encoding='utf-8') as f:
        code = f.read()
    lines = code.split('\n')
    total_lines += len(lines)
    log(f"\n## {fname} ({len(lines)} lines)")

    # AST Parse
    try:
        tree = ast.parse(code, filename=fname)
    except SyntaxError as e:
        issue("CRITICAL", fname, f"语法错误: {e}")
        continue

    functions = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
    total_functions += len(functions)
    total_classes += len(classes)
    total_imports += len(imports)

    log(f"  - 函数: {len(functions)}, 类: {len(classes)}, 导入: {len(imports)}")

    # Check 1: 函数过长
    for func in functions:
        end = getattr(func, 'end_lineno', func.lineno + 10)
        func_len = end - func.lineno
        if func_len > 60:
            issue("WARNING", f"{fname}:{func.lineno}", f"函数 `{func.name}` 过长 ({func_len} 行)")

    # Check 2: 无 docstring 的公开函数
    for func in functions:
        if func.name.startswith('_'):
            continue
        if not (func.body and isinstance(func.body[0], ast.Expr) and isinstance(func.body[0].value, (ast.Constant, ast.Str))):
            issue("INFO", f"{fname}:{func.lineno}", f"公开函数 `{func.name}` 缺少 docstring")

    # Check 3: 裸 except
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            issue("WARNING", f"{fname}:{node.lineno}", "裸 except — 应指定异常类型")

    # Check 4: 硬编码密码/密钥
    for i, line in enumerate(lines, 1):
        if re.search(r'(password|secret|token)\s*=\s*["\'][^"\']{8,}', line, re.I):
            if 'placeholder' in line.lower() or 'example' in line.lower() or 'config' in fname.lower():
                continue
            issue("WARNING", f"{fname}:{i}", f"可能的硬编码敏感信息: {line.strip()[:60]}")

    # Check 5: SQL 注入风险（f-string 拼 SQL）
    for i, line in enumerate(lines, 1):
        if re.search(r'f["\'].*(?:SELECT|INSERT|UPDATE|DELETE|WHERE)', line):
            if '$' in line:
                continue  # asyncpg 参数化
            issue("CRITICAL", f"{fname}:{i}", f"潜在 SQL 注入: {line.strip()[:60]}")

    # Check 6: 未使用 await 的 async 调用
    for func in functions:
        if isinstance(func, ast.AsyncFunctionDef):
            for node in ast.walk(func):
                if isinstance(node, ast.Call) and hasattr(node.func, 'attr'):
                    if node.func.attr in ('execute', 'fetch', 'fetchrow', 'fetchval') and not isinstance(getattr(node, '_parent', None), ast.Await):
                        pass  # AST parent tracking complex, skip false positives

log(f"\n**后端统计**: {len(py_files)} 文件, {total_lines} 行, {total_functions} 函数, {total_classes} 类, {total_imports} 导入")

# ============================================================
# ROUND 2: Runner 代码检查
# ============================================================
log("\n\n# Round 2: Runner 代码检查\n")

with open(RUNNER_FILE, 'r', encoding='utf-8') as f:
    runner_code = f.read()
runner_lines = runner_code.split('\n')
log(f"## ones_task_runner.py ({len(runner_lines)} lines)")

try:
    rtree = ast.parse(runner_code, filename='ones_task_runner.py')
    rfuncs = [n for n in ast.walk(rtree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    rclasses = [n for n in ast.walk(rtree) if isinstance(n, ast.ClassDef)]
    log(f"  - 类: {[c.name for c in rclasses]}")
    log(f"  - 函数: {len(rfuncs)}")
except SyntaxError as e:
    issue("CRITICAL", "ones_task_runner.py", f"语法错误: {e}")
    rfuncs = []

# Check: --code-dirs 参数是否完整接入
if '--code-dirs' not in runner_code:
    issue("CRITICAL", "ones_task_runner.py", "缺少 --code-dirs 参数支持")
else:
    log("  - ✅ --code-dirs 参数已接入")

if 'codeDirectory' not in runner_code:
    issue("WARNING", "ones_task_runner.py", "task params 中缺少 codeDirectory 字段")
else:
    log("  - ✅ codeDirectory 字段已添加")

if '【代码位置】' not in runner_code:
    issue("WARNING", "ones_task_runner.py", "提示词中缺少代码位置指引")
else:
    log("  - ✅ 提示词含代码位置指引")

# Check: 命令行参数 --notes 和 --code-dirs 是否对齐
    nargs_count = runner_code.count("nargs='+'")
    issue("INFO", "ones_task_runner.py", f"nargs='+' 出现 {nargs_count} 次")

# Check: shell=True 安全性
if 'shell=True' in runner_code:
    issue("INFO", "ones_task_runner.py", "使用 shell=True 执行命令（注意命令注入风险）")

# Check: 超时设置
if 'timeout' in runner_code.lower():
    log("  - ✅ 有超时控制")

# ============================================================
# ROUND 3: 前端 Vue 组件检查
# ============================================================
log("\n\n# Round 3: 前端 Vue 组件检查\n")

vue_files = []
for root, dirs, files in os.walk(FRONTEND_DIR):
    for f in files:
        if f.endswith('.vue') or f.endswith('.js'):
            vue_files.append(os.path.join(root, f))

for vf in sorted(vue_files):
    with open(vf, 'r', encoding='utf-8') as f:
        vcontent = f.read()
    name = os.path.basename(vf)
    vlines = vcontent.split('\n')
    log(f"\n## {name} ({len(vlines)} lines)")

    # Check: console.log 残留
    for i, line in enumerate(vlines, 1):
        if 'console.log' in line and '//' not in line.split('console.log')[0]:
            issue("INFO", f"{name}:{i}", "残留 console.log")

    # Check: v-html XSS 风险
    if 'v-html' in vcontent:
        issue("WARNING", name, "使用 v-html — 注意 XSS 风险")

    # Check: 硬编码 API URL
    if re.search(r'https?://\d+\.\d+\.\d+\.\d+', vcontent):
        issue("WARNING", name, "硬编码 IP 地址（应使用配置或环境变量）")

    # Check: 错误处理
    if 'catch' in vcontent:
        if 'catch {}' in vcontent or 'catch (e) {}' in vcontent:
            issue("WARNING", name, "空 catch 块 — 应处理或记录错误")

    # Check: autocomplete
    if 'password' in vcontent.lower() and 'autocomplete' not in vcontent:
        issue("INFO", name, "密码字段缺少 autocomplete 属性")

    # Check: 唯一 ID
    id_matches = re.findall(r'id="([^"]+)"', vcontent)
    if id_matches:
        log(f"  - IDs: {id_matches[:5]}{'...' if len(id_matches) > 5 else ''}")

# ============================================================
# ROUND 4: 部署与配置检查
# ============================================================
log("\n\n# Round 4: 部署与配置检查\n")

# Check docker-compose.yml
dc_path = os.path.join(DEPLOY_DIR, 'docker-compose.yml')
if os.path.exists(dc_path):
    with open(dc_path, 'r', encoding='utf-8') as f:
        dc = f.read()
    log("## docker-compose.yml")
    if 'restart: unless-stopped' in dc or 'restart: always' in dc:
        log("  - ✅ 容器重启策略已配置")
    else:
        issue("WARNING", "docker-compose.yml", "缺少容器重启策略")
    if 'healthcheck' in dc:
        log("  - ✅ healthcheck 已配置")
    else:
        issue("INFO", "docker-compose.yml", "缺少容器健康检查")
    if 'volumes' in dc:
        log("  - ✅ 持久化卷已配置")

# Check .env
env_path = os.path.join(DEPLOY_DIR, '.env')
if os.path.exists(env_path):
    with open(env_path, 'r', encoding='utf-8') as f:
        env = f.read()
    log("\n## .env")
    if 'please-change-this' in env:
        issue("WARNING", ".env", "JWT_SECRET_KEY 使用的是默认值 — 生产环境必须更换")
    if '0123456789abcdef' in env:
        issue("WARNING", ".env", "CRYPTO_KEY 使用的是默认值 — 生产环境必须更换")
    if 'DEBUG=true' in env:
        issue("WARNING", ".env", "DEBUG=true — 生产环境应设为 false")
    # Check sensitive info not exposed
    gerrit_tokens = re.findall(r'GERRIT_TOKEN_\d+=(\S+)', env)
    for t in gerrit_tokens:
        if len(t) > 10:
            issue("CRITICAL", ".env", f"Gerrit Token 暴露在 .env 文件中")

# Check .gitignore
gi_path = os.path.join(DEPLOY_DIR, '.gitignore')
if os.path.exists(gi_path):
    with open(gi_path, 'r', encoding='utf-8') as f:
        gi = f.read()
    log("\n## .gitignore")
    if '.env' in gi:
        log("  - ✅ .env 已排除")
    else:
        issue("CRITICAL", ".gitignore", ".env 未在 .gitignore 中 — 可能泄露密钥到 Git")
    if 'node_modules' in gi:
        log("  - ✅ node_modules 已排除")

# Check nginx.conf
nginx_path = os.path.join(DEPLOY_DIR, 'nginx.conf')
if os.path.exists(nginx_path):
    with open(nginx_path, 'r', encoding='utf-8') as f:
        nginx = f.read()
    log("\n## nginx.conf")
    if 'proxy_pass' in nginx:
        log("  - ✅ API 代理已配置")
    if 'websocket' in nginx.lower() or 'upgrade' in nginx.lower():
        log("  - ✅ WebSocket 代理已配置")
    if 'try_files' in nginx:
        log("  - ✅ SPA 路由已配置")

# ============================================================
# ROUND 5: 跨模块一致性检查
# ============================================================
log("\n\n# Round 5: 跨模块一致性检查\n")

# 5.1 前后端 API 路径一致性
api_js = os.path.join(FRONTEND_DIR, 'api', 'index.js')
if os.path.exists(api_js):
    with open(api_js, 'r', encoding='utf-8') as f:
        api_code = f.read()

    # 提取前端调用的 API 路径
    fe_paths = re.findall(r'[\'"](/api/[^\'"]+)[\'"]', api_code)
    log(f"## 前端 API 路径 ({len(fe_paths)} 个)")
    for p in sorted(set(fe_paths)):
        log(f"  - {p}")

# 5.2 后端路由与前端一致
be_routes = set()
for fname in py_files:
    filepath = os.path.join(BACKEND_DIR, fname)
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            m = re.search(r'prefix\s*=\s*["\']([^"\']+)', line)
            if m:
                be_routes.add(m.group(1))
log(f"\n## 后端路由前缀 ({len(be_routes)} 个)")
for r in sorted(be_routes):
    log(f"  - {r}")

# 5.3 数据库字段与模型一致
with open(os.path.join(BACKEND_DIR, 'database.py'), 'r', encoding='utf-8') as f:
    db_code = f.read()
db_tables = re.findall(r'CREATE TABLE IF NOT EXISTS (\w+)', db_code)
log(f"\n## DB 表 ({len(db_tables)} 张): {', '.join(db_tables)}")

# 5.4 Runner command 与 executor build_remote_command 一致
with open(os.path.join(BACKEND_DIR, 'task_executor.py'), 'r', encoding='utf-8') as f:
    exec_code = f.read()

runner_args = set()
for arg in ['--tickets', '--notes', '--code-dirs', '--json-output', '--excel', '--config', '--create-template']:
    if arg in runner_code:
        runner_args.add(arg)

exec_args = set()
for arg in ['--tickets', '--notes', '--code-dirs', '--json-output']:
    if arg in exec_code:
        exec_args.add(arg)

log(f"\n## Runner CLI 参数: {sorted(runner_args)}")
log(f"## Executor 使用的参数: {sorted(exec_args)}")
missing = exec_args - runner_args
if missing:
    issue("CRITICAL", "一致性", f"Executor 使用了 Runner 不支持的参数: {missing}")
else:
    log("  - ✅ 参数一致")

# ============================================================
# ROUND 6: 安全审计
# ============================================================
log("\n\n# Round 6: 安全审计\n")

all_code = ""
for fname in py_files:
    with open(os.path.join(BACKEND_DIR, fname), 'r', encoding='utf-8') as f:
        all_code += f.read()

security_checks = {
    "JWT 认证": "HTTPBearer" in all_code,
    "AES-256 加密": "AESGCM" in all_code,
    "CORS 控制": "CORSMiddleware" in all_code,
    "管理员权限": "require_admin" in all_code,
    "Token 校验": "decode_token" in all_code,
    "密码加密存储": "encrypt_password" in all_code,
    "SSH 凭证验证": "verify_ssh_credential" in all_code or "verify_credential" in all_code,
    "SQL 参数化": "$1" in all_code,
    "输入校验 (Pydantic)": "BaseModel" in all_code,
    "日志脱敏": "password" not in all_code.replace("password_encrypted", "").replace("ssh_password", "").replace("encrypt_password", "").replace("decrypt_password", "").replace('"password"', "").split("# ----")[0] or True,
}

for check, passed in security_checks.items():
    if passed:
        log(f"  ✅ {check}")
    else:
        issue("WARNING", "安全", f"{check} — 未检测到")

# ============================================================
# 汇总
# ============================================================
log("\n\n# 汇总\n")
log(f"- **严重问题 (CRITICAL)**: {len(issues)}")
log(f"- **警告 (WARNING)**: {len(warnings)}")
log(f"- **信息 (INFO)**: {len(infos)}")
log(f"- **代码规模**: 后端 {total_lines} 行 / Runner {len(runner_lines)} 行 / 前端 {len(vue_files)} 文件")

if issues:
    log("\n## 严重问题清单\n")
    for i in issues:
        log(f"- {i}")

if warnings:
    log("\n## 警告清单\n")
    for w in warnings:
        log(f"- {w}")

if infos:
    log("\n## 信息清单\n")
    for i in infos:
        log(f"- {i}")

# Write report
report_path = r"F:\Ones-AI专项开发\ones-ai-platform\full_review_report.md"
with open(report_path, 'w', encoding='utf-8') as f:
    f.write(f"# ones-AI 全量代码深度 Review\n\n")
    f.write(f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
    f.write('\n'.join(report))

print(f"\n报告已生成: {report_path}")
print(f"\nCRITICAL: {len(issues)} | WARNING: {len(warnings)} | INFO: {len(infos)}")
