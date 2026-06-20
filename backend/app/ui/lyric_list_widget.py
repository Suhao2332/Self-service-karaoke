"""
歌词对照列表组件 — EasyLRC 风格 (逐词高亮)

竖排逐行显示歌词，播放时当前行逐词高亮。
支持:
  - 点击选中行 (绿色)
  - 播放中当前行 + 当前词 (蓝色背景 + 亮色字)
  - 已过行 (灰色)
  - 每行显示: [#编号] [时间] 歌词文本
  - 信号通知选中变更 / 双击跳转
"""
from typing import List, Dict, Optional
from PyQt6.QtCore import Qt, QPoint, QPointF, pyqtSignal, QRectF
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QFont, QBrush, QPalette, QFontMetrics,
    QMouseEvent,
)
from PyQt6.QtWidgets import QWidget, QSizePolicy


# ── 配色 ──
ROW_HEIGHT = 38
ROW_PAD = 3
LEFT_MARGIN = 12

COLOR_BG = QColor("#1e1e2e")
COLOR_SEP = QColor("#313244")

# 已过 — 灰色
C_PAST_BG = QColor("#1e1e2e")
C_PAST_TEXT = QColor("#585b70")
C_PAST_TIME = QColor("#45475a")

# 当前行 — 蓝色背景
C_CUR_BG = QColor("#1e3a5f")
C_CUR_TEXT = QColor("#cdd6f4")       # 未唱到的字
C_CUR_TIME = QColor("#74c7ec")
C_CUR_BORDER = QColor("#89b4fa")
C_CUR_WORD = QColor("#ffffff")       # 当前唱到的字
C_CUR_WORD_BG = QColor("#89b4fa")    # 当前字背景

# 未来 — 正常
C_FUT_BG = QColor("#1e1e2e")
C_FUT_TEXT = QColor("#cdd6f4")
C_FUT_TIME = QColor("#6c7086")

# 选中 — 绿色
C_SEL_BG = QColor("#1a3a2a")
C_SEL_TEXT = QColor("#a6e3a1")
C_SEL_TIME = QColor("#94e2d5")
C_SEL_BORDER = QColor("#a6e3a1")

# 选中且当前
C_SC_BG = QColor("#1a4a3a")
C_SC_TEXT = QColor("#a6e3a1")
C_SC_TIME = QColor("#94e2d5")
C_SC_BORDER = QColor("#a6e3a1")
C_SC_WORD = QColor("#ffffff")
C_SC_WORD_BG = QColor("#a6e3a1")


