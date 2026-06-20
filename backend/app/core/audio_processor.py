"""
音频处理模块
从视频中提取音频，支持多种格式
"""
import subprocess
import os
from typing import Optional


def extract_audio(video_path: str, output_path: Optional[str] = None) -> str:
    """
    从视频中提取音频

    Args:
        video_path: 视频文件路径
        output_path: 输出音频路径（可选）

    Returns:
        音频文件路径
    """
    if not output_path:
        # 默认输出为WAV格式
        output_path = os.path.splitext(video_path)[0] + ".wav"

    # 确保输出目录存在
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # 使用FFmpeg提取音频
    cmd = [
        "ffmpeg",
        "-i", video_path,
        "-vn",  # 不处理视频
        "-acodec", "pcm_s16le",  # PCM 16位有符号小端格式
        "-ar", "44100",  # 44.1kHz采样率
        "-ac", "2",  # 双声道
        "-y",  # 覆盖输出文件
        output_path
    ]

    try:
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=300  # 5分钟超时
        )
        return output_path
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"音频提取失败: {e.stderr}")
    except subprocess.TimeoutExpired:
        raise RuntimeError("音频提取超时")


def get_audio_duration(audio_path: str) -> float:
    """获取音频时长（秒）"""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        audio_path
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())
    except Exception:
        return 0.0
