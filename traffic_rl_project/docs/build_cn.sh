#!/usr/bin/env bash
# WSL 下编译中文版 PDF（用之前能编译的环境：tectonic + Windows 字体）
#
# 用法（WSL）：
#   cd /mnt/d/Code/MultiAgent/traffic_rl_project
#   bash docs/build_cn.sh
#
# 依赖：tectonic（在 PATH 中；通过 cargo install tectonic 或 GitHub release 安装）
# 字体：Windows 系统字体 simsun.ttc / simhei.ttf（/mnt/c/Windows/Fonts/）

set -e
cd "$(dirname "$0")/.."
DOCS=docs

echo "[1/2] 由 md 重生成 tex（修复列表/公式/引用/表格 bug）..."
D:/Anaconda/python.exe _md2tex.py || python3 _md2tex.py

echo "[2/2] 编译 PDF（tectonic）..."
cd "$DOCS"
tectonic --keep-intermediates --keep-logs --outdir . ITSC_PAPER_CN.tex 2>&1 | tail -20

echo
echo "输出: $DOCS/ITSC_PAPER_CN.pdf"
ls -la "$DOCS/ITSC_PAPER_CN.pdf" 2>/dev/null
