"""
FFmpeg辅助工具
"""
import subprocess
import os

def check_ffmpeg() -> bool:
    """检查FFmpeg是否可用"""
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def get_ffmpeg_path() -> str:
    """获取FFmpeg路径"""
    # 优先使用环境变量
    ffmpeg_path = os.environ.get("FFMPEG_PATH", "ffmpeg")
    return ffmpeg_path
