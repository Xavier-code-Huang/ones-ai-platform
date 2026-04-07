#!/usr/bin/env bash
# ones-AI 独立打包脚本
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VERSION=$(cat version 2>/dev/null || echo "1.0.0")
OUTPUT="ones-ai-deploy-v${VERSION}.tar.gz"

echo "📦 ones-AI 打包 v${VERSION}"

tar -czf "$OUTPUT" \
    ones-AI.sh \
    ones_task_runner.py \
    config.yaml \
    version \
    commands/ \
    install-ones-ai.sh

SIZE=$(du -h "$OUTPUT" | cut -f1)
echo "✅ $OUTPUT ($SIZE)"
