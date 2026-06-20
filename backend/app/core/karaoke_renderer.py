"""
卡拉OK渲染模块 v2
使用FFmpeg + ASS字幕实现双行卡拉OK效果
- 两句歌词堆叠在视频下半部分
- \kf 平滑渐变填充
- 像素级位置控制（X/Y偏移）
- 支持视频帧预览
"""
import subprocess
import os
import re
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass, field


@dataclass
class KaraokeStyleConfig:
    """卡拉OK歌词样式配置"""

    # ── 字体 ──
    font_name: str = "Microsoft YaHei"
    font_size: int = 56            # 当前句字号
    next_font_scale: float = 0.7   # 下一句字号比例（相对于font_size）
    bold: bool = True
    italic: bool = False

    # ── 颜色（ASS格式 &HAABBGGRR）──
    primary_color: str = "&H00FFFFFF"       # 已唱（白）
    secondary_color: str = "&H0000FF00"     # 未唱（绿）
    outline_color: str = "&H00000000"       # 轮廓（黑）
    back_color: str = "&H00000000"          # 阴影

    # ── 下一句预览颜色（独立于唱句，内置alpha半透明）──
    next_primary_color: str = "&H8CFFFFFF"     # 预览已唱色
    next_secondary_color: str = "&H8C00FF00"   # 预览未唱色
    next_outline_color: str = "&H8C000000"     # 预览轮廓色

    # ── 轮廓/阴影 ──
    outline_width: float = 2.5
    shadow_depth: float = 1.5

    # ── 当前句位置（边缘比例，以预览窗口为基准）──
    # current_left_ratio: 当前句左边缘距左侧窗口边缘的比例 (0=贴左, 1=贴右)
    # current_bottom_ratio: 当前句底部距窗口底部的比例 (0=贴底, 1=贴顶)
    current_left_ratio: float = 0.05
    current_bottom_ratio: float = 0.12

    # ── 下一句位置（边缘比例）──
    # next_right_ratio: 下一句右边缘距右侧窗口边缘的比例 (0=贴右, 1=贴左)
    # next_bottom_ratio: 下一句底部距窗口底部的比例 (0=贴底, 1=贴顶)
    next_right_ratio: float = 0.05
    next_bottom_ratio: float = 0.05

    # ── 下一句透明度（0=全透明, 255=不透明）──
    next_alpha: int = 140

    # ── 边距（用于非\pos定位的fallback）──
    margin_l: int = 30
    margin_r: int = 30
    margin_v: int = 30

    def clone(self) -> "KaraokeStyleConfig":
        return KaraokeStyleConfig(
            font_name=self.font_name,
            font_size=self.font_size,
            next_font_scale=self.next_font_scale,
            bold=self.bold,
            italic=self.italic,
            primary_color=self.primary_color,
            secondary_color=self.secondary_color,
            outline_color=self.outline_color,
            back_color=self.back_color,
            next_primary_color=self.next_primary_color,
            next_secondary_color=self.next_secondary_color,
            next_outline_color=self.next_outline_color,
            outline_width=self.outline_width,
            shadow_depth=self.shadow_depth,
            current_left_ratio=self.current_left_ratio,
            current_bottom_ratio=self.current_bottom_ratio,
            next_right_ratio=self.next_right_ratio,
            next_bottom_ratio=self.next_bottom_ratio,
            next_alpha=self.next_alpha,
            margin_l=self.margin_l,
            margin_r=self.margin_r,
            margin_v=self.margin_v,
        )

    def _dim_color(self, color: str, alpha: int) -> str:
        """替换ASS颜色的alpha通道"""
        if color.startswith("&H") and len(color) >= 10:
            return f"&H{alpha:02X}{color[4:]}"
        return color

    def get_next_primary(self) -> str:
        return self._dim_color(self.primary_color, self.next_alpha)

    def get_next_secondary(self) -> str:
        return self._dim_color(self.secondary_color, self.next_alpha)

    def get_next_outline(self) -> str:
        return self._dim_color(self.outline_color, self.next_alpha)

    def next_font_size(self) -> int:
        return max(int(self.font_size * self.next_font_scale), 14)

    def build_style_line(self, name: str, size: int,
                         primary: str, secondary: str,
                         outline: str, back: str) -> str:
        """生成ASS V4+ Style行（统一用alignment=5居中，通过\pos控制位置）"""
        return (
            f"Style: {name},{self.font_name},{size},"
            f"{primary},{secondary},{outline},{back},"
            f"{1 if self.bold else 0},{1 if self.italic else 0},0,0,"
            f"100,100,0,0,1,"
            f"{self.outline_width:.1f},{self.shadow_depth:.1f},"
            f"5,{self.margin_l},{self.margin_r},{self.margin_v},1"
        )