class LyricListWidget(QWidget):
    """竖排歌词列表 — 支持逐词高亮"""

    lyric_selected = pyqtSignal(int)
    lyric_double_clicked = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(300)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAutoFillBackground(True)
        p = self.palette()
        p.setColor(QPalette.ColorRole.Window, COLOR_BG)
        self.setPalette(p)

        self._lyrics: List[Dict] = []          # 行级歌词
        self._word_lyrics: List[Dict] = []     # 逐词歌词 (flat list)
        self._line_word_map: Dict[int, List[Dict]] = {}  # line_idx → [words]
        self._playhead_sec: float = 0.0
        self._selected_index: int = -1
        self._hover_index: int = -1

    # ════════════════════════════════════════════════════════════
    # 公共 API
    # ════════════════════════════════════════════════════════════

    def set_lyrics(self, lyrics: List[Dict], word_lyrics: Optional[List[Dict]] = None,
                  line_words: Optional[List[List[Dict]]] = None):
        """
        设置歌词数据。
        line_words: 显式指定每行的逐词列表，[line0_words, line1_words, ...]。
                    提供后不再用时间推断。
        """
        self._lyrics = lyrics
        self._word_lyrics = word_lyrics or []
        self._selected_index = -1
        if line_words is not None:
            # 直接使用显式映射
            self._line_word_map = {i: wl for i, wl in enumerate(line_words) if wl}
        else:
            self._build_word_map()
        self._update_height()
        self.update()

    def set_playhead(self, sec: float):
        old = self._current_index()
        self._playhead_sec = sec
        if self._current_index() != old:
            self.update()
        elif self._word_lyrics:
            # 逐词模式下当前字变化也需要重绘
            self.update()

    def select_lyric(self, index: int):
        if 0 <= index < len(self._lyrics) and index != self._selected_index:
            self._selected_index = index
            self.update()
            y = index * (ROW_HEIGHT + ROW_PAD)
            if self.parent() and hasattr(self.parent(), 'verticalScrollBar'):
                vs = self.parent().verticalScrollBar()
                if vs:
                    vs.setValue(max(0, y - 80))

    def get_lyrics(self) -> List[Dict]:
        return self._lyrics

    def get_current_index(self) -> int:
        return self._current_index()

    def _current_index(self) -> int:
        idx = -1
        for i, l in enumerate(self._lyrics):
            if l.get("time", 0.0) <= self._playhead_sec:
                idx = i
            else:
                break
        return idx

    # ════════════════════════════════════════════════════════════
    # 逐词映射
    # ════════════════════════════════════════════════════════════

    def _build_word_map(self):
        """将逐词列表按行分组"""
        self._line_word_map = {}
        if not self._word_lyrics or not self._lyrics:
            return

        w_idx = 0
        for i, line in enumerate(self._lyrics):
            line_start = line.get("time", 0.0)
            line_end = self._get_line_end(i)
            words = []
            while w_idx < len(self._word_lyrics):
                w = self._word_lyrics[w_idx]
                ws = w.get("start", 0.0)
                we = w.get("end", 0.0)
                # 词完全在下一行之后 → 停止
                if ws >= line_end and we >= line_end:
                    break
                # 词与当前行有交集 → 归属当前行
                if we > line_start and ws < line_end:
                    words.append(w)
                w_idx += 1
            if words:
                self._line_word_map[i] = words

    def _get_line_end(self, idx: int) -> float:
        if idx < len(self._lyrics) - 1:
            return self._lyrics[idx + 1].get("time", 999999.0)
        return float('inf')

    def _find_active_word(self, line_idx: int) -> int:
        """返回当前行内活跃字的索引，-1 表示没有"""
        words = self._line_word_map.get(line_idx, [])
        for j, w in enumerate(words):
            ws = w.get("start", 0.0)
            we = w.get("end", 0.0)
            if ws <= self._playhead_sec < we:
                return j
        return -1

    # ════════════════════════════════════════════════════════════
    # 绘制
    # ════════════════════════════════════════════════════════════

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), COLOR_BG)

        if not self._lyrics:
            painter.setPen(C_FUT_TIME)
            painter.setFont(QFont("Microsoft YaHei", 12))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "暂无歌词数据")
            return

        cur = self._current_index()

        for i, lyric in enumerate(self._lyrics):
            y = i * (ROW_HEIGHT + ROW_PAD) + ROW_PAD
            w = self.width()

            is_cur = (i == cur)
            is_sel = (i == self._selected_index)
            text = lyric.get("text", "")
            t = lyric.get("time", 0.0)

            # ── 颜色 ──
            if is_sel and is_cur:
                bg, tx, tm, bd = C_SC_BG, C_SC_TEXT, C_SC_TIME, C_SC_BORDER
            elif is_sel:
                bg, tx, tm, bd = C_SEL_BG, C_SEL_TEXT, C_SEL_TIME, C_SEL_BORDER
            elif is_cur:
                bg, tx, tm, bd = C_CUR_BG, C_CUR_TEXT, C_CUR_TIME, C_CUR_BORDER
            elif i < cur:
                bg, tx, tm, bd = C_PAST_BG, C_PAST_TEXT, C_PAST_TIME, C_PAST_BG
            else:
                bg, tx, tm, bd = C_FUT_BG, C_FUT_TEXT, C_FUT_TIME, C_FUT_BG

            # 行背景
            painter.fillRect(QRectF(0, y, w, ROW_HEIGHT), bg)

            # 左侧竖线
            if is_cur or is_sel:
                painter.fillRect(QRectF(0, y, 3, ROW_HEIGHT), bd)

            # 编号
            painter.setFont(QFont("Consolas", 9))
            painter.setPen(tm)
            idx_str = f"{i+1:>3}"
            painter.drawText(
                QRectF(LEFT_MARGIN, y, 30, ROW_HEIGHT),
                Qt.AlignmentFlag.AlignVCenter, idx_str)

            # 时间
            time_str = f"{int(t)//60}:{int(t)%60:02d}.{int((t%1)*100):02d}"
            painter.drawText(
                QRectF(LEFT_MARGIN + 36, y, 78, ROW_HEIGHT),
                Qt.AlignmentFlag.AlignVCenter, time_str)

            # ── 歌词文本（逐词或整句）──
            text_x = LEFT_MARGIN + 116
            text_w = max(w - text_x - 20, 50)

            if is_cur and i in self._line_word_map:
                # 逐词绘制当前行
                self._paint_word_line(painter, i, text_x, y, text_w, tx, bd)
            else:
                # 整句绘制
                painter.setFont(QFont("Microsoft YaHei", 11))
                painter.setPen(tx)
                fm = QFontMetrics(QFont("Microsoft YaHei", 11))
                elided = fm.elidedText(text, Qt.TextElideMode.ElideRight, text_w)
                painter.drawText(
                    QRectF(text_x, y, text_w, ROW_HEIGHT),
                    Qt.AlignmentFlag.AlignVCenter, elided)

            # 下分隔线
            painter.setPen(QPen(COLOR_SEP, 1))
            painter.drawLine(
                QPointF(LEFT_MARGIN, y + ROW_HEIGHT),
                QPointF(w - 8, y + ROW_HEIGHT))

    def _paint_word_line(self, painter: QPainter, line_idx: int,
                         start_x: float, y: float, max_w: float,
                         normal_color: QColor, highlight_color: QColor):
        """逐词绘制某一行，当前字用高亮色"""
        words = self._line_word_map.get(line_idx, [])
        active = self._find_active_word(line_idx)

        painter.setFont(QFont("Microsoft YaHei", 11))
        fm = QFontMetrics(QFont("Microsoft YaHei", 11))
        x = start_x

        for j, w in enumerate(words):
            word_text = w.get("text", "")
            is_active = (j == active)

            if is_active:
                # 当前字：高亮背景 + 亮色文字
                tw = fm.horizontalAdvance(word_text) + 4
                if x + tw > start_x + max_w:
                    tw = max_w - (x - start_x)
                if tw > 4:
                    bg_rect = QRectF(x, y + 2, tw, ROW_HEIGHT - 4)
                    painter.fillRect(bg_rect, QBrush(highlight_color))
                    painter.setPen(QColor("#1e1e2e"))  # 深色字
                    painter.drawText(bg_rect, Qt.AlignmentFlag.AlignVCenter,
                                     word_text)
                x += tw
            else:
                # 非当前字：正常颜色
                painter.setPen(normal_color)
                tw = fm.horizontalAdvance(word_text)
                if x + tw > start_x + max_w:
                    tw = max_w - (x - start_x)
                    if tw <= 0:
                        break
                    elided = fm.elidedText(word_text, Qt.TextElideMode.ElideRight, int(tw))
                    painter.drawText(QRectF(x, y, tw, ROW_HEIGHT),
                                     Qt.AlignmentFlag.AlignVCenter, elided)
                    break
                painter.drawText(QRectF(x, y, tw, ROW_HEIGHT),
                                 Qt.AlignmentFlag.AlignVCenter, word_text)
                x += tw

    # ════════════════════════════════════════════════════════════
    # 交互
    # ════════════════════════════════════════════════════════════

    def _update_height(self):
        h = max(100, len(self._lyrics) * (ROW_HEIGHT + ROW_PAD) + 20)
        self.setMinimumHeight(h)

    def _hit_test(self, y: int) -> int:
        for i in range(len(self._lyrics)):
            row_y = i * (ROW_HEIGHT + ROW_PAD) + ROW_PAD
            if row_y <= y < row_y + ROW_HEIGHT:
                return i
        return -1

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            idx = self._hit_test(int(event.position().y()))
            if idx >= 0:
                self._selected_index = idx
                self.lyric_selected.emit(idx)
                self.update()

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        idx = self._hit_test(int(event.position().y()))
        if idx >= 0 and idx < len(self._lyrics):
            t = self._lyrics[idx].get("time", 0.0)
            self.lyric_double_clicked.emit(t)

    def mouseMoveEvent(self, event: QMouseEvent):
        idx = self._hit_test(int(event.position().y()))
        if idx != self._hover_index:
            self._hover_index = idx
            self.setCursor(
                Qt.CursorShape.PointingHandCursor if idx >= 0
                else Qt.CursorShape.ArrowCursor)
