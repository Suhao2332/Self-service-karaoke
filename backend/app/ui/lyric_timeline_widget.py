"""
歌词时间轴可视化拖拽组件

在水平时间轴上以彩色横条展示每句歌词的开始时间，支持:
  - 鼠标拖拽调整时间
  - 播放进度指示器（playhead）
  - 高亮当前/选中歌词
  - 时间标尺
  - 信号通知时间变更
  - 歌词条宽度反映持续时间
  - 已过/当前/未来 三种视觉状态
"""
from typing import List, Dict, Optional
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal, QRect
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QFont, QBrush, QFontMetrics,
)
from PyQt6.QtWidgets import QWidget, QToolTip


# ── 配色 — Catppuccin Mocha ──
COLOR_BG = QColor("#1e1e2e")
COLOR_RULER_BG = QColor("#181825")
COLOR_RULER = QColor("#6c7086")
COLOR_RULER_TICK = QColor("#4a4d5e")
COLOR_GRID_LINE = QColor("#313244")

# 歌词条 — 正常
COLOR_BAR_NORMAL = QColor("#45475a")
COLOR_BAR_NORMAL_TEXT = QColor("#cdd6f4")
COLOR_BAR_NORMAL_BORDER = QColor("#585b70")

# 歌词条 — 已过（播放头已通过）
COLOR_BAR_PAST = QColor("#313244")
COLOR_BAR_PAST_TEXT = QColor("#6c7086")
COLOR_BAR_PAST_BORDER = QColor("#45475a")

# 歌词条 — 当前正在唱
COLOR_BAR_CURRENT = QColor("#89b4fa")
COLOR_BAR_CURRENT_TEXT = QColor("#1e1e2e")
COLOR_BAR_CURRENT_BORDER = QColor("#b4d0fb")

# 歌词条 — hover
COLOR_BAR_HOVER = QColor("#585b70")
COLOR_BAR_HOVER_TEXT = QColor("#cdd6f4")

# 歌词条 — 选中（非播放中）
COLOR_BAR_SELECTED = QColor("#a6e3a1")
COLOR_BAR_SELECTED_TEXT = QColor("#1e1e2e")

# 播放头
COLOR_PLAYHEAD = QColor("#f38ba8")
COLOR_PLAYHEAD_GLOW = QColor(243, 139, 168, 60)


