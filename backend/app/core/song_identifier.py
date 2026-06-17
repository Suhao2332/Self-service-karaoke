"""
歌曲识别模块
使用Shazam API进行在线歌曲识别
"""
import requests
import hashlib
import json
from typing import Optional, Dict

class SongIdentifier:
    """歌曲识别器"""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key
        # 使用免费的Shazam API代理
        self.api_url = "https://shazam-api-free.p.rapidapi.com/shazam/identify"
    
    def identify_from_audio(self, audio_path: str) -> Optional[Dict]:
        """从音频文件识别歌曲"""
        # 读取音频文件
        with open(audio_path, "rb") as f:
            audio_data = f.read()
        
        # 计算音频指纹
        fingerprint = self._calculate_fingerprint(audio_data)
        
        # 调用识别API
        try:
            response = requests.post(
                self.api_url,
                files={"audio": (audio_path, audio_data, "audio/wav")},
                headers={
                    "X-RapidAPI-Key": self.api_key,
                    "X-RapidAPI-Host": "shazam-api-free.p.rapidapi.com"
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                if "track" in data:
                    track = data["track"]
                    return {
                        "title": track.get("title", ""),
                        "artist": track.get("subtitle", ""),
                        "album": track.get("sections", [{}])[0]
                                   .get("metadata", [{}])[0]
                                   .get("text", ""),
                        "genre": track.get("genres", {}).get("primary", ""),
                        "confidence": track.get("score", 0)
                    }
        except Exception as e:
            print(f"歌曲识别失败: {e}")
        
        return None
    
    def _calculate_fingerprint(self, audio_data: bytes) -> str:
        """计算音频指纹（简化版）"""
        return hashlib.md5(audio_data[:1024]).hexdigest()
