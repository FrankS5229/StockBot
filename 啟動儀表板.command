#!/usr/bin/env bash
# StockBot 一鍵啟動（macOS / Linux）—— 對應 Windows 的「啟動儀表板.bat」。
# 首次執行自動建立 .venv + 安裝套件（需網路，數分鐘）；之後直接開。
#
# macOS 使用：在 Finder 對本檔按右鍵 →「打開」（首次需授權一次）即可雙擊啟動；
# 若顯示權限不足，先在終端機執行一次：  chmod +x 啟動儀表板.command
set -euo pipefail
cd "$(dirname "$0")"

VENV=".venv"
PY="$VENV/bin/python"

echo "============================================"
echo "  StockBot one-click launcher (macOS/Linux)"
echo "  First run auto-builds the environment"
echo "  (takes a few minutes, needs internet)"
echo "  Later runs just open directly."
echo "============================================"
echo

# --- 1. 找系統 Python（需 3.10+）---
PYBIN=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1; then PYBIN="$c"; break; fi
done
if [ -z "$PYBIN" ]; then
  echo "[X] Python not found. Install Python 3.10+:"
  echo "    macOS:  brew install python   (or https://www.python.org/downloads/)"
  read -r -p "Press Enter to exit..." _
  exit 1
fi
if ! "$PYBIN" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "[X] Python too old. Need 3.10+. Current version:"
  "$PYBIN" --version
  read -r -p "Press Enter to exit..." _
  exit 1
fi

# --- 2. 首次建立 venv ---
if [ ! -x "$PY" ]; then
  echo "[1/3] Creating virtual environment .venv ..."
  "$PYBIN" -m venv "$VENV"
fi

# --- 3. requirements.txt 變動才重裝 ---
NEED_INSTALL=0
if [ ! -f "$VENV/requirements.lock" ]; then
  NEED_INSTALL=1
elif ! cmp -s requirements.txt "$VENV/requirements.lock"; then
  NEED_INSTALL=1
fi
if [ "$NEED_INSTALL" -eq 1 ]; then
  echo "[2/3] Installing/updating packages, please wait..."
  "$PY" -m pip install --upgrade pip
  "$PY" -m pip install -r requirements.txt
  cp -f requirements.txt "$VENV/requirements.lock"
else
  echo "[2/3] Packages up to date, skipping install."
fi

# --- 4. 啟動 ---
echo "[3/3] Launching dashboard... browser opens http://localhost:8501"
echo "      (press Ctrl+C or close this window to stop the dashboard)"
echo
"$VENV/bin/streamlit" run dashboard/app.py --server.port 8501
