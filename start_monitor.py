#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频文件监控启动脚本
"""

import sys
import os
from pathlib import Path

# 添加当前目录到Python路径
sys.path.insert(0, str(Path(__file__).parent))

from video_monitor import main

if __name__ == "__main__":
    print("🎬 视频语音转文字监控服务启动中...")
    print("按 Ctrl+C 停止服务")
    print("-" * 50)
    
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 服务已停止")
    except Exception as e:
        print(f"❌ 服务启动失败: {e}")
        sys.exit(1)