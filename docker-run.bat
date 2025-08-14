@echo off
chcp 65001 >nul

echo 🐳 启动视频语音转文字监控服务...

REM 检查配置文件是否存在
if not exist "config.json" (
    echo ❌ 错误: config.json 配置文件不存在
    echo 请先创建配置文件，参考 README.md
    pause
    exit /b 1
)

REM 创建必要的目录
if not exist "downloads" mkdir downloads
if not exist "temp_audio" mkdir temp_audio
if not exist "logs" mkdir logs

REM 使用 docker-compose 启动服务
docker-compose --version >nul 2>&1
if %errorlevel% == 0 (
    echo 使用 docker-compose 启动服务...
    docker-compose up -d
) else (
    docker compose version >nul 2>&1
    if %errorlevel% == 0 (
        echo 使用 docker compose 启动服务...
        docker compose up -d
    ) else (
        echo ❌ 错误: 未找到 docker-compose 或 docker compose 命令
        echo 请安装 Docker Compose
        pause
        exit /b 1
    )
)

echo ✅ 服务启动完成!
echo.
echo 📋 常用命令:
echo   查看日志: docker-compose logs -f
echo   查看日志文件: type logs\video_monitor.log
echo   停止服务: docker-compose down
echo   重启服务: docker-compose restart
echo   查看状态: docker-compose ps
echo.
pause