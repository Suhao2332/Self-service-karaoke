"""
卡拉OK渲染模块
使用FFmpeg + ASS字幕实现卡拉OK效果
支持手动调整歌词时间轴
"""
import subprocess
import os
import json
import re
from typing import List, Dict

class KaraokeRenderer:
    """卡拉OK渲染器"""
    
    def __init__(self, ffmpeg_path: str = "ffmpeg"):
        self.ffmpeg_path = ffmpeg_path
    
    def render_karaoke(self, video_path: str, lyrics: List[Dict], 
                       output_path: str = None) -> str:
        """渲染卡拉OK视频"""
        if not output_path:
            output_path = video_path.replace(".mp4", "_karaoke.mp4")
        
        # 生成ASS字幕文件
        ass_path = video_path.replace(".mp4", ".ass")
        self._create_ass_subtitle(ass_path, lyrics)
        
        # 使用FFmpeg叠加字幕
        cmd = [
            self.ffmpeg_path,
            "-i", video_path,
            "-vf", f"ass={ass_path}",
            "-c:a", "copy",
            "-y",  # 覆盖输出文件
            output_path
        ]
        
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            return output_path
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"FFmpeg渲染失败: {e.stderr}")
    
    def _create_ass_subtitle(self, ass_path: str, lyrics: List[Dict]):
        """创建ASS字幕文件"""
        ass_content = self._generate_ass_content(lyrics)
        
        with open(ass_path, "w", encoding="utf-8") as f:
            f.write(ass_content)
    
    def _generate_ass_content(self, lyrics: List[Dict]) -> str:
        """生成ASS字幕内容"""
        ass_header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Microsoft YaHei,48,&H00FFFFFF,&H0000FF00,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,1,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        
        events = []
        for i, lyric in enumerate(lyrics):
            if "start" in lyric and "end" in lyric:
                # 逐词歌词
                start_ass = self._format_time_ass(lyric["start"])
                end_ass = self._format_time_ass(lyric["end"])
                text = lyric["text"]
                
                # 使用{\k}标签实现卡拉OK效果
                karaoke_text = f"{{\\k{int((lyric['end'] - lyric['start']) * 100)}}}{text}"
                events.append(
                    f"Dialogue: 0,{start_ass},{end_ass},Default,,0,0,0,,{karaoke_text}"
                )
            elif "time" in lyric and "text" in lyric:
                # LRC格式歌词（整句）
                start_ass = self._format_time_ass(lyric["time"])
                # 计算结束时间
                if i < len(lyrics) - 1 and "time" in lyrics[i + 1]:
                    end_ass = self._format_time_ass(lyrics[i + 1]["time"])
                else:
                    end_ass = self._format_time_ass(lyric["time"] + 5)
                
                text = lyric["text"]
                # 整句卡拉OK效果
                karaoke_text = self._create_sentence_karaoke(text, 
                    lyric["time"], 
                    lyrics[i + 1]["time"] if i < len(lyrics) - 1 and "time" in lyrics[i + 1] else lyric["time"] + 5
                )
                events.append(
                    f"Dialogue: 0,{start_ass},{end_ass},Default,,0,0,0,,{karaoke_text}"
                )
        
        return ass_header + "\n".join(events)
    
    def _format_time_ass(self, seconds: float) -> str:
        """将秒数转换为ASS时间格式 (H:MM:SS.cc)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        centiseconds = int((seconds % 1) * 100)
        return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"
    
    def _create_sentence_karaoke(self, text: str, start_time: float, 
                                  end_time: float) -> str:
        """创建整句卡拉OK效果"""
        duration = end_time - start_time
        char_duration = duration / len(text) if len(text) > 0 else 0
        
        karaoke_parts = []
        for char in text:
            k_time = int(char_duration * 100)  # 转换为厘秒
            karaoke_parts.append(f"{{\\k{k_time}}}{char}")
        
        return "".join(karaoke_parts)
    
    def update_lyrics_timing(self, ass_path: str, time_offset: float):
        """手动调整歌词时间轴（偏移）"""
        with open(ass_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # 解析并调整所有时间戳
        def adjust_time(match):
            start = self._parse_ass_time(match.group(1)) + time_offset
            end = self._parse_ass_time(match.group(2)) + time_offset
            return f"{self._format_time_ass(start)},{self._format_time_ass(end)}"
        
        pattern = r'Dialogue: \d+,(\d+:\d{2}:\d{2}\.\d{2}),(\d+:\d{2}:\d{2}\.\d{2})'
        content = re.sub(pattern, adjust_time, content)
        
        with open(ass_path, "w", encoding="utf-8") as f:
            f.write(content)
    
    def _parse_ass_time(self, time_str: str) -> float:
        """解析ASS时间格式为秒数"""
        parts = time_str.split(':')
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])
        return hours * 3600 + minutes * 60 + seconds
