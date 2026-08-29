@echo off
chcp 65001 >nul
title AI 人格聊天平台 - 前端

cd /d "%~dp0frontend"

if not exist "node_modules" (
    echo 安装前端依赖...
    npm install
)

npm run dev
