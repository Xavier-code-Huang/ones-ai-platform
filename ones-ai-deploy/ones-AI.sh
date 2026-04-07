#!/usr/bin/env bash
# ============================================================
#  ones-AI — ONES工单夜间自动处理命令
# ============================================================
#  完全模仿 Auth-Claude.sh (lango-AI) 的运行方式：
#  docker run --rm 一次性容器，用完即销，无需宿主机有Python。
#
#  用法：
#    ones-AI ONES-12345 ONES-12346          # 直接跑
#    ones-AI ONES-12345 -n "修复样式"       # 带补充说明
#    ones-AI --excel tasks.xlsx             # Excel模式
#    ones-AI                                # 交互式输入
#    ones-AI --create-template              # 生成Excel模板
#    ones-AI --help                         # 帮助
# ============================================================

set -e

# 编码保护（最小化 Linux 环境可能缺少 locale）
export LANG=C.UTF-8
export LC_ALL=C.UTF-8

# 配置
KEY_GATEWAY_URL="http://172.60.1.35:9601"
DOCKER_IMAGE="lango-claude:latest"
CURRENT_USER=$(whoami)
# 解析符号链接真实路径，避免 Docker 挂载冲突
USER_HOME=$(readlink -f "$HOME" 2>/dev/null || echo "$HOME")
WORK_DIR=$(readlink -f "$(pwd)" 2>/dev/null || echo "$(pwd)")

# 自动检测二进制模式 vs 源码模式
if [[ -x "/opt/lango/ones_task_runner/ones_task_runner" ]]; then
    RUNNER_PATH="/opt/lango/ones_task_runner/ones_task_runner"
    RUNNER_CMD="$RUNNER_PATH"
else
    RUNNER_PATH="/opt/lango/ones_task_runner/ones_task_runner.py"
    RUNNER_CMD="python3 $RUNNER_PATH"
fi

# 绕过代理访问内网
export no_proxy="172.60.1.35,localhost,127.0.0.1"
export NO_PROXY="172.60.1.35,localhost,127.0.0.1"

step() { echo "[*] $1"; }
error() { echo "[x] $1" >&2; exit 1; }
success() { echo "[ok] $1"; }

# 临时文件清理（trap确保异常退出也能清理）
CLEANUP_FILES=()
cleanup() {
    for f in "${CLEANUP_FILES[@]}"; do
        rm -f "$f" 2>/dev/null
    done
}
trap cleanup EXIT

