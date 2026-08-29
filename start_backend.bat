@echo off
chcp 65001 >nul
title AI 人格聊天平台 - 后端

cd /d "%~dp0"

if not exist "backend\venv" (
    echo 创建 Python 虚拟环境...
    python -m venv backend\venv
)

call backend\venv\Scripts\activate.bat
pip install -r backend\requirements.txt -q

cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
