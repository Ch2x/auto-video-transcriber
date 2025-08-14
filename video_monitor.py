import os
import json
import time
import logging
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from faster_whisper import WhisperModel
import ffmpeg
import requests
import tempfile

# 配置日志
import os
log_dir = 'logs'
os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(log_dir, 'video_monitor.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class VideoFileHandler(FileSystemEventHandler):
    def __init__(self, config):
        self.config = config
        self.supported_formats = config['supported_video_formats']
        # 根据设备类型选择合适的计算类型
        compute_type = "float32" if config['whisper_device'] == "cpu" else "float16"
        
        self.whisper_model = WhisperModel(
            config['whisper_model'], 
            device=config['whisper_device'],
            compute_type=compute_type
        )
        self.temp_audio_dir = Path(config['temp_audio_dir'])
        self.temp_audio_dir.mkdir(exist_ok=True)
        
        # 文件完成检查配置
        self.file_check_config = config.get('file_completion_check', {
            'max_wait_time': 300,
            'check_interval': 5,
            'required_stable_checks': 3
        })
        
    def on_created(self, event):
        if event.is_directory:
            return
            
        file_path = Path(event.src_path)
        if file_path.suffix.lower() in self.supported_formats:
            logger.info(f"检测到新视频文件: {file_path}")
            # 等待文件完全写入
            if self.wait_for_file_complete(file_path):
                self.process_video(file_path)
            else:
                logger.warning(f"文件可能仍在写入，跳过处理: {file_path}")
    
    def wait_for_file_complete(self, file_path):
        """等待文件写入完成
        
        Args:
            file_path: 文件路径
            
        Returns:
            bool: 文件是否写入完成
        """
        max_wait_time = self.file_check_config['max_wait_time']
        check_interval = self.file_check_config['check_interval']
        required_stable_checks = self.file_check_config['required_stable_checks']
        
        logger.info(f"开始监控文件写入状态: {file_path} (最大等待{max_wait_time}秒)")
        
        start_time = time.time()
        last_size = -1
        stable_count = 0
        
        while time.time() - start_time < max_wait_time:
            try:
                if not file_path.exists():
                    logger.warning(f"文件不存在: {file_path}")
                    return False
                
                current_size = file_path.stat().st_size
                
                if current_size == last_size and current_size > 0:
                    stable_count += 1
                    logger.debug(f"文件大小稳定 ({stable_count}/{required_stable_checks}): {current_size} bytes")
                    
                    if stable_count >= required_stable_checks:
                        logger.info(f"文件写入完成: {file_path} (大小: {current_size} bytes)")
                        return True
                else:
                    if current_size != last_size:
                        logger.debug(f"文件大小变化: {last_size} -> {current_size} bytes")
                    stable_count = 0
                    last_size = current_size
                
                time.sleep(check_interval)
                
            except Exception as e:
                logger.error(f"检查文件状态时出错: {e}")
                time.sleep(check_interval)
        
        logger.warning(f"等待文件写入完成超时: {file_path}")
        return False
    
    def extract_audio(self, video_path):
        """从视频中提取音频"""
        try:
            audio_path = self.temp_audio_dir / f"{video_path.stem}.wav"
            
            # 使用ffmpeg提取音频
            (
                ffmpeg
                .input(str(video_path))
                .output(str(audio_path), acodec='pcm_s16le', ac=1, ar='16000')
                .overwrite_output()
                .run(quiet=True)
            )
            
            logger.info(f"音频提取完成: {audio_path}")
            return audio_path
            
        except Exception as e:
            logger.error(f"音频提取失败: {e}")
            return None
    
    def transcribe_audio(self, audio_path):
        """使用Faster-Whisper转录音频"""
        try:
            logger.info("开始语音识别...")
            segments, info = self.whisper_model.transcribe(
                str(audio_path),
                beam_size=5,
                language="zh"  # 可以设置为None让模型自动检测
            )
            
            # 收集所有文本段落
            transcript_text = ""
            for segment in segments:
                transcript_text += f"[{segment.start:.2f}s - {segment.end:.2f}s] {segment.text}\n"
            
            logger.info("语音识别完成")
            return transcript_text.strip()
            
        except Exception as e:
            logger.error(f"语音识别失败: {e}")
            return None
    
    def send_to_wechat(self, video_name, transcript):
        """发送结果到企业微信"""
        try:
            webhook_url = self.config['wechat_webhook_url']
            
            message = {
                "msgtype": "text",
                "text": {
                    "content": f"🎬 新视频语音转文字完成\n\n📁 文件名: {video_name}\n\n📝 转录内容:\n{transcript}"
                }
            }
            
            response = requests.post(webhook_url, json=message, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('errcode') == 0:
                    logger.info("企业微信消息发送成功")
                else:
                    logger.error(f"企业微信消息发送失败: {result}")
            else:
                logger.error(f"HTTP请求失败: {response.status_code}")
                
        except Exception as e:
            logger.error(f"发送企业微信消息失败: {e}")
    
    def process_video(self, video_path):
        """处理视频文件的完整流程"""
        try:
            logger.info(f"开始处理视频: {video_path.name}")
            
            # 1. 提取音频
            audio_path = self.extract_audio(video_path)
            if not audio_path:
                return
            
            # 2. 语音转文字
            transcript = self.transcribe_audio(audio_path)
            if not transcript:
                return
            
            # 3. 发送到企业微信
            self.send_to_wechat(video_path.name, transcript)
            
            # 4. 清理临时音频文件
            try:
                audio_path.unlink()
                logger.info("临时音频文件已清理")
            except Exception as e:
                logger.warning(f"清理临时文件失败: {e}")
                
            logger.info(f"视频处理完成: {video_path.name}")
            
        except Exception as e:
            logger.error(f"处理视频失败: {e}")

def load_config():
    """加载配置文件"""
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error("配置文件config.json不存在")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"配置文件格式错误: {e}")
        return None

def main():
    """主函数"""
    # 加载配置
    config = load_config()
    if not config:
        return
    
    # 检查监控目录
    watch_dir = Path(config['watch_directory'])
    if not watch_dir.exists():
        logger.error(f"监控目录不存在: {watch_dir}")
        return
    
    # 创建文件监控器
    event_handler = VideoFileHandler(config)
    observer = Observer()
    recursive_watch = config.get('recursive_watch', True)
    observer.schedule(event_handler, str(watch_dir), recursive=recursive_watch)
    
    # 启动监控
    observer.start()
    logger.info(f"开始监控目录: {watch_dir} (递归监控: {'是' if recursive_watch else '否'})")
    logger.info(f"支持的视频格式: {config['supported_video_formats']}")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        logger.info("监控已停止")
    
    observer.join()

if __name__ == "__main__":
    main()