# ---- 智能参数处理 ----
# 纯工单号（不以-开头）自动加 --tickets
# 支持逗号分隔：ones-AI 668380,668381 等效于 ones-AI 668380 668381
build_args() {
    if [ $# -eq 0 ]; then
        return
    fi

    # 先拆分逗号分隔的参数
    local expanded_args=()
    for arg in "$@"; do
        if [[ "$arg" == *,* ]] && [[ "$arg" != -* ]]; then
            # 逗号分隔的工单号，拆成多个
            IFS=',' read -ra parts <<< "$arg"
            for p in "${parts[@]}"; do
                [[ -n "${p// /}" ]] && expanded_args+=("${p// /}")
            done
        else
            expanded_args+=("$arg")
        fi
    done

    local all_tickets=true
    for arg in "${expanded_args[@]}"; do
        [[ "$arg" == -* ]] && { all_tickets=false; break; }
    done

    if $all_tickets; then
        echo "--tickets"
    fi
    for arg in "${expanded_args[@]}"; do
        echo "$arg"
    done
}

# ---- 环境检测 ----

# ---- 确保 execute-task skill 已部署到用户目录（必须在 exec 前执行） ----
COMMANDS_DIR="${USER_HOME}/.claude/commands"
mkdir -p "$COMMANDS_DIR" 2>/dev/null || true
SKILL_SRC="/opt/lango/commands/execute-task.md"
SKILL_DST="${COMMANDS_DIR}/execute-task.md"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SKILL_SRC" ]]; then
    if [[ ! -f "$SKILL_DST" ]] || ! cmp -s "$SKILL_SRC" "$SKILL_DST"; then
        cp -f "$SKILL_SRC" "$SKILL_DST"
        step "execute-task skill 已同步"
    fi
else
    # 回退：从脚本同目录的 commands/ 下找
    ALT_SRC="${SCRIPT_DIR}/commands/execute-task.md"
    if [[ -f "$ALT_SRC" ]] && { [[ ! -f "$SKILL_DST" ]] || ! cmp -s "$ALT_SRC" "$SKILL_DST"; }; then
        cp -f "$ALT_SRC" "$SKILL_DST"
        step "execute-task skill 已从脚本目录同步"
    fi
fi

# 1. 容器内执行（仅在 Docker 容器内部才走此路径，宿主机一律走 Docker 模式）
if [ -f /.dockerenv ] && [ -f "$RUNNER_PATH" ] && command -v claude &>/dev/null; then
    # 读取处理后的参数（每行一个）
    mapfile -t FINAL_ARGS < <(build_args "$@")
    if [[ -x "$RUNNER_PATH" ]] && [[ "$RUNNER_PATH" != *.py ]]; then
        exec "$RUNNER_PATH" "${FINAL_ARGS[@]}"
    else
        exec python3 "$RUNNER_PATH" "${FINAL_ARGS[@]}"
    fi
fi

# 2. 宿主机模式：docker run
step "检查 Docker..."
command -v docker &>/dev/null || error "Docker 未安装"
docker info &>/dev/null 2>&1 || error "Docker 服务未运行或无权限"
docker image inspect "$DOCKER_IMAGE" &>/dev/null 2>&1 || error "Docker 镜像 $DOCKER_IMAGE 不存在"

# ---- 获取 API Key ----
step "获取 API Key..."
# 优先用宿主机python3，没有就用docker
_fetch_key_script='
import json,urllib.request
try:
    r=urllib.request.urlopen("'"${KEY_GATEWAY_URL}"'/api/allocate?username='"${CURRENT_USER}"'",timeout=10)
    d=json.loads(r.read())
    if d.get("success"): print(d.get("api_key",""))
    else: print("ERROR:"+d.get("message",""))
except Exception as e: print("ERROR:"+str(e))'

if command -v python3 &>/dev/null; then
    API_KEY=$(python3 -c "$_fetch_key_script" 2>/dev/null)
else
    API_KEY=$(docker run --rm --network host "$DOCKER_IMAGE" python3 -c "$_fetch_key_script" 2>/dev/null)
fi

[[ "$API_KEY" == ERROR:* ]] && error "${API_KEY#ERROR:}"
[[ -z "$API_KEY" ]] && error "无法获取 API Key"
success "已认证"

# ---- 构建Docker挂载参数 ----
MOUNT_ARGS=()
MOUNT_ARGS+=(-v "${USER_HOME}:${USER_HOME}")
# 挂载 /opt/lango（ones_task_runner.py 安装在宿主机此目录）
MOUNT_ARGS+=(-v "/opt/lango:/opt/lango:ro")
# 如果工作目录不在HOME下，额外挂载
case "$WORK_DIR" in
    "${USER_HOME}"*) ;;
    *) MOUNT_ARGS+=(-v "${WORK_DIR}:${WORK_DIR}") ;;
esac

# ---- 解析 --agent-dir / --extra-mounts / --code-dirs 用于Docker挂载 ----
ARGS_ARRAY=("$@")   # 必须在此处初始化，后面解析依赖此变量
AGENT_DIR=""
EXTRA_MOUNTS=""
CODE_DIRS=()
for i in "${!ARGS_ARRAY[@]}"; do
    case "${ARGS_ARRAY[$i]}" in
        --agent-dir)
            next=$((i + 1))
            [ $next -lt ${#ARGS_ARRAY[@]} ] && AGENT_DIR="${ARGS_ARRAY[$next]}"
            ;;
        --extra-mounts)
            next=$((i + 1))
            [ $next -lt ${#ARGS_ARRAY[@]} ] && EXTRA_MOUNTS="${ARGS_ARRAY[$next]}"
            ;;
        --code-dirs)
            # 收集 --code-dirs 后面所有非 -- 开头的参数
            j=$((i + 1))
            while [ $j -lt ${#ARGS_ARRAY[@]} ] && [[ "${ARGS_ARRAY[$j]}" != --* ]]; do
                CODE_DIRS+=("${ARGS_ARRAY[$j]}")
                j=$((j + 1))
            done
            ;;
    esac
done

# Agent 目录挂载（只读）
if [[ -n "$AGENT_DIR" ]]; then
    # 解析真实路径
    AGENT_DIR_REAL=$(readlink -f "$AGENT_DIR" 2>/dev/null || echo "$AGENT_DIR")
    case "$AGENT_DIR_REAL" in
        "${USER_HOME}"*|"${WORK_DIR}"*) ;;
        *) MOUNT_ARGS+=(-v "${AGENT_DIR_REAL}:${AGENT_DIR_REAL}:ro") ;;
    esac
fi

# 代码目录挂载（读写）
for cd_path in "${CODE_DIRS[@]}"; do
    [[ -z "$cd_path" ]] && continue
    cd_real=$(readlink -f "$cd_path" 2>/dev/null || echo "$cd_path")
    case "$cd_real" in
        "${USER_HOME}"*|"${WORK_DIR}"*) ;;
        *) MOUNT_ARGS+=(-v "${cd_real}:${cd_real}") ;;
    esac
done

