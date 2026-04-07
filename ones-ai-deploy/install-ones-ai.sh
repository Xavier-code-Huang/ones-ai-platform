#!/usr/bin/env bash
# ============================================================
#  ones-AI 独立安装器
#  用法: sudo bash install-ones-ai.sh
#  只安装 ones-AI 相关文件，不动 lango-AI 的任何内容
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NEW_VER=$(cat "$SCRIPT_DIR/version" 2>/dev/null || echo "未知")
OLD_VER=$(cat /opt/lango/ones_task_runner/version 2>/dev/null || echo "未安装")

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║       ones-AI 独立安装器                  ║"
echo "╚══════════════════════════════════════════╝"
echo "  版本: $OLD_VER → $NEW_VER"
echo ""

if [[ $EUID -ne 0 ]]; then
    echo "❌ 请使用 root 用户执行"
    exit 1
fi

# 1. 备份旧版
if [[ -d "/opt/lango/ones_task_runner" ]] && [[ "$OLD_VER" != "未安装" ]]; then
    BACKUP="/opt/lango/ones_task_runner/backup/$(date +%Y%m%d_%H%M%S)_v${OLD_VER}"
    echo "[1/3] 备份旧版到 $BACKUP ..."
    mkdir -p "$BACKUP"
    cp -a /opt/lango/ones_task_runner/ones_task_runner.py "$BACKUP/" 2>/dev/null || true
    cp -a /opt/lango/ones_task_runner/ones_task_runner "$BACKUP/" 2>/dev/null || true
    cp -a /opt/lango/ones_task_runner/config.yaml "$BACKUP/" 2>/dev/null || true
    cp -a /usr/local/bin/ones-AI "$BACKUP/" 2>/dev/null || true
    echo "  ✓ 备份完成"
else
    echo "[1/3] 首次安装，跳过备份"
fi

# 2. 安装文件
echo "[2/3] 安装 ones-AI ..."
mkdir -p /opt/lango/ones_task_runner
mkdir -p /opt/lango/commands

# runner
if [[ -f "$SCRIPT_DIR/ones_task_runner" ]]; then
    # 二进制模式
    cp -f "$SCRIPT_DIR/ones_task_runner" /opt/lango/ones_task_runner/
    chmod +x /opt/lango/ones_task_runner/ones_task_runner
    rm -f /opt/lango/ones_task_runner/ones_task_runner.py 2>/dev/null || true
    echo "  ✓ ones_task_runner (二进制)"
elif [[ -f "$SCRIPT_DIR/ones_task_runner.py" ]]; then
    # 源码模式
    cp -f "$SCRIPT_DIR/ones_task_runner.py" /opt/lango/ones_task_runner/
    rm -f /opt/lango/ones_task_runner/ones_task_runner 2>/dev/null || true
    echo "  ✓ ones_task_runner.py (源码)"
fi

# 配置
cp -f "$SCRIPT_DIR/config.yaml" /opt/lango/ones_task_runner/ 2>/dev/null || true

# execute-task skill
cp -f "$SCRIPT_DIR/commands/execute-task.md" /opt/lango/commands/ 2>/dev/null || true

# ones-AI 入口命令
if [[ -f "$SCRIPT_DIR/ones-AI" ]]; then
    cp -f "$SCRIPT_DIR/ones-AI" /usr/local/bin/ones-AI
elif [[ -f "$SCRIPT_DIR/ones-AI.sh" ]]; then
    cp -f "$SCRIPT_DIR/ones-AI.sh" /usr/local/bin/ones-AI
fi
chmod +x /usr/local/bin/ones-AI

# 版本号
cp -f "$SCRIPT_DIR/version" /opt/lango/ones_task_runner/

echo "  ✓ /opt/lango/ones_task_runner/"
echo "  ✓ /usr/local/bin/ones-AI"

# 3. 验证
echo "[3/3] 验证 ..."
if which ones-AI &>/dev/null; then
    echo "  ✓ ones-AI 命令可用"
else
    echo "  ✗ ones-AI 命令不可用"
fi

INSTALLED=$(cat /opt/lango/ones_task_runner/version 2>/dev/null || echo "?")
echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  ✅ ones-AI v${INSTALLED} 安装完成        ║"
echo "║  命令: ones-AI --help                     ║"
echo "╚══════════════════════════════════════════╝"
echo ""
