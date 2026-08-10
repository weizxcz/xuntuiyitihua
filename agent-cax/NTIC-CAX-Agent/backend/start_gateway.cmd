@echo off
REM 一键启动 / 重启后端 Gateway（:8001）
REM 用法：双击本文件，或命令行 start_gateway.cmd
cd /d "D:\wyg\xuntuiyitihua\NTIC-CAX-Agent\backend"

REM 1) 停掉旧的后端进程，确保配置/代码变更生效
taskkill /F /IM uvicorn.exe >nul 2>&1
taskkill /F /IM uv.exe >nul 2>&1
timeout /T 1 >nul

REM 2) 后台启动 Gateway，日志写入 gateway.log
set PYTHONUNBUFFERED=1
start "" cmd /c "C:\Users\admin\.local\bin\uv.exe run uvicorn app.gateway.app:app --host 0.0.0.0 --port 8001 --reload > gateway.log 2>&1"

echo Gateway 启动中... 日志见 backend\gateway.log
echo 就绪后访问 http://localhost:8001  （前端 http://localhost:3000）