# 额外挂载路径（逗号分隔）
if [[ -n "$EXTRA_MOUNTS" ]]; then
    IFS=',' read -ra MOUNT_LIST <<< "$EXTRA_MOUNTS"
    for mp in "${MOUNT_LIST[@]}"; do
        mp="${mp// /}"
        [[ -z "$mp" ]] && continue
        case "$mp" in
            "${USER_HOME}"*|"${WORK_DIR}"*) ;;
            *) MOUNT_ARGS+=(-v "${mp}:${mp}") ;;
        esac
    done
fi

# ---- 处理Excel文件 ----
# --excel 指定的文件需要确保容器内可访问
# 如果文件在已挂载的目录内，不需要额外处理
# 否则额外挂载文件所在目录
EXCEL_FILE=""
for i in "${!ARGS_ARRAY[@]}"; do
    if [[ "${ARGS_ARRAY[$i]}" == "--excel" || "${ARGS_ARRAY[$i]}" == "-e" ]]; then
        next=$((i + 1))
        if [ $next -lt ${#ARGS_ARRAY[@]} ]; then
            EXCEL_FILE="${ARGS_ARRAY[$next]}"
            # 转为绝对路径
            if [[ "$EXCEL_FILE" != /* ]]; then
                EXCEL_FILE="${WORK_DIR}/${EXCEL_FILE}"
            fi
            EXCEL_DIR=$(dirname "$EXCEL_FILE")
            # 检查是否已被挂载覆盖
            case "$EXCEL_DIR" in
                "${USER_HOME}"*|"${WORK_DIR}"*) ;;
                *) MOUNT_ARGS+=(-v "${EXCEL_DIR}:${EXCEL_DIR}") ;;
            esac
        fi
    fi
done

# ---- 处理 --create-template ----
# 模板文件生成到当前目录（已挂载），容器内直接写宿主机

# ---- 构建容器 ----
# /etc/passwd（模仿Auth-Claude.sh，避免用户ID不存在问题）
CONTAINER_PASSWD=$(mktemp /tmp/ones-ai-passwd.XXXXXX)
CLEANUP_FILES+=("$CONTAINER_PASSWD")
echo "${CURRENT_USER}:x:$(id -u):$(id -g):${CURRENT_USER}:${USER_HOME}:/bin/sh" > "$CONTAINER_PASSWD"
CONTAINER_NAME="ones-ai-${CURRENT_USER}-$$"

# 构建最终参数（保留空格等特殊字符）
mapfile -t FINAL_ARGS < <(build_args "$@")

# 将参数写入临时文件，避免 printf '%q' 破坏中文字符
# 每行一个参数，容器内读取后逐行恢复
ARGS_FILE=$(mktemp /tmp/ones-ai-args.XXXXXX)
CLEANUP_FILES+=("$ARGS_FILE")
for arg in "${FINAL_ARGS[@]}"; do
    echo "$arg" >> "$ARGS_FILE"
done

step "启动 ones-AI (容器: $CONTAINER_NAME)..."

# 交互式检测：
#  - 如果带 --json-output 参数（前端调用），强制非交互
#  - 如果 stdin 不是终端（SSH/管道），用 -i
#  - 否则用 -it
DOCKER_IT="-it"
for _a in "$@"; do
    [[ "$_a" == "--json-output" ]] && { DOCKER_IT="-i"; break; }
done
if [ ! -t 0 ]; then
    DOCKER_IT="-i"
fi

docker run $DOCKER_IT --rm \
    --name "$CONTAINER_NAME" \
    --user "$(id -u):$(id -g)" \
    --network host \
    --entrypoint /bin/bash \
    -e "HOME=${USER_HOME}" \
    -e "USER=${CURRENT_USER}" \
    -e "HOSTNAME=$(hostname)" \
    -e "TERM=${TERM:-xterm-256color}" \
    -e "ANTHROPIC_AUTH_TOKEN=${API_KEY}" \
    -e "ANTHROPIC_BASE_URL=https://open.bigmodel.cn/api/anthropic" \
    -e "ANTHROPIC_DEFAULT_HAIKU_MODEL=glm-4.7" \
    -e "ANTHROPIC_DEFAULT_SONNET_MODEL=glm-4.7" \
    -e "ANTHROPIC_DEFAULT_OPUS_MODEL=glm-5" \
    -e "API_TIMEOUT_MS=3000000" \
    -e "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1" \
    -e "GIT_DISCOVERY_ACROSS_FILESYSTEM=1" \
    "${MOUNT_ARGS[@]}" \
    -v "${CONTAINER_PASSWD}:/etc/passwd:ro" \
    -v "${ARGS_FILE}:/tmp/ones-ai-args:ro" \
    -w "${WORK_DIR}" \
    "$DOCKER_IMAGE" \
    -c '
git config --global --add safe.directory "*" 2>/dev/null
mapfile -t _ARGS < /tmp/ones-ai-args
'"${RUNNER_CMD}"' "${_ARGS[@]}"
'