class LyricTimelineWidget(QWidget):
    """可拖拽歌词时间轴 v2 — 时长条 + 三态视觉"""

    # 信号：歌词时间被用户调整 (index, new_time_sec)
    lyric_time_changed = pyqtSignal(int, float)
    # 信号：当前播放位置变化（外部驱动）
    playhead_position_changed = pyqtSignal(float)
    # 信号：选中歌词变化 (index)
    lyric_selected = pyqtSignal(int)
    # 信号：双击歌词发起跳转 (time_sec)
    lyric_double_clicked = pyqtSignal(float)

    # ── 常量 ──
    RULER_HEIGHT = 28          # 顶部标尺区高度
    BAR_HEIGHT = 30            # 每条歌词条高度
    BAR_GAP = 8                # 条间距
    BAR_MIN_WIDTH = 20         # 条最小宽度（px）
    MAX_BAR_WIDTH_RATIO = 0.95 # 条最大宽度占内容区比例
    LEFT_MARGIN = 50           # 左留白（秒数字）
    RIGHT_MARGIN = 20          # 右留白
    PLAYHEAD_WIDTH = 3         # 播放线宽度

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(200)
        self.setMouseTracking(True)

        # ── 数据 ──
        self._lyrics: List[Dict] = []
        self._duration: float = 10.0
        self._playhead_sec: float = 0.0

        # ── 交互状态 ──
        self._selected_index: int = -1
        self._hover_index: int = -1
        self._dragging_index: int = -1
        self._drag_start_x: float = 0.0
        self._drag_start_time: float = 0.0

        # 缓存几何
        self._bar_rects: List[QRectF] = []

    # ════════════════════════════════════════════════════════════
    # 公共 API
    # ════════════════════════════════════════════════════════════

    def set_lyrics(self, lyrics: List[Dict]):
        self._lyrics = lyrics
        self._selected_index = -1
        self._hover_index = -1
        self._dragging_index = -1
        self._build_bar_rects()
        self.update()

    def set_duration(self, duration_sec: float):
        self._duration = max(duration_sec, 1.0)
        self._build_bar_rects()
        self.update()

    def set_playhead(self, sec: float):
        self._playhead_sec = max(0.0, min(sec, self._duration))
        self.update()

    def select_lyric(self, index: int):
        if 0 <= index < len(self._lyrics):
            old = self._selected_index
            self._selected_index = index
            if index != old:
                self.update()

    def get_lyrics(self) -> List[Dict]:
        return self._lyrics

    def get_current_index(self) -> int:
        """根据播放头位置返回当前歌词索引"""
        idx = -1
        for i, l in enumerate(self._lyrics):
            t = l.get("time", 0.0)
            if t <= self._playhead_sec:
                idx = i
            else:
                break
        return idx

    # ════════════════════════════════════════════════════════════
    # 坐标映射
    # ════════════════════════════════════════════════════════════

    def _time_to_x(self, sec: float) -> float:
        w = self._content_width()
        if self._duration <= 0:
            return self.LEFT_MARGIN
        return self.LEFT_MARGIN + (sec / self._duration) * w

    def _x_to_time(self, x: float) -> float:
        w = self._content_width()
        if w <= 0:
            return 0.0
        ratio = (x - self.LEFT_MARGIN) / w
        return max(0.0, min(ratio * self._duration, self._duration))

    def _content_width(self) -> float:
        return max(1.0, self.width() - self.LEFT_MARGIN - self.RIGHT_MARGIN)

    def _bar_y(self, idx: int) -> float:
        return self.RULER_HEIGHT + idx * (self.BAR_HEIGHT + self.BAR_GAP) + 6

    # ════════════════════════════════════════════════════════════
    # 几何构建 — 宽度基于歌词持续时间
    # ════════════════════════════════════════════════════════════

    def _lyric_end(self, idx: int) -> float:
        """第 idx 句歌词的结束时间（下一句的开始或歌曲结束）"""
        if idx >= len(self._lyrics) - 1:
            return self._duration
        return self._lyrics[idx + 1].get("time", self._duration)

    def _compute_bar_width(self, idx: int) -> float:
        """基于歌词持续时长计算条宽度"""
        start = self._lyrics[idx].get("time", 0.0)
        end = self._lyric_end(idx)
        duration = max(end - start, 0.3)
        max_w = self._content_width() * self.MAX_BAR_WIDTH_RATIO
        ratio = duration / self._duration if self._duration > 0 else 0.1
        w = max(self.BAR_MIN_WIDTH, ratio * self._content_width())
        return min(w, max_w)

    def _build_bar_rects(self):
        self._bar_rects = []
        for i in range(len(self._lyrics)):
            t = self._lyrics[i].get("time", 0.0)
            x = self._time_to_x(t)
            y = self._bar_y(i)
            bw = self._compute_bar_width(i)
            self._bar_rects.append(QRectF(x, y, bw, self.BAR_HEIGHT))

    def _recalc_bar_positions(self):
        for i in range(len(self._lyrics)):
            if i < len(self._bar_rects):
                t = self._lyrics[i].get("time", 0.0)
                x = self._time_to_x(t)
                self._bar_rects[i].setLeft(x)
                self._bar_rects[i].setTop(self._bar_y(i))
                # 宽度也重算（因为相邻时间变了）
                bw = self._compute_bar_width(i)
                self._bar_rects[i].setWidth(bw)

    # ════════════════════════════════════════════════════════════
    # 绘制
    # ════════════════════════════════════════════════════════════

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        content_w = self._content_width()

        painter.fillRect(self.rect(), COLOR_BG)
        self._draw_ruler(painter, content_w)
        self._draw_grid(painter, content_w)
        self._draw_bars(painter)
        self._draw_playhead(painter)

    def _draw_ruler(self, painter: QPainter, content_w: float):
        painter.fillRect(QRectF(0, 0, self.width(), self.RULER_HEIGHT), COLOR_RULER_BG)
        tick_interval = self._guess_tick_interval()
        painter.setFont(QFont("Segoe UI", 9))
        t = 0.0
        while t <= self._duration:
            x = self._time_to_x(t)
            painter.setPen(QPen(COLOR_RULER_TICK, 1))
            painter.drawLine(QPointF(x, self.RULER_HEIGHT),
                             QPointF(x, self.RULER_HEIGHT - 8))
            painter.setPen(COLOR_RULER)
            label = f"{int(t)}s" if t == int(t) else ""
            if label:
                fm = painter.fontMetrics()
                tw = fm.horizontalAdvance(label)
                painter.drawText(QPointF(x - tw / 2, self.RULER_HEIGHT - 12), label)

            for sub in [0.25, 0.5, 0.75]:
                sub_t = t + sub * tick_interval
                if sub_t <= self._duration:
                    sx = self._time_to_x(sub_t)
                    painter.setPen(QPen(COLOR_RULER_TICK, 1))
                    painter.drawLine(QPointF(sx, self.RULER_HEIGHT),
                                     QPointF(sx, self.RULER_HEIGHT - 4))
            t += tick_interval

    def _guess_tick_interval(self) -> float:
        if self._duration <= 5:
            return 0.5
        elif self._duration <= 15:
            return 1.0
        elif self._duration <= 60:
            return 5.0
        else:
            return 10.0

    def _draw_grid(self, painter: QPainter, content_w: float):
        painter.setPen(QPen(COLOR_GRID_LINE, 1))
        interval = self._guess_tick_interval()
        t = 0.0
        while t <= self._duration:
            x = self._time_to_x(t)
            painter.drawLine(QPointF(x, self.RULER_HEIGHT),
                             QPointF(x, self.height()))
            t += interval

    def _draw_bars(self, painter: QPainter):
        current_idx = self.get_current_index()

        for i, lyric in enumerate(self._lyrics):
            rect = self._bar_rects[i] if i < len(self._bar_rects) else QRectF()
            text = lyric.get("text", "")

            # ── 确定颜色状态 ──
            is_past = i < current_idx and i != self._selected_index
            is_current = i == current_idx and i != self._selected_index

            if self._dragging_index == i or self._selected_index == i:
                # 选中/拖拽中 → 绿色强调
                bar_color = COLOR_BAR_SELECTED
                text_color = COLOR_BAR_SELECTED_TEXT
                border_color = COLOR_BAR_SELECTED.lighter(130)
            elif self._hover_index == i and self._dragging_index < 0:
                bar_color = COLOR_BAR_HOVER
                text_color = COLOR_BAR_HOVER_TEXT
                border_color = COLOR_BAR_HOVER.lighter(120)
            elif is_current:
                # 当前唱到的句 → 蓝色高亮
                bar_color = COLOR_BAR_CURRENT
                text_color = COLOR_BAR_CURRENT_TEXT
                border_color = COLOR_BAR_CURRENT_BORDER
            elif is_past:
                # 已经唱过的 → 灰色暗化
                bar_color = COLOR_BAR_PAST
                text_color = COLOR_BAR_PAST_TEXT
                border_color = COLOR_BAR_PAST_BORDER
            else:
                bar_color = COLOR_BAR_NORMAL
                text_color = COLOR_BAR_NORMAL_TEXT
                border_color = COLOR_BAR_NORMAL_BORDER

            painter.setPen(QPen(border_color, 1))
            painter.setBrush(QBrush(bar_color))
            painter.drawRoundedRect(rect, 6, 6)

            # 文字（左侧留padding）
            painter.setPen(text_color)
            painter.setFont(QFont("Microsoft YaHei", 9))
            fm = painter.fontMetrics()
            text_w = rect.width() - 10
            elided = fm.elidedText(text, Qt.TextElideMode.ElideRight,
                                   max(int(text_w), 10))
            painter.drawText(
                QRectF(rect.x() + 5, rect.y(), rect.width() - 10, rect.height()),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                elided
            )

    def _draw_playhead(self, painter: QPainter):
        x = self._time_to_x(self._playhead_sec)
        # 发光
        painter.setPen(QPen(COLOR_PLAYHEAD_GLOW, 8))
        painter.drawLine(QPointF(x, self.RULER_HEIGHT),
                         QPointF(x, self.height()))
        # 实线
        painter.setPen(QPen(COLOR_PLAYHEAD, self.PLAYHEAD_WIDTH))
        painter.drawLine(QPointF(x, self.RULER_HEIGHT),
                         QPointF(x, self.height()))
        # 顶部三角
        painter.setBrush(QBrush(COLOR_PLAYHEAD))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPolygon([
            QPointF(x - 5, self.RULER_HEIGHT - 8),
            QPointF(x + 5, self.RULER_HEIGHT - 8),
            QPointF(x, self.RULER_HEIGHT),
        ])

    # ════════════════════════════════════════════════════════════
    # 交互
    # ════════════════════════════════════════════════════════════

    def _hit_test(self, x: float, y: float) -> int:
        for i, rect in enumerate(self._bar_rects):
            if rect.contains(x, y):
                return i
        return -1

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            idx = self._hit_test(event.position().x(), event.position().y())
            if idx >= 0 and idx < len(self._lyrics):
                self._selected_index = idx
                self._dragging_index = idx
                self._drag_start_x = event.position().x()
                self._drag_start_time = self._lyrics[idx].get("time", 0.0)
                self.lyric_selected.emit(idx)
                self.setCursor(Qt.CursorShape.SizeHorCursor)
            else:
                click_time = self._x_to_time(event.position().x())
                self._playhead_sec = click_time
                self.playhead_position_changed.emit(click_time)
                self._selected_index = -1
                self._dragging_index = -1
            self.update()

    def mouseMoveEvent(self, event):
        x, y = event.position().x(), event.position().y()

        if self._dragging_index >= 0:
            dx = x - self._drag_start_x
            dt = self._x_to_time(self._drag_start_x + dx) - self._drag_start_time
            new_time = max(0.0, self._drag_start_time + dt)
            new_time = min(new_time, self._duration)

            if self._lyrics and self._dragging_index < len(self._lyrics):
                self._lyrics[self._dragging_index]["time"] = round(new_time, 3)
                self._recalc_bar_positions()
                self.lyric_time_changed.emit(self._dragging_index, new_time)
            self.update()

            self._playhead_sec = new_time
            self.playhead_position_changed.emit(new_time)

            text = self._lyrics[self._dragging_index].get("text", "") if \
                self._lyrics and self._dragging_index < len(self._lyrics) else ""
            QToolTip.showText(
                event.globalPosition().toPoint(),
                f"{text}  @  {new_time:.2f}s"
            )
        else:
            idx = self._hit_test(x, y)
            if idx != self._hover_index:
                self._hover_index = idx
                self.update()
            self.setCursor(Qt.CursorShape.SizeHorCursor if idx >= 0
                           else Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._dragging_index >= 0:
            self._dragging_index = -1
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.update()

    def mouseDoubleClickEvent(self, event):
        idx = self._hit_test(event.position().x(), event.position().y())
        if idx >= 0 and idx < len(self._lyrics):
            t = self._lyrics[idx].get("time", 0.0)
            self._playhead_sec = t
            self.lyric_double_clicked.emit(t)
            self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._build_bar_rects()
        self.update()
