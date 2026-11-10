@echo off
chcp 65001 >nul
title 安装北京总厂稽核数据自动刷新任务

echo ========================================
echo   北京总厂日稽核问题分析报告
echo   自动刷新安装脚本
echo ========================================
echo.
echo 将创建定时任务：每天早上 8:00 自动从智能表格拉取最新数据并推送到 Cloudflare
echo.

:: 获取当前目录
set "WORK_DIR=%~dp0"
set "SCRIPT=%WORK_DIR%refresh_report.py"

:: 检查脚本是否存在
if not exist "%SCRIPT%" (
    echo [错误] 找不到 refresh_report.py
    echo 请确认脚本在 %WORK_DIR% 目录下
    pause
    exit /b 1
)

:: 先测试一次脚本能否正常运行
echo [步骤1/3] 测试脚本运行...
python "%SCRIPT%"
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [警告] 脚本测试未通过，请检查后重试
    echo 常见原因：
    echo   1. 网络不通（无法访问 pages.dev）
    echo   2. PASSWORD 与 Cloudflare 设置不一致
    echo   3. API_URL 域名不正确
    pause
    exit /b 1
)
echo [OK] 脚本测试通过
echo.

:: 删除旧任务（如果有）
echo [步骤2/3] 创建定时任务...
schtasks /DELETE /TN "北京总厂稽核数据刷新" /F >nul 2>&1

:: 创建新任务
schtasks /CREATE ^
    /TN "北京总厂稽核数据刷新" ^
    /TR "'%WORK_DIR%run_refresh.bat'" ^
    /SC DAILY ^
    /ST 08:00 ^
    /F

if %ERRORLEVEL% NEQ 0 (
    echo [错误] 定时任务创建失败
    echo 请尝试以管理员身份运行此脚本
    pause
    exit /b 1
)
echo [OK] 定时任务创建成功
echo.

:: 创建辅助启动脚本（解决路径问题）
echo @echo off > "%WORK_DIR%run_refresh.bat"
echo chcp 65001 ^>nul >> "%WORK_DIR%run_refresh.bat"
echo cd /d "%WORK_DIR%" >> "%WORK_DIR%run_refresh.bat"
echo python refresh_report.py >> "%WORK_DIR%run_refresh.bat"

:: 验证
echo [步骤3/3] 验证任务...
schtasks /QUERY /TN "北京总厂稽核数据刷新" /FO LIST | findstr /C:"任务名"
echo.
echo ========================================
echo   ✅ 安装完成！
echo ========================================
echo.
echo   ⏰ 每天 08:00 自动刷新数据
echo   📊 本机运行脚本后，刷新网页即可查看最新数据
echo.
echo   如需手动立即执行一次，请运行：
echo   schtasks /RUN /TN "北京总厂稽核数据刷新"
echo.
pause
