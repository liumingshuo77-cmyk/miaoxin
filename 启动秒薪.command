#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "$0")"

if [[ -d "dist/秒薪.app" ]]; then
    exec open "dist/秒薪.app"
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "请先安装 Python 3.10 或更新版本，或使用已构建的 秒薪.app。"
    read -r -p "按回车退出…"
    exit 1
fi
if [[ ! -x .venv/bin/python ]]; then
    python3 -m venv .venv
fi
if ! .venv/bin/python -c 'import webview, Cocoa, WebKit' >/dev/null 2>&1; then
    .venv/bin/python -m pip install -r requirements.txt
fi
exec .venv/bin/python 秒薪.pyw
