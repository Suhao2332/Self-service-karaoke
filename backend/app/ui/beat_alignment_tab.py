"""
节拍对准标签页 — EasyLRC 风格

整合音频播放器 + 竖排歌词对照列表，提供：
  - 音频播放/暂停/停止
  - 一键「节拍自动对准」
  - Space 键标记当前歌词时间
  - ← → 微调 (步进 ±0.1s)
  - 应用/取消对准结果
  - 双击歌词行跳转播放位置
"""
import os
from typing import List, Dict, Optional
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QKeyEvent
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QDoubleSpinBox, QGroupBox, QScrollArea, QSizePolicy,
)

from core.audio_player import AudioPlayer
from ui.lyric_list_widget import LyricListWidget


class BeatAlignmentTab(QWidget):
    alignment_applied = pyqtSignal(list)
    auto_align_requested = pyqtSignal(str, list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._audio_path = ""
        self._lyrics: List[Dict] = []
        self._original_lyrics: List[Dict] = []
        self._word_lyrics: List[Dict] = []
        self._line_words: List[List[Dict]] = []

        self._player = AudioPlayer()
        self._play_timer = QTimer(self)
        self._play_timer.setInterval(50)
        self._play_timer.timeout.connect(self._on_play_tick)

        self._build_ui()
        self._connect_signals()

    # ── UI (与之前相同) ──
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)
        self._build_playback_bar(layout)
        self._build_action_bar(layout)
        self._lyric_list = LyricListWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._lyric_list)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background: #1e1e2e; }
            QScrollBar:vertical { width: 8px; background: #1e1e2e; }
            QScrollBar::handle:vertical { background: #45475a; border-radius: 4px; min-height: 30px; }
            QScrollBar::handle:vertical:hover { background: #585b70; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)
        layout.addWidget(scroll, stretch=1)
        self._build_fine_tune(layout)
        self._build_bottom(layout)

    def _build_playback_bar(self, layout):  # noqa
        row = QHBoxLayout(); row.setSpacing(8)
        self._play_btn = QPushButton("▶ 播放"); self._play_btn.setFixedWidth(90)
        self._play_btn.setStyleSheet("QPushButton{background:#89b4fa;color:#1e1e2e;padding:6px 16px;border-radius:5px;font-weight:bold}QPushButton:hover{background:#74c7ec}QPushButton:disabled{background:#45475a;color:#6c7086}")
        self._stop_btn = QPushButton("⏹ 停止"); self._stop_btn.setFixedWidth(70)
        self._stop_btn.setStyleSheet("QPushButton{background:#45475a;color:#cdd6f4;padding:6px 12px;border-radius:5px}QPushButton:hover{background:#585b70}")
        self._time_label = QLabel("0:00 / 0:00"); self._time_label.setFont(QFont("Consolas", 11)); self._time_label.setStyleSheet("color:#cdd6f4")
        row.addWidget(self._play_btn); row.addWidget(self._stop_btn); row.addWidget(self._time_label); row.addStretch()
        layout.addLayout(row)

    def _build_action_bar(self, layout):  # noqa
        row = QHBoxLayout(); row.setSpacing(8)
        self._auto_align_btn = QPushButton("🎯 节拍自动对准")
        self._auto_align_btn.setStyleSheet("QPushButton{background:#89b4fa;color:#1e1e2e;padding:8px 20px;border-radius:6px;font-weight:bold;font-size:13px}QPushButton:hover{background:#74c7ec}QPushButton:disabled{background:#45475a;color:#6c7086}")
        self._mark_btn = QPushButton("⌨ 标记 (Space)")
        self._mark_btn.setStyleSheet("QPushButton{background:#fab387;color:#1e1e2e;padding:8px 16px;border-radius:6px;font-weight:bold;font-size:12px}QPushButton:hover{background:#f9e2af}")
        self._align_status = QLabel(""); self._align_status.setStyleSheet("color:#a6e3a1;font-size:12px")
        row.addWidget(self._auto_align_btn); row.addWidget(self._mark_btn); row.addWidget(self._align_status, stretch=1)
        layout.addLayout(row)

    def _build_fine_tune(self, layout):  # noqa
        box = QGroupBox("微调  (← / → 步进 ±0.1s)")
        box.setStyleSheet("QGroupBox{color:#a6adc8;font-size:12px;border:1px solid #313244;border-radius:6px;margin-top:8px;padding:10px 8px 6px 8px}QGroupBox::title{subcontrol-origin:margin;left:10px;padding:0 4px}")
        row = QHBoxLayout()
        self._selected_label = QLabel("[无]"); self._selected_label.setStyleSheet("color:#89b4fa;font-size:12px")
        self._time_spin = QDoubleSpinBox(); self._time_spin.setRange(0, 9999); self._time_spin.setDecimals(3); self._time_spin.setSingleStep(0.1)
        self._time_spin.setStyleSheet("QDoubleSpinBox{background:#313244;color:#cdd6f4;border:1px solid #45475a;border-radius:4px;padding:4px;font-size:13px}")
        self._nudge_left = QPushButton("−0.1"); self._nudge_left.setFixedWidth(50)
        self._nudge_right = QPushButton("+0.1"); self._nudge_right.setFixedWidth(50)
        row.addWidget(QLabel("选中:")); row.addWidget(self._selected_label, stretch=1)
        row.addWidget(QLabel("时间:")); row.addWidget(self._time_spin)
        row.addWidget(self._nudge_left); row.addWidget(self._nudge_right)
        box.setLayout(row); layout.addWidget(box)

    def _build_bottom(self, layout):  # noqa
        row = QHBoxLayout(); row.setSpacing(8)
        self._apply_btn = QPushButton("✔ 应用对准结果")
        self._apply_btn.setStyleSheet("QPushButton{background:#a6e3a1;color:#1e1e2e;padding:8px 24px;border-radius:6px;font-weight:bold;font-size:13px}QPushButton:hover{background:#94e2d5}QPushButton:disabled{background:#45475a;color:#6c7086}")
        self._cancel_btn = QPushButton("✖ 取消")
        self._cancel_btn.setStyleSheet("QPushButton{background:#45475a;color:#cdd6f4;padding:8px 24px;border-radius:6px;font-size:13px}QPushButton:hover{background:#585b70}")
        row.addStretch(); row.addWidget(self._cancel_btn); row.addWidget(self._apply_btn)
        layout.addLayout(row)

    def _connect_signals(self):
        self._play_btn.clicked.connect(self._toggle_play)
        self._stop_btn.clicked.connect(self._stop_playback)
        self._mark_btn.clicked.connect(self._mark_current_time)
        self._auto_align_btn.clicked.connect(self._request_auto_align)
        self._lyric_list.lyric_selected.connect(self._on_lyric_selected)
        self._lyric_list.lyric_double_clicked.connect(self._on_double_click)
        self._time_spin.valueChanged.connect(self._on_spin_changed)
        self._nudge_left.clicked.connect(lambda: self._nudge(-0.1))
        self._nudge_right.clicked.connect(lambda: self._nudge(0.1))
        self._apply_btn.clicked.connect(self._apply)
        self._cancel_btn.clicked.connect(self._cancel)

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        if key == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._on_space_pressed(); return
        elif key == Qt.Key.Key_Left:
            self._nudge(-0.1); return
        elif key == Qt.Key.Key_Right:
            self._nudge(0.1); return
        super().keyPressEvent(event)

    # ═══════════════════════════ 核心 ═══════════════════════════

    def _build_line_words(self, lyrics, word_lyrics):
        """构建显式行→词绑定列表，每行一个词列表。不再依赖时间推断。"""
        lw = [[] for _ in range(len(lyrics))]
        if not word_lyrics:
            return lw
        w_idx = 0
        for i in range(len(lyrics)):
            line_end = (lyrics[i + 1].get("time", float('inf'))
                        if i + 1 < len(lyrics) else float('inf'))
            while w_idx < len(word_lyrics):
                w = word_lyrics[w_idx]
                if w.get("start", 0.0) >= line_end:
                    break
                lw[i].append(w)
                w_idx += 1
        return lw

    def load_data(self, audio_path, lyrics, word_lyrics=None):
        self._audio_path = audio_path
        self._lyrics = [dict(l) for l in lyrics]
        self._original_lyrics = [dict(l) for l in lyrics]
        self._word_lyrics = word_lyrics or []
        self._line_words = self._build_line_words(self._lyrics, self._word_lyrics)

        if audio_path and os.path.isfile(audio_path):
            try:
                self._player.load(audio_path)
                if not self._player.is_available():
                    self._play_btn.setEnabled(False); self._play_btn.setText("⛔ 音频不可用")
            except Exception as e:
                self._align_status.setText(f"⚠️ 音频加载失败: {e}")
                self._align_status.setStyleSheet("color:#f38ba8")
                self._play_btn.setEnabled(False); self._play_btn.setText("⛔ 音频不可用")

        self._lyric_list.set_lyrics(self._lyrics, self._word_lyrics, self._line_words)
        self._update_time_label()
        self._auto_align_btn.setEnabled(True)
        self._apply_btn.setEnabled(True)

    def get_adjusted_lyrics(self):
        return list(self._lyrics)

    # ── 播放 ──
    def _toggle_play(self):
        try:
            if not self._player.is_available(): return
            if self._player.is_playing():
                self._player.pause(); self._play_timer.stop(); self._play_btn.setText("▶ 继续")
            elif self._player.is_paused():
                self._player.resume(); self._play_timer.start(); self._play_btn.setText("⏸ 暂停")
            else:
                pos = self._player.get_pos()
                if pos >= self._player.get_duration() - 0.1: pos = 0.0
                self._player.play_from(pos); self._play_timer.start(); self._play_btn.setText("⏸ 暂停")
        except Exception as e:
            self._align_status.setText(f"⚠️ 播放失败: {e}"); self._align_status.setStyleSheet("color:#f38ba8")
            self._play_timer.stop(); self._play_btn.setText("▶ 播放")

    def _stop_playback(self):
        try: self._player.stop()
        except Exception: pass
        self._play_timer.stop(); self._play_btn.setText("▶ 播放")
        self._lyric_list.set_playhead(0.0); self._update_time_label()

    def _on_play_tick(self):
        try:
            if not self._player.is_playing(): self._play_timer.stop(); self._play_btn.setText("▶ 播放"); return
            self._lyric_list.set_playhead(self._player.get_pos())
            self._update_time_label()
        except Exception: self._play_timer.stop(); self._play_btn.setText("▶ 播放")

    def _on_space_pressed(self):
        if self._player.is_playing() or self._player.is_paused(): self._mark_current_time()
        else: self._toggle_play()

    def _mark_current_time(self):
        if not self._lyrics: return
        pos = self._player.get_pos()
        idx = self._lyric_list._selected_index
        if idx < 0: idx = self._lyric_list.get_current_index()
        if idx < 0 or idx >= len(self._lyrics): return
        old_time = self._lyrics[idx].get("time", 0.0)
        self._lyrics[idx]["time"] = round(pos, 3)
        self._shift_words_in_line(idx, pos - old_time)
        self._lyric_list.set_lyrics(self._lyrics, self._word_lyrics, self._line_words)
        self._lyric_list.select_lyric(idx)
        self._time_spin.setValue(pos)
        self._align_status.setText(f"✅ 已标记: [{idx+1}] {self._lyrics[idx].get('text','')[:20]} → {pos:.2f}s")
        self._align_status.setStyleSheet("color:#a6e3a1;font-size:12px")

    # ── 自动对准 ──

    def _request_auto_align(self):
        if not self._audio_path or not self._lyrics: return
        self._auto_align_btn.setEnabled(False); self._auto_align_btn.setText("⏳ 对准中...")
        self._align_status.setText("")
        self.auto_align_requested.emit(self._audio_path, list(self._lyrics))

    def on_auto_align_result(self, aligned_lyrics):
        """接收对准结果。只平移行时间+对应逐词，不改变行文本和词归属。"""
        old_lyrics = self._lyrics
        self._lyrics = aligned_lyrics

        # 每行逐词平移：delta = 新行时间 - 旧行时间
        if self._line_words and len(aligned_lyrics) == len(old_lyrics):
            for i in range(len(aligned_lyrics)):
                delta = aligned_lyrics[i].get("time", 0.0) - old_lyrics[i].get("time", 0.0)
                if abs(delta) < 0.001: continue
                for w in self._line_words[i]:
                    w["start"] = round(w["start"] + delta, 3)
                    w["end"] = round(w["end"] + delta, 3)
            # 更新 _word_lyrics 为展平列表
            self._word_lyrics = [w for wl in self._line_words for w in wl]

        self._lyric_list.set_lyrics(self._lyrics, self._word_lyrics, self._line_words)
        self._auto_align_btn.setEnabled(True); self._auto_align_btn.setText("🎯 节拍自动对准")
        self._align_status.setText("✅ 对准完成, 播放 + Space 微调")
        self._align_status.setStyleSheet("color:#a6e3a1;font-size:12px")

    # ── 微调 ──

    def _on_lyric_selected(self, index):
        if 0 <= index < len(self._lyrics):
            t = self._lyrics[index].get("time", 0.0)
            self._selected_label.setText(f"[{index+1}] {self._lyrics[index].get('text','')[:25]}")
            self._time_spin.blockSignals(True); self._time_spin.setValue(t); self._time_spin.blockSignals(False)

    def _on_double_click(self, sec):
        was = self._player.is_playing() or self._player.is_paused()
        self._player.seek(sec); self._lyric_list.set_playhead(sec); self._update_time_label(sec)
        if was and not self._player.is_playing():
            self._player.play_from(sec); self._play_timer.start(); self._play_btn.setText("⏸ 暂停")
        self._align_status.setText(f"跳转到 {sec:.2f}s"); self._align_status.setStyleSheet("color:#a6adc8;font-size:12px")

    def _on_spin_changed(self, value):
        idx = self._lyric_list._selected_index
        if 0 <= idx < len(self._lyrics):
            old = self._lyrics[idx].get("time", 0.0)
            self._lyrics[idx]["time"] = value
            self._shift_words_in_line(idx, value - old)
            self._lyric_list.set_lyrics(self._lyrics, self._word_lyrics, self._line_words)
            self._lyric_list.select_lyric(idx)

    def _nudge(self, delta):
        idx = self._lyric_list._selected_index
        if 0 <= idx < len(self._lyrics):
            old = self._lyrics[idx].get("time", 0.0)
            new = max(0.0, old + delta)
            self._lyrics[idx]["time"] = round(new, 3)
            self._shift_words_in_line(idx, new - old)
            self._lyric_list.set_lyrics(self._lyrics, self._word_lyrics, self._line_words)
            self._lyric_list.select_lyric(idx)
            self._time_spin.setValue(new); self._player.seek(new)

    def _shift_words_in_line(self, line_idx, delta):
        """平移指定行的所有逐词时间"""
        if abs(delta) < 0.001 or line_idx >= len(self._line_words):
            return
        for w in self._line_words[line_idx]:
            w["start"] = round(w["start"] + delta, 3)
            w["end"] = round(w["end"] + delta, 3)

    # ── 应用/取消 ──

    def _apply(self):
        self._stop_playback()
        self._original_lyrics = [dict(l) for l in self._lyrics]
        self.alignment_applied.emit([dict(l) for l in self._lyrics])

    def _cancel(self):
        self._stop_playback()
        self._lyrics = [dict(l) for l in self._original_lyrics]
        self._line_words = self._build_line_words(self._lyrics, self._word_lyrics)
        self._lyric_list.set_lyrics(self._lyrics, self._word_lyrics, self._line_words)
        self._align_status.setText("已取消"); self._align_status.setStyleSheet("color:#fab387;font-size:12px")

    def _update_time_label(self, pos_sec=None):
        if pos_sec is None: pos_sec = self._player.get_pos()
        dur = self._player.get_duration()
        self._time_label.setText(f"{int(pos_sec)//60}:{int(pos_sec)%60:02d} / {int(dur)//60}:{int(dur)%60:02d}")

    def cleanup(self):
        self._play_timer.stop(); self._player.close()
