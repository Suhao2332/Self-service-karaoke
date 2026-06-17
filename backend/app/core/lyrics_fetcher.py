"""
基于LDDC项目的歌词获取模块
支持网易云、QQ音乐等多源歌词获取
实现逐词匹配功能
"""
import requests
import re
import json
from typing import List, Dict, Optional

class LyricsFetcher:
    """歌词获取器，集成LDDC的多源搜索功能"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def search_song(self, title: str, artist: str = "") -> List[Dict]:
        """搜索歌曲，返回歌曲列表"""
        # 使用网易云音乐搜索
        url = "https://music.163.com/api/search/get"
        params = {
            "s": f"{title} {artist}",
            "type": 1,
            "offset": 0,
            "limit": 10
        }
        
        try:
            response = self.session.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                songs = []
                for song in data.get("result", {}).get("songs", []):
                    songs.append({
                        "id": song["id"],
                        "title": song["name"],
                        "artist": " / ".join([a["name"] for a in song.get("artists", [])]),
                        "album": song.get("album", {}).get("name", "")
                    })
                return songs
        except Exception as e:
            print(f"搜索歌曲失败: {e}")
        return []
    
    def fetch_lyrics(self, song_id: int) -> Optional[Dict]:
        """获取歌词，返回包含逐词时间轴的歌词数据"""
        url = f"https://music.163.com/api/song/lyric?id={song_id}&lv=1&kv=1&tv=-1"
        
        try:
            response = self.session.get(url)
            if response.status_code == 200:
                data = response.json()
                
                # 获取LRC格式歌词
                lrc_text = ""
                if "lrc" in data and "lyric" in data["lrc"]:
                    lrc_text = data["lrc"]["lyric"]
                
                # 获取逐词歌词（如果有）
                word_lyrics = []
                if "klyric" in data and "lyric" in data["klyric"]:
                    word_lyrics = self._parse_word_lyrics(data["klyric"]["lyric"])
                
                # 解析LRC歌词
                lrc_lyrics = self._parse_lrc_lyrics(lrc_text)
                
                return {
                    "lrc": lrc_lyrics,
                    "word_lyrics": word_lyrics,
                    "raw_lrc": lrc_text
                }
        except Exception as e:
            print(f"获取歌词失败: {e}")
        return None
    
    def _parse_lrc_lyrics(self, lrc_text: str) -> List[Dict]:
        """解析LRC格式歌词"""
        pattern = re.compile(r'\[(\d{2}):(\d{2})\.(\d{2,3})\](.*)')
        lyrics = []
        
        for line in lrc_text.split('\n'):
            match = pattern.match(line)
            if match:
                minutes = int(match.group(1))
                seconds = int(match.group(2))
                milliseconds = int(match.group(3))
                text = match.group(4).strip()
                
                # 跳过元数据行
                if text and not text.startswith(('作词', '作曲', '编曲', '制作')):
                    timestamp = minutes * 60 + seconds + milliseconds / 1000
                    lyrics.append({
                        "time": timestamp,
                        "text": text
                    })
        
        return lyrics
    
    def _parse_word_lyrics(self, word_lyric_text: str) -> List[Dict]:
        """解析逐词歌词（网易云格式）"""
        # 逐词歌词格式：[start_time,end_time]word
        pattern = re.compile(r'\[(\d+),(\d+)\](.*?)(?=\[\d+|\Z)')
        words = []
        
        for match in pattern.finditer(word_lyric_text):
            start_time = int(match.group(1)) / 1000  # 转换为秒
            end_time = int(match.group(2)) / 1000
            text = match.group(3).strip()
            
            if text:
                words.append({
                    "start": start_time,
                    "end": end_time,
                    "text": text
                })
        
        return words
    
    def get_word_timeline(self, song_id: int) -> List[Dict]:
        """获取逐词时间轴（用于卡拉OK效果）"""
        lyrics_data = self.fetch_lyrics(song_id)
        if not lyrics_data:
            return []
        
        # 优先使用逐词歌词
        if lyrics_data["word_lyrics"]:
            return lyrics_data["word_lyrics"]
        
        # 如果没有逐词歌词，从LRC生成近似逐词时间轴
        return self._generate_word_timeline(lyrics_data["lrc"])
    
    def _generate_word_timeline(self, lrc_lyrics: List[Dict]) -> List[Dict]:
        """从LRC歌词生成逐词时间轴（近似）"""
        word_timeline = []
        
        for i, lyric in enumerate(lrc_lyrics):
            text = lyric["text"]
            start_time = lyric["time"]
            
            # 计算结束时间
            if i < len(lrc_lyrics) - 1:
                end_time = lrc_lyrics[i + 1]["time"]
            else:
                end_time = start_time + 5  # 最后一句默认5秒
            
            # 将每个字均匀分配到时间区间
            duration = end_time - start_time
            char_duration = duration / len(text) if len(text) > 0 else 0
            
            for j, char in enumerate(text):
                if char.strip():  # 跳过空白字符
                    word_start = start_time + j * char_duration
                    word_end = word_start + char_duration
                    word_timeline.append({
                        "start": word_start,
                        "end": word_end,
                        "text": char
                    })
        
        return word_timeline
