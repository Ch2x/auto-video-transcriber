# 使用Python 3.11作为基础镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 复制requirements文件并安装Python依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY . .

# 创建必要的目录
RUN mkdir -p downloads temp_audio logs

# 设置环境变量
ENV PYTHONUNBUFFERED=1

# 暴露端口（如果需要的话）
# EXPOSE 8000

# 启动命令
CMD ["python", "start_monitor.py"]