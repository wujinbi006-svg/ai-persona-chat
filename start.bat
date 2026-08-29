@echo off
chcp 65001 >nul
title AI 人格聊天平台 - 一键启动

echo ========================================
echo   AI 人格聊天平台 - 一键启动
echo ========================================
echo.

REM 检查 Python
where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未检测到 Python，请先安装 Python 3.10+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

REM 检查 Node
where node >nul 2>nul
if errorlevel 1 (
    echo [错误] 未检测到 Node.js，请先安装 Node.js 18+
    echo 下载地址: https://nodejs.org/
    pause
    exit /b 1
)

cd /d "%~dp0"

REM 安装后端依赖
echo [1/3] 检查后端依赖...
if not exist "backend\venv" (
    echo 创建 Python 虚拟环境...
    python -m venv backend\venv
)
call backend\venv\Scripts\activate.bat
pip install -r backend\requirements.txt -q
if errorlevel 1 (
    echo [错误] 后端依赖安装失败
    pause
    exit /b 1
)

REM 安装前端依赖
echo [2/3] 检查前端依赖...
if not exist "frontend\node_modules" (
    echo 安装前端依赖（首次可能需要几分钟）...
    cd frontend
    npm install
    if errorlevel 1 (
        echo [错误] 前端依赖安装失败
        pause
        exit /b 1
    )
    cd ..
)

REM 启动后端
echo [3/3] 启动服务...
echo.
echo 后端地址: http://127.0.0.1:8000  (局域网: http://192.168.0.147:8000)
echo 前端地址: http://127.0.0.1:5173  (局域网: http://192.168.0.147:5173)
echo.
echo 按 Ctrl+C 停止所有服务
echo ========================================

start "AI 后端" cmd /k "cd /d %~dp0 && call backend\venv\Scripts\activate.bat && cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

timeout /t 3 /nobreak >nul

start "AI 前端" cmd /k "cd /d %~dp0frontend && npm run dev"

timeout /t 2 /nobreak >nul

start "" "http://127.0.0.1:5173"

echo.
echo 服务已启动，浏览器将自动打开。
echo 如未自动打开，请手动访问: http://127.0.0.1:5173
echo.
pause
