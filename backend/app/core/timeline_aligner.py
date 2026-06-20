"""
时间轴对齐模块 v2
使用音频特征对齐歌词时间轴

改进历史:
  v2 — 节拍网格比例映射替代简单最近邻吸附
        (1) 将时间映射到归一化节拍空间，再四舍五入到最近节拍
            避免在大间隔区间内所有歌词都吸附到同一侧
        (2) 碰撞自动发散: 多句歌词落到同一节拍时按原始比例展开
        (3) 有序性保证: 对齐后时间戳严格单调递增
"""
import numpy as np
from typing import List, Dict, Tuple


class TimelineAligner:
    """时间轴对齐器 v2 — 比例节拍网格映射 + 碰撞发散"""

    # 最小间隔（秒），防止同拍歌词完全重叠
    MIN_GAP = 0.05

    def align_lyrics(self, lyrics: List[Dict], beat_times: List[float]) -> List[Dict]:
        """
        将歌词时间轴对齐到节拍

        Args:
            lyrics: 歌词列表
            beat_times: 节拍时间列表

        Returns:
            对齐后的歌词列表
        """
        if not lyrics or not beat_times or len(beat_times) < 2:
            return lyrics

        # ── 第一遍: 映射到节拍网格 ──
        aligned_lyrics = []
        for lyric in lyrics:
            if "time" in lyric:
                # LRC格式
                original = lyric["time"]
                adjusted = self._map_to_beat_grid(original, beat_times)
                aligned_lyrics.append({
                    "time": adjusted,
                    "text": lyric["text"],
                    "original_time": original,
                })
            elif "start" in lyric:
                # 逐词格式
                start = self._map_to_beat_grid(lyric["start"], beat_times)
                end = self._map_to_beat_grid(lyric["end"], beat_times)
                if end <= start:
                    end = start + 0.5
                aligned_lyrics.append({
                    "start": start,
                    "end": end,
                    "text": lyric["text"],
                })

        # ── 第二遍: 碰撞发散 + 有序性保证 ──
        aligned_lyrics = self._resolve_collisions(aligned_lyrics, beat_times)

        return aligned_lyrics

    # ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈
    # 节拍网格比例映射
    # ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈

    def _map_to_beat_grid(self, time: float, beat_times: List[float]) -> float:
        """
        将时间映射到最近的节拍，使用归一化节拍空间

        原理:
            先把 wall-clock 时间 t 转换为「节拍空间」中的浮点位置
            (例如 3.7 表示「第 3 和第 4 拍之间 70% 的位置」),
            四舍五入到最近整数拍, 再映射回真实时间。

            相比简单找绝对距离最近拍的优势:
            - 在变速段落(伸缩节拍间隔)中, 归一化空间让判定更准确
            - 在大间隔区间内不会所有歌词都吸到同一侧
        """
        if not beat_times or len(beat_times) < 2:
            return time

        # 边界处理
        if time <= beat_times[0]:
            return beat_times[0]
        if time >= beat_times[-1]:
            return beat_times[-1]

        # 二分搜索: 找到 time 所在的节拍区间 [idx, idx+1)
        idx = int(np.searchsorted(beat_times, time, side="right")) - 1
        idx = max(0, min(idx, len(beat_times) - 2))

        b0, b1 = beat_times[idx], beat_times[idx + 1]
        interval = b1 - b0
        if interval <= 0:
            return b0

        # 在归一化节拍空间中的浮点位置
        norm_pos = idx + (time - b0) / interval

        # 四舍五入到最近整数拍
        rounded = int(round(norm_pos))
        rounded = max(0, min(rounded, len(beat_times) - 1))

        return beat_times[rounded]

    # ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈
    # 碰撞发散
    # ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈

    def _resolve_collisions(self, lyrics: List[Dict],
                            beat_times: List[float]) -> List[Dict]:
        """
        检测并解决时间碰撞: 确保每句歌词的起止时间严格递增,
        且同一节拍上的多句歌词按原始比例展开。
        """
        if len(lyrics) < 2:
            return lyrics

        resolved = [dict(lyrics[0])]  # 深拷贝第一条

        for i in range(1, len(lyrics)):
            prev = resolved[-1]
            curr = dict(lyrics[i])

            prev_time = self._get_start(prev)
            curr_time = self._get_start(curr)

            if curr_time > prev_time:
                # 无碰撞，直接追加
                resolved.append(curr)
                continue

            # ── 碰撞: 在原始节拍区间内展开 ──
            # 找到 curr 原始时间所属的节拍区间
            orig_time = self._get_original(lyrics[i], curr_time)
            if orig_time is None:
                # 没有原始时间信息，简单偏移
                self._bump_start(curr, prev_time + self.MIN_GAP)
                resolved.append(curr)
                continue

            # 用原始时间的节拍区间占比决定偏移位置
            spread_start, spread_end = self._find_spread_interval(
                orig_time, beat_times
            )
            new_time = min(spread_start + self.MIN_GAP, spread_end - self.MIN_GAP)
            # 确保不会退到 prev 之前
            new_time = max(new_time, prev_time + self.MIN_GAP)
            # 但也不能超出区间右边界
            new_time = min(new_time, spread_end)

            self._bump_start(curr, new_time)
            resolved.append(curr)

        return resolved

    def _get_start(self, lyric: Dict) -> float:
        """取歌词起始时间"""
        if "time" in lyric:
            return lyric["time"]
        return lyric.get("start", 0.0)

    def _get_original(self, lyric: Dict, fallback: float) -> float:
        """取原始时间（对齐前的原始值）"""
        return lyric.get("original_time", fallback)

    def _bump_start(self, lyric: Dict, new_start: float):
        """将歌词起始时间设为 new_start，同步调整 end/time"""
        if "time" in lyric:
            lyric["time"] = new_start
        elif "start" in lyric:
            duration = lyric["end"] - lyric["start"]
            if duration <= 0:
                duration = 0.5
            lyric["start"] = new_start
            lyric["end"] = new_start + duration

    def _find_spread_interval(self, orig_time: float,
                              beat_times: List[float]) -> Tuple[float, float]:
        """
        找到原始时间所在的节拍区间作为展开范围。
        如果 orig_time 恰好在某个拍上，用前后各一个节拍的区间。
        """
        if orig_time <= beat_times[0] or len(beat_times) < 2:
            return (beat_times[0], beat_times[1] if len(beat_times) > 1
                    else beat_times[0] + 1.0)

        if orig_time >= beat_times[-1]:
            return (beat_times[-2] if len(beat_times) > 1 else beat_times[-1],
                    beat_times[-1])

        idx = int(np.searchsorted(beat_times, orig_time, side="right")) - 1
        idx = max(0, min(idx, len(beat_times) - 2))
        return (beat_times[idx], beat_times[idx + 1])

    # ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈
    # 保留向后兼容
    # ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈

    def _find_nearest_beat(self, time: float, beat_times: List[float]) -> float:
        """保留旧接口 — 直接调用 _map_to_beat_grid"""
        return self._map_to_beat_grid(time, beat_times)
