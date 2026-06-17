"""
音频提取模块
使用FFmpeg从视频中提取音频
"""
import subprocess
import os

def extract_audio(video_path: str, output_path: str = None) -> str:
    """从视频中提取音频"""
    if not output_path:
        output_path = video_path.replace(".mp4", ".wav")
    
    cmd = [
        "ffmpeg",
        "-i", video_path,
        "-vn",           # 不处理视频
        "-acodec", "pcm_s16le",  # 16位PCM编码
        "-ar", "44100",  # 采样率
        "-ac", "2",      # 双声道
        "-y",            # 覆盖输出文件
        output_path
    ]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return output_path
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"音频提取失败: {e.stderr}")
