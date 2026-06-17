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
