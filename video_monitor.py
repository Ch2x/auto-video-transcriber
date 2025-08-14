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
        
        # 跟踪已处理和正在处理的文件
        self.processed_files = set()  # 已完成处理的文件
        self.processing_files = set()  # 正在处理中的文件
        self.max_processed_files = config.get('max_processed_files_cache', 1000)  # 最大缓存数量
        
    def on_created(self, event):
        if event.is_directory:
            return
            
        file_path = Path(event.src_path)
        if file_path.suffix.lower() in self.supported_formats:
            self._handle_video_file(file_path, "创建")
    
    def on_modified(self, event):
        if event.is_directory:
            return
            
        file_path = Path(event.src_path)
        if file_path.suffix.lower() in self.supported_formats:
            self._handle_video_file(file_path, "修改")
    
    def _handle_video_file(self, file_path, event_type):
        """统一处理视频文件事件"""
        try:
            # 获取文件的唯一标识（路径 + 大小 + 修改时间）
            file_stat = file_path.stat()
            file_key = f"{file_path.resolve()}_{file_stat.st_size}_{file_stat.st_mtime}"
        except (OSError, FileNotFoundError):
            logger.warning(f"无法获取文件信息，跳过: {file_path}")
            return
        
        # 检查文件是否已经处理过或正在处理中
        if file_key in self.processed_files:
            logger.info(f"文件已处理过，跳过: {file_path}")
            return
            
        if file_key in self.processing_files:
            logger.info(f"文件正在处理中，跳过重复事件: {file_path}")
            return
        
        logger.info(f"检测到{event_type}视频文件: {file_path}")
        logger.debug(f"文件唯一标识: {file_key}")
        
        # 标记为正在处理
        self.processing_files.add(file_key)
        
        try:
            # 等待文件完全写入
            if self.wait_for_file_complete(file_path):
                self.process_video(file_path)
                # 标记为已处理
                self.processed_files.add(file_key)
                logger.info(f"文件已标记为已处理: {file_path.name}")
                self._cleanup_processed_files_cache()
            else:
                logger.warning(f"文件可能仍在写入，跳过处理: {file_path}")
        finally:
            # 从正在处理列表中移除
            self.processing_files.discard(file_key)
    
    def _cleanup_processed_files_cache(self):
        """清理已处理文件缓存，避免内存无限增长"""
        if len(self.processed_files) > self.max_processed_files:
            # 移除最旧的一半记录（简单的FIFO策略）
            files_to_remove = len(self.processed_files) - self.max_processed_files // 2
            files_list = list(self.processed_files)
            for i in range(files_to_remove):
                self.processed_files.discard(files_list[i])
            logger.debug(f"清理已处理文件缓存，移除了 {files_to_remove} 条记录")
    
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
        """从视频中提取音频，优化中文语音识别"""
        try:
            audio_path = self.temp_audio_dir / f"{video_path.stem}.wav"
            
            # 优化的音频提取参数，更适合中文语音识别
            (
                ffmpeg
                .input(str(video_path))
                .output(
                    str(audio_path), 
                    acodec='pcm_s16le',     # 16位PCM编码
                    ac=1,                   # 单声道
                    ar='16000',             # 16kHz采样率（Whisper推荐）
                    af='highpass=f=80,lowpass=f=8000',  # 高通和低通滤波，保留语音频段
                    **{'b:a': '256k'}       # 音频比特率
                )
                .overwrite_output()
                .run(quiet=True, capture_stdout=True, capture_stderr=True)
            )
            
            # 检查音频文件是否成功创建
            if not audio_path.exists() or audio_path.stat().st_size == 0:
                logger.error("音频提取失败：输出文件为空")
                return None
            
            logger.info(f"音频提取完成: {audio_path} (大小: {audio_path.stat().st_size} bytes)")
            return audio_path
            
        except ffmpeg.Error as e:
            logger.error(f"FFmpeg音频提取失败: {e.stderr.decode() if e.stderr else str(e)}")
            return None
        except Exception as e:
            logger.error(f"音频提取失败: {e}")
            return None
    
    def transcribe_audio(self, audio_path):
        """使用Faster-Whisper转录音频"""
        try:
            logger.info("开始语音识别...")
            
            # 从配置文件获取Whisper参数
            whisper_opts = self.config.get('whisper_options', {})
            language = self.config.get('whisper_language', 'zh')
            
            # 优化的中文语音识别参数
            segments, info = self.whisper_model.transcribe(
                str(audio_path),
                beam_size=whisper_opts.get('beam_size', 5),
                language=language,
                condition_on_previous_text=whisper_opts.get('condition_on_previous_text', True),
                temperature=whisper_opts.get('temperature', 0.0),
                compression_ratio_threshold=whisper_opts.get('compression_ratio_threshold', 2.4),
                logprob_threshold=whisper_opts.get('logprob_threshold', -1.0),
                no_speech_threshold=whisper_opts.get('no_speech_threshold', 0.6),
                word_timestamps=whisper_opts.get('word_timestamps', True),
                vad_filter=whisper_opts.get('vad_filter', True),
                vad_parameters=dict(
                    min_silence_duration_ms=500,  # 最小静音持续时间
                    speech_pad_ms=400,            # 语音填充时间
                )
            )
            
            logger.info(f"识别语言: {info.language} (置信度: {info.language_probability:.2f})")
            logger.info(f"音频时长: {info.duration:.2f}秒")
            
            # 收集所有文本段落，优化格式
            transcript_text = ""
            total_segments = 0
            
            for segment in segments:
                total_segments += 1
                # 清理文本：去除多余空格，优化标点
                clean_text = self._clean_chinese_text(segment.text)
                
                if clean_text.strip():  # 只添加非空文本
                    # 格式化时间戳
                    start_time = self._format_timestamp(segment.start)
                    end_time = self._format_timestamp(segment.end)
                    transcript_text += f"[{start_time} - {end_time}] {clean_text}\n"
            
            logger.info(f"语音识别完成，共识别 {total_segments} 个片段")
            
            if not transcript_text.strip():
                logger.warning("未识别到有效语音内容")
                return "未检测到清晰的语音内容"
            
            return transcript_text.strip()
            
        except Exception as e:
            logger.error(f"语音识别失败: {e}")
            return None
    
    def _clean_chinese_text(self, text):
        """清理和优化中文文本"""
        import re
        
        if not text:
            return ""
        
        # 去除多余的空格
        text = re.sub(r'\s+', ' ', text.strip())
        
        # 优化中文标点符号
        text = text.replace('，', '，')
        text = text.replace('。', '。')
        text = text.replace('？', '？')
        text = text.replace('！', '！')
        text = text.replace('：', '：')
        text = text.replace('；', '；')
        
        # 移除英文标点前后的多余空格
        text = re.sub(r'\s*([，。？！：；])\s*', r'\1', text)
        
        # 确保句子结尾有标点
        if text and not text[-1] in '，。？！：；':
            text += '。'
        
        return text
    
    def _format_timestamp(self, seconds):
        """格式化时间戳为 MM:SS 格式"""
        minutes = int(seconds // 60)
        seconds = int(seconds % 60)
        return f"{minutes:02d}:{seconds:02d}"
    
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
            # 双重检查：确保文件没有被其他进程处理
            try:
                file_stat = video_path.stat()
                file_key = f"{video_path.resolve()}_{file_stat.st_size}_{file_stat.st_mtime}"
                if file_key in self.processed_files:
                    logger.info(f"文件已在其他地方处理过，跳过: {video_path.name}")
                    return
            except (OSError, FileNotFoundError):
                logger.warning(f"无法获取文件信息，跳过处理: {video_path}")
                return
            
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