#!/bin/bash

# 初始化 conda 以允许在脚本中使用 conda activate
eval "$(conda shell.bash hook)"

# 启动Python核心
conda activate Amadeus
# 启动时一定要将流重定向，不然进程中标准输入输出流会被影响从而导致MCP无法启动
python kernel/invoke.py 1> /dev/null 2>&1&
# $!：Bash 的特殊变量，自动保存上一个被 & 丢到后台的进程的 PID
PYTHON_PID=$!

# 写一个函数，使得关闭时连同后台 Python 进程一起关闭
cleanup() {
    echo ""
    echo "[AMADEUS]:正在关闭后台 Python 核心 (PID: $PYTHON_PID)..."
    kill $PYTHON_PID 2>/dev/null
    wait $PYTHON_PID 2>/dev/null
    echo "[AMADEUS]:已关闭。"
    exit 0
}
# 捕获 Ctrl+C / 脚本退出信号
trap cleanup SIGINT SIGTERM

# 启动Tauri应用
cd amadeus-app
npm run tauri dev

# Tauri 退出后也触发清理
cleanup