class KaraokeRenderer:
    """卡拉OK渲染器 v2 — 双行堆叠布局 + 像素级位置控制"""

    _render_seq = 0  # 全局渲染序号，用于调试追踪

    def __init__(self, ffmpeg_path: str = "ffmpeg"):
        self.ffmpeg_path = ffmpeg_path
        self.last_ass_path: Optional[str] = None
        self.style_config = KaraokeStyleConfig()

    def clear_state(self):
        """清除上次渲染状态，防止残留导致重复渲染"""
        if self.last_ass_path and os.path.exists(self.last_ass_path):
            try:
                os.remove(self.last_ass_path)
            except Exception:
                pass
        self.last_ass_path = None

    # ═══════════════════════════════════════════════════════════════
    # 公共API
    # ═══════════════════════════════════════════════════════════════

    def render_karaoke(self, video_path: str, lyrics: List[Dict],
                       output_path: str,
                       style_config: Optional[KaraokeStyleConfig] = None) -> str:
        """渲染卡拉OK视频（每次渲染生成唯一ASS用于调试）"""
        from datetime import datetime
        KaraokeRenderer._render_seq += 1
        seq = KaraokeRenderer._render_seq

        self.clear_state()
        if style_config is not None:
            self.style_config = style_config

        out_dir = os.path.dirname(output_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        # 每次渲染使用带序号的唯一 ASS 文件，防止新旧混淆
        ts = datetime.now().strftime("%H%M%S")
        ass_path = os.path.join(out_dir, f"{os.path.splitext(os.path.basename(output_path))[0]}_r{seq}_{ts}.ass")
        # 清理旧 ASS 文件（无时间戳 & 带时间戳）
        base = os.path.splitext(output_path)[0]
        old_ass = base + ".ass"
        if os.path.exists(old_ass):
            os.remove(old_ass)
        import glob
        for old in glob.glob(base + "_r*_*.ass"):
            try:
                os.remove(old)
            except Exception:
                pass
        self._create_ass_subtitle(ass_path, lyrics)
        self.last_ass_path = ass_path

        ass_path_filter = ass_path.replace("\\", "/").replace(":", "\\:")
        video_size = self._get_video_size(video_path)

        # ── 构建视频滤镜链 ──
        vf_parts = []

        # 1) 非16:9视频自动加黑边
        w_str, h_str = video_size.split("x") if "x" in video_size else ("1920", "1080")
        try:
            vw, vh = int(w_str), int(h_str)
        except ValueError:
            vw, vh = 1920, 1080
        ratio = vw / vh if vh > 0 else 1.777
        if abs(ratio - 16.0 / 9.0) > 0.01:
            # 计算16:9的目标尺寸
            if ratio > 16.0 / 9.0:
                # 视频过宽：上下加黑边
                target_w = vw
                target_h = int(vw * 9 / 16)
            else:
                # 视频过高：左右加黑边
                target_h = vh
                target_w = int(vh * 16 / 9)
            # 确保偶数（264编码要求）
            target_w = target_w + (target_w % 2)
            target_h = target_h + (target_h % 2)
            vf_parts.append(
                f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:black"
            )
            # 更新字幕渲染分辨率
            video_size = f"{target_w}x{target_h}"

        # 2) ASS 字幕
        vf_parts.append(f"ass='{ass_path_filter}':original_size={video_size}")

        vf = ",".join(vf_parts)

        cmd = [
            self.ffmpeg_path,
            "-i", video_path,
            "-vf", vf,
            "-c:a", "copy",
            "-c:v", "libx264", "-crf", "18", "-preset", "medium",
            "-y",
            output_path
        ]

        try:
            subprocess.run(cmd, check=True, capture_output=True,
                           text=True, timeout=600)
            return output_path
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"FFmpeg渲染失败: {e.stderr}")
        except subprocess.TimeoutExpired:
            raise RuntimeError("渲染超时")

    def extract_preview_frame(self, video_path: str,
                               output_image: str,
                               time_sec: float = 0.5) -> bool:
        """提取视频帧用于预览"""
        try:
            subprocess.run([
                self.ffmpeg_path,
                "-ss", str(time_sec),
                "-i", video_path,
                "-vframes", "1",
                "-q:v", "2",
                "-y", output_image
            ], check=True, capture_output=True, timeout=30)
            return os.path.exists(output_image)
        except Exception:
            return False

    def generate_preview_ass(self, sample_text: str = "示例歌词预览") -> str:
        """生成预览用ASS片段"""
        cfg = self.style_config
        return self._generate_ass_header() + "\n".join([
            self._make_dialogue(
                "LineA", 0, 5,
                self._make_karaoke(sample_text, 0, 5),
                anchor=1,
                x_ratio=cfg.current_left_ratio,
                y_ratio=cfg.current_bottom_ratio,
            ),
            self._make_dialogue(
                "LineB", 0, 5,
                f"下一句: {sample_text}",
                anchor=3,
                x_ratio=1.0 - cfg.next_right_ratio,
                y_ratio=cfg.next_bottom_ratio,
            ),
        ])

    # ═══════════════════════════════════════════════════════════════
    # ASS生成
    # ═══════════════════════════════════════════════════════════════

    def _create_ass_subtitle(self, ass_path: str, lyrics: List[Dict]):
        ass_content = self._generate_ass_content(lyrics)
        with open(ass_path, "w", encoding="utf-8") as f:
            f.write(ass_content)

    def _generate_ass_content(self, lyrics: List[Dict]) -> str:
        """生成双行卡拉OK ASS — 左右交替 + 长歌词智能拆分

        偶数行 → 当前唱句左侧、预览右侧；奇数行反之。
        超长歌词自动拆为两句：前半先唱（带预览），后半随后唱（从预览过渡为唱句）。
        """
        cfg = self.style_config
        header = self._generate_ass_header()
        events = []
        # 动态阈值：3/4 屏幕宽度 (1440px@1920)
        MAX_WIDTH_UNITS = max(int(2880 / cfg.font_size), 18)

        def _est_width(text: str) -> float:
            w = 0.0
            for ch in text:
                if '\u4e00' <= ch <= '\u9fff' or '\u3000' <= ch <= '\u303f' or '\uff00' <= ch <= '\uffef':
                    w += 2.0
                else:
                    w += 1.0
            return w

        def _split_text(text: str) -> tuple:
            if "\\N" in text:
                sub_parts = text.split("\\N")
                if any(_est_width(p) > MAX_WIDTH_UNITS for p in sub_parts):
                    # 在 \\N 边界拆分，避免截断转义符
                    mid = len(sub_parts) // 2
                    if mid > 0:
                        part1 = "\\N".join(sub_parts[:mid]).strip()
                        part2 = "\\N".join(sub_parts[mid:]).strip()
                        if part1 and part2:
                            return part1, part2
                    return ("", "")
                return ("", "")
            half = len(text) // 2
            for offset in range(0, half):
                idx = half + offset
                if idx < len(text) and text[idx] in ' ,./;:!?-':
                    return text[:idx + 1].strip(), text[idx + 1:].strip()
                idx2 = half - offset
                if text[idx2] in ' ,./;:!?-':
                    return text[:idx2 + 1].strip(), text[idx2 + 1:].strip()
            return text[:half].strip(), text[half:].strip()

        # ── 预处理：先计算所有原始时间，再展开长歌词 ──
        raw_timings = []
        for i, lyric in enumerate(lyrics):
            start, end, _ = self._extract_timing(lyric, lyrics, i)
            raw_timings.append((start, end))

        expanded = []
        for i, (lyric, (start, end)) in enumerate(zip(lyrics, raw_timings)):
            text = lyric.get("text", "")
            if _est_width(text) > MAX_WIDTH_UNITS:
                part1, part2 = _split_text(text)
                if part1 and part2:
                    duration = end - start if end > start else 5.0
                    r = len(part1) / len(text)
                    mid = start + duration * r
                    expanded.append({**lyric, "text": part1, "_start": start, "_end": mid})
                    expanded.append({**lyric, "text": part2, "_start": mid, "_end": end})
                    continue
            expanded.append({**lyric, "_start": start, "_end": end})

        for i, lyric in enumerate(expanded):
            start = lyric["_start"]
            end = lyric["_end"]
            text = lyric.get("text", "")
            is_even = (i % 2 == 0)

            cur_anchor = 1 if is_even else 3
            cur_x = cfg.current_left_ratio if is_even else (1.0 - cfg.next_right_ratio)
            cur_y = cfg.current_bottom_ratio if is_even else cfg.next_bottom_ratio
            nxt_anchor = 3 if is_even else 1
            nxt_x = (1.0 - cfg.next_right_ratio) if is_even else cfg.current_left_ratio
            nxt_y = cfg.next_bottom_ratio if is_even else cfg.current_bottom_ratio

            # ── 防遮挡检测 ──
            n_text = ""
            n_lyric = None
            if i < len(expanded) - 1:
                n_lyric = expanded[i + 1]
                n_text = n_lyric.get("text", "")

            # 估算左右文本的像素宽度
            avail_w = int((1.0 - cfg.next_right_ratio) * 1920) - int(cfg.current_left_ratio * 1920)
            left_px = _est_width(text) * cfg.font_size * 0.5
            right_px = _est_width(n_text) * cfg.next_font_size() * 0.5 if n_text else 0
            # 若重叠，左半句向上抬高一行
            lift_y = 0.0
            if left_px + right_px > avail_w:
                lift_y = 0.06  # ~65px 上移一行

            # ── 当前唱句 ──
            events.append(self._make_dialogue(
                "LineA", start, end,
                self._make_karaoke(text, start, end),
                anchor=cur_anchor, x_ratio=cur_x,
                y_ratio=cur_y + (lift_y if cur_anchor == 1 else 0),
            ))

            # ── 下一句预览 ──
            if n_lyric:
                events.append(self._make_dialogue(
                    "LineB", start, end, n_text,
                    anchor=nxt_anchor, x_ratio=nxt_x,
                    y_ratio=nxt_y + (lift_y if nxt_anchor == 1 else 0),
                ))

        return header + "\n".join(events)

    def _generate_ass_header(self) -> str:
        """生成ASS头部 — LineA（上排）和 LineB（下排）两个样式"""
        cfg = self.style_config
        n_size = cfg.next_font_size()
        # LineA: 当前唱句（上排，全色）
        # LineB: 下一句预览（下排，内置半透明颜色）
        n_size = cfg.next_font_size()
        return f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{cfg.build_style_line("LineA", cfg.font_size, cfg.primary_color, cfg.secondary_color, cfg.outline_color, cfg.back_color)}
{cfg.build_style_line("LineB", n_size, cfg.next_primary_color, cfg.next_secondary_color, cfg.next_outline_color, cfg.back_color)}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    def _make_dialogue(self, style: str, start: float, end: float,
                       text: str, anchor: int,
                       x_ratio: float, y_ratio: float) -> str:
        """生成一条Dialogue，用边缘锚定\\an + \\pos控制精确位置"""
        s = self._format_time_ass(start)
        e = self._format_time_ass(end)
        pos_x = int(x_ratio * 1920)
        pos_y = int(1080 * (1 - y_ratio))
        return (
            f"Dialogue: 0,{s},{e},{style},,0,0,0,,"
            f"{{\\an{anchor}\\pos({pos_x},{pos_y})}}{text}"
        )

    def _make_karaoke(self, text: str, start: float, end: float) -> str:
        """用\\kf构建卡拉OK平滑渐变文本"""
        duration = end - start
        if duration <= 0:
            duration = 5

        parts = text.split("\\N")
        non_empty = [p for p in parts if p]
        if not non_empty:
            return text

        karaoke_lines = []
        for part in non_empty:
            chars = list(part)
            if not chars:
                continue
            cs = max(int(duration * 100 / len(chars)), 1)
            karaoke_lines.append(
                "".join(f"{{\\kf{cs}}}{ch}" for ch in chars)
            )
        return "\\N".join(karaoke_lines)

    def _extract_timing(self, lyric: Dict, lyrics: List[Dict],
                        idx: int) -> tuple:
        """提取歌词时间与文本"""
        if "start" in lyric and "end" in lyric:
            return lyric["start"], lyric["end"], lyric["text"]
        elif "time" in lyric and "text" in lyric:
            start = lyric["time"]
            end = (lyrics[idx + 1]["time"]
                   if idx < len(lyrics) - 1 and "time" in lyrics[idx + 1]
                   else start + 5)
            return start, end, lyric["text"]
        return 0.0, 5.0, ""

    # ═══════════════════════════════════════════════════════════════
    # 时间工具
    # ═══════════════════════════════════════════════════════════════

    def _format_time_ass(self, seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        cs = int((seconds % 1) * 100)
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

    def update_lyrics_timing(self, ass_path: str, time_offset: float):
        with open(ass_path, "r", encoding="utf-8") as f:
            content = f.read()

        def adjust_time(match):
            start = self._parse_ass_time(match.group(1)) + time_offset
            end = self._parse_ass_time(match.group(2)) + time_offset
            return f"{self._format_time_ass(max(0, start))},{self._format_time_ass(max(0, end))}"

        pattern = r'Dialogue: \d+,(\d+:\d{2}:\d{2}\.\d{2}),(\d+:\d{2}:\d{2}\.\d{2})'
        content = re.sub(pattern, adjust_time, content)

        with open(ass_path, "w", encoding="utf-8") as f:
            f.write(content)

    def _parse_ass_time(self, time_str: str) -> float:
        parts = time_str.split(':')
        h = int(parts[0])
        m = int(parts[1])
        sp = parts[2].split('.')
        s = int(sp[0])
        cs = int(sp[1]) if len(sp) > 1 else 0
        return h * 3600 + m * 60 + s + cs / 100

    def _get_video_size(self, video_path: str) -> str:
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=width,height",
                 "-of", "csv=p=0", video_path],
                capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split(",")
                if len(parts) == 2:
                    return f"{parts[0]}x{parts[1]}"
        except Exception:
            pass
        return "1920x1080"
