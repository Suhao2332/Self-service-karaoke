"""
时间轴对齐模块
将歌词时间轴与音频节拍对齐
"""
from typing import List, Dict

class TimelineAligner:
    """时间轴对齐器"""
    
    def align_lyrics(self, lyrics: List[Dict], beat_times: List[float]) -> List[Dict]:
        """将歌词时间轴与节拍对齐"""
        aligned = []
        beat_index = 0
        
        for lyric in lyrics:
            if "start" in lyric:
                # 找到最近的节拍
                while beat_index < len(beat_times) and beat_times[beat_index] < lyric["start"]:
                    beat_index += 1
                
                if beat_index < len(beat_times):
                    # 对齐到最近的节拍
                    lyric["start"] = beat_times[beat_index]
                    if "end" in lyric:
                        # 计算结束时间
                        if beat_index + 1 < len(beat_times):
                            lyric["end"] = beat_times[beat_index + 1]
                        else:
                            lyric["end"] = lyric["start"] + 2
                    beat_index += 1
                
                aligned.append(lyric)
            elif "time" in lyric:
                # LRC格式
                while beat_index < len(beat_times) and beat_times[beat_index] < lyric["time"]:
                    beat_index += 1
                
                if beat_index < len(beat_times):
                    lyric["time"] = beat_times[beat_index]
                    beat_index += 1
                
                aligned.append(lyric)
        
        return aligned
"""
时间轴对齐模块
使用音频特征对齐歌词时间轴
"""
import numpy as np
from typing import List, Dict

class TimelineAligner:
    """时间轴对齐器"""
    
    def align_lyrics(self, lyrics: List[Dict], beat_times: List[float]) -> List[Dict]:
        """
        将歌词时间轴对齐到节拍
        
        Args:
            lyrics: 歌词列表
            beat_times: 节拍时间列表
        
        Returns:
            对齐后的歌词列表
        """
        if not lyrics or not beat_times:
            return lyrics
        
        aligned_lyrics = []
        
        for lyric in lyrics:
            if "time" in lyric:
                # LRC格式歌词对齐
                original_time = lyric["time"]
                adjusted_time = self._find_nearest_beat(original_time, beat_times)
                
                aligned_lyrics.append({
                    "time": adjusted_time,
                    "text": lyric["text"],
                    "original_time": original_time
                })
            elif "start" in lyric:
                # 逐词歌词对齐
                start = self._find_nearest_beat(lyric["start"], beat_times)
                end = self._find_nearest_beat(lyric["end"], beat_times)
                
                # 确保end > start
                if end <= start:
                    end = start + 0.5
                
                aligned_lyrics.append({
                    "start": start,
                    "end": end,
                    "text": lyric["text"]
                })
        
        return aligned_lyrics
    
    def _find_nearest_beat(self, time: float, beat_times: List[float]) -> float:
        """找到最近的节拍时间"""
        if not beat_times:
            return time
        
        # 转换为numpy数组
        beat_array = np.array(beat_times)
        
        # 找到最近的节拍
        idx = np.argmin(np.abs(beat_array - time))
        return beat_times[idx]
