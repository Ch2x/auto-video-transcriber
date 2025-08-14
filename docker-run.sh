#!/bin/bash

# 视频语音转文字监控服务 Docker 启动脚本

echo "🐳 启动视频语音转文字监控服务..."

# 检查配置文件是否存在
if [ ! -f "config.json" ]; then
    echo "❌ 错误: config.json 配置文件不存在"
    echo "请先创建配置文件，参考 README.md"
    exit 1
fi

# 创建必要的目录
mkdir -p downloads temp_audio

# 使用 docker-compose 启动服务
if command -v docker-compose &> /dev/null; then
    echo "使用 docker-compose 启动服务..."
    docker-compose up -d
elif command -v docker &> /dev/null && docker compose version &> /dev/null; then
    echo "使用 docker compose 启动服务..."
    docker compose up -d
else
    echo "❌ 错误: 未找到 docker-compose 或 docker compose 命令"
    echo "请安装 Docker Compose"
    exit 1
fi

echo "✅ 服务启动完成!"
echo ""
echo "📋 常用命令:"
echo "  查看日志: docker-compose logs -f"
echo "  停止服务: docker-compose down"
echo "  重启服务: docker-compose restart"
echo "  查看状态: docker-compose ps"