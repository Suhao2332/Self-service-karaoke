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
"""
歌曲识别模块
使用AcoustID API进行免费歌曲识别
"""
import requests
import subprocess
import json
import os
import tempfile
from typing import Optional, Dict, Tuple

class SongIdentifier:
    """歌曲识别器"""
    
    def __init__(self, api_key: str = None):
        """
        初始化歌曲识别器
        
        Args:
            api_key: AcoustID API密钥（从https://acoustid.org/免费获取）
        """
        self.api_key = api_key or "YOUR_ACOUSTID_API_KEY"
        self.api_url = "https://api.acoustid.org/v2/lookup"
        
        # 查找fpcalc工具
        self.fpcalc_path = self._find_fpcalc()
    
    def _find_fpcalc(self) -> str:
        """查找fpcalc工具路径"""
        import shutil
        
        # 检查系统PATH
        fpcalc = shutil.which("fpcalc")
        if fpcalc:
            return fpcalc
        
        # 检查常见安装路径
        common_paths = [
            "/usr/bin/fpcalc",
            "/usr/local/bin/fpcalc",
            "C:\\Program Files\\chromaprint\\fpcalc.exe",
            "C:\\Program Files (x86)\\chromaprint\\fpcalc.exe",
        ]
        
        for path in common_paths:
            if os.path.exists(path):
                return path
        
        # 检查项目目录
        local_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "bin", "fpcalc"
        )
        if os.path.exists(local_path):
            return local_path
        
        return "fpcalc"  # 默认，假设在PATH中
    
    def identify_from_audio(self, audio_path: str) -> Optional[Dict]:
        """
        从音频文件识别歌曲
        
        Args:
            audio_path: 音频文件路径
        
        Returns:
            歌曲信息字典，包含title、artist、album等
        """
        try:
            # 1. 计算音频指纹
            fingerprint, duration = self._calculate_fingerprint(audio_path)
            
            if not fingerprint or not duration:
                print("无法计算音频指纹")
                return None
            
            # 2. 查询AcoustID数据库
            song_info = self._query_acoustid(fingerprint, duration)
            
            if song_info:
                return song_info
            
            # 3. 如果失败，尝试使用音频片段
            return self._try_with_segment(audio_path)
            
        except Exception as e:
            print(f"歌曲识别失败: {e}")
            return None
    
    def _calculate_fingerprint(self, audio_path: str) -> Tuple[Optional[str], Optional[int]]:
        """
        计算音频指纹
        
        Returns:
            (fingerprint, duration) 元组
        """
        try:
            # 使用fpcalc计算指纹
            result = subprocess.run(
                [self.fpcalc_path, "-raw", "-length", "120", audio_path],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                fingerprint = None
                duration = None
                
                for line in result.stdout.split('\n'):
                    if line.startswith('FINGERPRINT='):
                        fingerprint = line.split('=', 1)[1].strip()
                    elif line.startswith('DURATION='):
                        duration = int(float(line.split('=', 1)[1].strip()))
                
                return fingerprint, duration
            
            print(f"fpcalc错误: {result.stderr}")
            
        except FileNotFoundError:
            print("未找到fpcalc工具，请安装chromaprint")
        except subprocess.TimeoutExpired:
            print("指纹计算超时")
        except Exception as e:
            print(f"指纹计算异常: {e}")
        
        return None, None
    
    def _query_acoustid(self, fingerprint: str, duration: int) -> Optional[Dict]:
        """
        查询AcoustID数据库
        
        Args:
            fingerprint: 音频指纹
            duration: 音频时长（秒）
        
        Returns:
            歌曲信息字典
        """
        params = {
            "client": self.api_key,
            "fingerprint": fingerprint,
            "duration": duration,
            "format": "json",
            "meta": "recordings+releasegroups+releases+artists"
        }
        
        try:
            response = requests.get(
                self.api_url,
                params=params,
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get("status") == "ok" and data.get("results"):
                    # 获取最佳匹配结果
                    results = data["results"]
                    results.sort(key=lambda x: x.get("score", 0), reverse=True)
                    best_result = results[0]
                    
                    if best_result.get("recordings"):
                        recording = best_result["recordings"][0]
                        
                        # 提取歌曲信息
                        title = recording.get("title", "")
                        artists = recording.get("artists", [])
                        artist = " / ".join([
                            a.get("name", "") for a in artists
                        ])
                        
                        # 获取专辑信息
                        album = ""
                        if recording.get("releasegroups"):
                            release = recording["releasegroups"][0]
                            album = release.get("title", "")
                        
                        return {
                            "title": title,
                            "artist": artist,
                            "album": album,
                            "confidence": best_result.get("score", 0),
                            "source": "acoustid"
                        }
            
            print(f"AcoustID查询失败: {response.status_code}")
            
        except requests.RequestException as e:
            print(f"AcoustID网络请求失败: {e}")
        
        return None
    
    def _try_with_segment(self, audio_path: str) -> Optional[Dict]:
        """
        使用音频片段尝试识别（提高成功率）
        """
        # 尝试不同时间段的音频片段
        segments = [0, 30, 60, 90, 120]  # 秒
        
        for start_time in segments:
            if start_time >= get_audio_duration(audio_path):
                break
            
            segment_path = None
            try:
                # 创建临时文件
                with tempfile.NamedTemporaryFile(
                    suffix=".wav", delete=False
                ) as tmp:
                    segment_path = tmp.name
                
                # 提取音频片段
                subprocess.run([
                    "ffmpeg",
                    "-i", audio_path,
                    "-ss", str(start_time),
                    "-t", "30",  # 30秒片段
                    "-acodec", "pcm_s16le",
                    "-ar", "44100",
                    "-ac", "2",
                    "-y",
                    segment_path
                ], check=True, capture_output=True, timeout=60)
                
                # 识别片段
                fingerprint, duration = self._calculate_fingerprint(segment_path)
                if fingerprint and duration:
                    result = self._query_acoustid(fingerprint, duration)
                    if result:
                        return result
                        
            except Exception as e:
                print(f"片段识别失败 ({start_time}s): {e}")
            finally:
                # 清理临时文件
                if segment_path and os.path.exists(segment_path):
                    try:
                        os.remove(segment_path)
                    except:
                        pass
        
        return None

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
    except:
        return 0.0
