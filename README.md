# 视频语音转文字监控服务

自动监控downloads目录下的新视频文件，使用Faster-Whisper提取语音文字，并推送到企业微信。

## 安装步骤

### 方式一：Docker部署（推荐）

1. 确保已安装Docker和Docker Compose

2. 配置企业微信Webhook：
   - 在企业微信群中添加机器人
   - 获取Webhook URL
   - 修改config.json中的wechat_webhook_url

3. 启动服务：

   ```bash
   # Linux/Mac
   chmod +x docker-run.sh
   ./docker-run.sh
   
   # Windows
   docker-run.bat
   
   # 或直接使用docker-compose
   docker-compose up -d
   ```

4. 查看服务状态：

   ```bash
   docker-compose logs -f
   ```

### 方式二：本地Python环境

1. 安装Python依赖：

```bash
pip install -r requirements.txt
```

2. 安装FFmpeg：
   - Windows: 下载FFmpeg并添加到PATH环境变量
   - 或使用chocolatey: `choco install ffmpeg`

3. 配置企业微信Webhook：
   - 在企业微信群中添加机器人
   - 获取Webhook URL
   - 修改config.json中的wechat_webhook_url

4. 启动监控服务：

```bash
python start_monitor.py
```

## 配置说明

- `wechat_webhook_url`: 企业微信机器人的Webhook地址
- `watch_directory`: 监控的目录路径
- `supported_video_formats`: 支持的视频格式
- `whisper_model`: Whisper模型大小 (tiny, base, small, medium, large)
- `whisper_device`: 运行设备 (cpu, cuda)
  - cpu: 使用CPU运行，自动使用float32计算类型
  - cuda: 使用GPU运行，自动使用float16计算类型（需要NVIDIA GPU支持）
- `whisper_language`: 语音识别语言 (zh=中文, en=英文, auto=自动检测)
- `whisper_options`: Whisper识别参数优化
  - `beam_size`: 束搜索大小，提高准确性 (默认: 5)
  - `temperature`: 随机性控制，0.0最确定 (默认: 0.0)
  - `compression_ratio_threshold`: 压缩比阈值，过滤低质量片段 (默认: 2.4)
  - `logprob_threshold`: 对数概率阈值，过滤不确定识别 (默认: -1.0)
  - `no_speech_threshold`: 静音检测阈值 (默认: 0.6)
  - `condition_on_previous_text`: 基于前文上下文 (默认: true)
  - `word_timestamps`: 启用词级时间戳 (默认: true)
  - `vad_filter`: 启用语音活动检测 (默认: true)
- `max_processed_files_cache`: 已处理文件缓存的最大数量，防止重复处理同一文件

## 中文语音识别优化

本项目针对中文语音识别进行了专门优化：

### 音频预处理

- 使用16kHz采样率，最适合Whisper模型
- 应用高通和低通滤波，保留语音频段
- 单声道处理，减少干扰

### 识别参数优化

- 明确指定中文语言，避免语言检测错误
- 启用上下文连贯性，提高长句识别准确度
- 使用语音活动检测(VAD)，过滤静音片段
- 词级时间戳，提供精确的时间定位

### 文本后处理

- 自动优化中文标点符号
- 清理多余空格和格式
- 智能添加句末标点

### 模型推荐

- `tiny`: 最快，适合实时处理，准确度较低
- `base`: 平衡速度和准确度，推荐日常使用
- `small`: 更高准确度，处理时间适中
- `medium`: 高准确度，适合重要内容
- `large`: 最高准确度，处理时间较长

## 注意事项

- 首次运行会下载Whisper模型，需要网络连接
- 大视频文件处理时间较长，请耐心等待
- 确保有足够的磁盘空间存储临时音频文件
- 中文识别效果与音频质量密切相关，建议使用清晰的录音

## 使用方法

### Docker方式

1. 修改config.json中的企业微信Webhook URL
2. 运行 `./docker-run.sh` (Linux/Mac) 或 `docker-run.bat` (Windows) 启动监控
3. 将视频文件放入downloads目录测试

### 本地Python方式

1. 修改config.json中的企业微信Webhook URL
2. 运行 `python start_monitor.py` 启动监控
3. 将视频文件放入downloads目录测试

## Docker常用命令

```bash
# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down

# 重启服务
docker-compose restart

# 查看服务状态
docker-compose ps

# 进入容器调试
docker-compose exec video-whisper-monitor bash
```
