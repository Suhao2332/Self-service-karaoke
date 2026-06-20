"""
主窗口UI模块 v2 — 双行堆叠歌词 + 视频帧预览 + 像素级位置控制
"""
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QTextEdit,
    QProgressBar, QMessageBox, QGroupBox,
    QFormLayout, QDoubleSpinBox, QInputDialog, QFrame,
    QSplitter, QDialog, QCheckBox, QDialogButtonBox,
    QTabWidget, QFontComboBox, QSpinBox, QColorDialog,
    QSlider, QGridLayout, QComboBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QPixmap, QFontInfo
from typing import Optional
import os
import sys
import tempfile

from utils.ffmpeg_helper import check_ffmpeg


STYLE_DISABLED = """
    QPushButton { background-color: #e0e0e0; color: #999; border: 1px solid #ccc; padding: 10px 20px; border-radius: 6px; font-size: 14px; }
"""
STYLE_ACTIVE = """
    QPushButton { background-color: #4a90d9; color: white; border: none; padding: 10px 20px; border-radius: 6px; font-size: 14px; font-weight: bold; }
    QPushButton:hover { background-color: #357abd; }
"""
STYLE_DONE = """
    QPushButton { background-color: #27ae60; color: white; border: none; padding: 10px 20px; border-radius: 6px; font-size: 14px; }
"""
STYLE_COLOR_BTN = """
    QPushButton { border: 2px solid #ccc; border-radius: 4px; min-width: 36px; min-height: 24px; max-width: 48px; }
    QPushButton:hover { border-color: #4a90d9; }
"""


class WorkerThread(QThread):
    """工作线程"""
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, target, args=()):
        super().__init__()
        self.target = target
        self.args = args

    def run(self):
        try:
            result = self.target(*self.args)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class StepIndicator(QWidget):
    """步骤指示器"""
    def __init__(self, steps: list[str], parent=None):
        super().__init__(parent)
        self.steps = steps
        self.current = 0
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.labels = []
        for i, text in enumerate(self.steps):
            if i > 0:
                arrow = QLabel("  →  ")
                arrow.setStyleSheet("color: #aaa; font-size: 16px;")
                layout.addWidget(arrow)
            label = QLabel(f"{i+1}. {text}")
            label.setStyleSheet("color: #999; font-size: 13px; padding: 4px 8px; border-radius: 4px;")
            layout.addWidget(label)
            self.labels.append(label)
        self._update_style()

    def set_step(self, index: int):
        self.current = index
        self._update_style()

    def _update_style(self):
        for i, label in enumerate(self.labels):
            if i < self.current:
                label.setStyleSheet("color: #27ae60; font-size: 13px; padding: 4px 8px; border-radius: 4px; font-weight: bold;")
            elif i == self.current:
                label.setStyleSheet("color: #2c3e50; font-size: 13px; padding: 4px 8px; border-radius: 4px; font-weight: bold; background-color: #ebf5fb; border: 1px solid #4a90d9;")
            else:
                label.setStyleSheet("color: #bbb; font-size: 13px; padding: 4px 8px; border-radius: 4px;")


class KaraokePreviewWidget(QFrame):
    """预览组件 — 固定480×270，视频帧 + QLabel歌词叠加"""

    FIXED_W = 480
    FIXED_H = 270

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("karaokePreview")
        self.setFixedSize(self.FIXED_W, self.FIXED_H)
        self.setStyleSheet(
            "#karaokePreview { background-color: #111; border: 1px solid #333; border-radius: 8px; }"
        )

        self._bg_pixmap: Optional[QPixmap] = None
        self._cur_plain = "这是当前歌词句"
        self._next_plain = "下一句歌词预览"
        self._font_name = "Microsoft YaHei"
        self._font_size = 56
        self._next_scale = 0.7
        self._primary = QColor(255, 255, 255)
        self._secondary = QColor(0, 255, 0)
        self._outline = QColor(0, 0, 0)
        self._next_primary = QColor(255, 255, 255, 140)
        self._next_secondary = QColor(0, 255, 0, 140)
        self._next_outline = QColor(0, 0, 0, 140)
        self._next_alpha = 140
        self._current_left_ratio = 0.05
        self._current_bottom_ratio = 0.12
        self._next_right_ratio = 0.05
        self._next_bottom_ratio = 0.05

        # 底层: 视频帧（压缩到组件大小）
        self._bg_label = QLabel(self)
        self._bg_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._bg_label.setStyleSheet("background: transparent;")
        self._bg_label.setGeometry(0, 0, self.FIXED_W, self.FIXED_H)

        # 顶层: 当前歌词（左锚定）
        self._cur_label = QLabel("这是当前歌词句", self)
        self._cur_label.setStyleSheet("background: transparent;")
        self._cur_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)

        # 顶层: 下一句歌词（右锚定）
        self._next_label = QLabel("下一句歌词预览", self)
        self._next_label.setStyleSheet("background: transparent;")
        self._next_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)

        self._rebuild_labels()

    def set_background(self, pixmap: Optional[QPixmap], video_w: int = 0, video_h: int = 0):
        self._bg_pixmap = pixmap
        if pixmap and not pixmap.isNull():
            scaled = pixmap.scaled(
                self.FIXED_W, self.FIXED_H,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self._bg_label.setPixmap(scaled)
        self._reposition()

    def set_style(self, font_name: str, font_size: int,
                  primary: QColor, secondary: QColor, outline: QColor,
                  next_alpha: int = 140, next_scale: float = 0.7,
                  current_left_ratio: float = 0.05, current_bottom_ratio: float = 0.12,
                  next_right_ratio: float = 0.05, next_bottom_ratio: float = 0.05,
                  next_primary: QColor = None,
                  next_secondary: QColor = None,
                  next_outline: QColor = None):
        self._font_name = font_name
        self._font_size = font_size
        self._primary = QColor(primary)
        self._secondary = QColor(secondary)
        self._outline = QColor(outline)
        self._next_alpha = next_alpha
        self._next_scale = next_scale
        self._current_left_ratio = current_left_ratio
        self._current_bottom_ratio = current_bottom_ratio
        self._next_right_ratio = next_right_ratio
        self._next_bottom_ratio = next_bottom_ratio
        if next_primary is not None:
            self._next_primary = QColor(next_primary)
        if next_secondary is not None:
            self._next_secondary = QColor(next_secondary)
        if next_outline is not None:
            self._next_outline = QColor(next_outline)
        self._rebuild_labels()

    def set_preview_text(self, current: str, next_line: str):
        self._cur_plain = current or "这是当前歌词句"
        self._next_plain = next_line or "下一句歌词预览"
        self._rebuild_labels()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition()

    def _rebuild_labels(self):
        self._cur_label.setTextFormat(Qt.TextFormat.PlainText)
        self._cur_label.setText(self._cur_plain)
        self._next_label.setTextFormat(Qt.TextFormat.PlainText)
        self._next_label.setText(self._next_plain)
        self._reposition()

    def _reposition(self):
        """基于边缘比例重新定位歌词标签"""
        pw = self.width()
        ph = self.height()

        # 视频帧始终填满组件
        self._bg_label.setGeometry(0, 0, pw, ph)
        if self._bg_pixmap and not self._bg_pixmap.isNull():
            pm = self._bg_pixmap.scaled(
                pw, ph, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self._bg_label.setPixmap(pm)

        # 字号缩放：ASS PlayRes 1080 → 预览逻辑尺寸 270px，用 px 避免 DPI 二次缩放
        cur_px = max(int(self._font_size * self.FIXED_H / 1080), 1)
        next_px = max(int(cur_px * self._next_scale), 1)

        # 当前歌词：左边缘锚定
        self._cur_label.setStyleSheet(
            f"font-family: '{self._font_name}'; font-size: {cur_px}px; "
            f"font-weight: bold; color: {self._secondary.name()}; "
            f"background: transparent;"
        )
        self._cur_label.adjustSize()
        cw = self._cur_label.sizeHint().width()
        ch = self._cur_label.sizeHint().height()
        cur_x = int(self._current_left_ratio * pw)
        cur_y = int(ph * (1 - self._current_bottom_ratio))
        self._cur_label.setGeometry(cur_x, cur_y - ch, cw, ch)

        # 下一句歌词：右边缘锚定
        npr, npg, npb = self._next_primary.red(), self._next_primary.green(), self._next_primary.blue()
        npa = self._next_primary.alpha() / 255.0
        self._next_label.setStyleSheet(
            f"font-family: '{self._font_name}'; font-size: {next_px}px; "
            f"color: rgba({npr},{npg},{npb},{npa:.2f}); background: transparent;"
        )
        self._next_label.adjustSize()
        nw = self._next_label.sizeHint().width()
        nh = self._next_label.sizeHint().height()
        next_x = int(pw * (1 - self._next_right_ratio))
        next_y = int(ph * (1 - self._next_bottom_ratio))
        self._next_label.setGeometry(next_x - nw, next_y - nh, nw, nh)


class MainWindow(QMainWindow):
    """主窗口 v2"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("MV卡拉OK制作器")
        self.setMinimumSize(1200, 720)
        self.resize(1200, 720)
        self.setStyleSheet("""
            QMainWindow { background-color: #f5f6fa; }
            QGroupBox { font-weight: bold; border: 1px solid #ddd; border-radius: 8px; margin-top: 12px; padding-top: 16px; background: white; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }
            QTextEdit { border: 1px solid #ddd; border-radius: 4px; background: #fafafa; }
            QProgressBar { border: none; border-radius: 4px; background: #e0e0e0; text-align: center; height: 20px; }
            QProgressBar::chunk { background: #4a90d9; border-radius: 4px; }
            QTabWidget::pane { border: 1px solid #ddd; border-radius: 4px; background: white; }
            QTabBar::tab { padding: 6px 14px; margin-right: 2px; }
            QTabBar::tab:selected { background: white; border-bottom: 2px solid #4a90d9; font-weight: bold; }
        """)

        self.video_path = ""
        self.audio_path = ""
        self.output_dir = ""
        self.song_info = None
        self.lyrics_data = None
        self.karaoke_renderer = None
        self.lyrics_type_prefs = None
        self._preview_frame_path: Optional[str] = None

        # 配置文件（exe 同目录）
        import json as _json
        if getattr(sys, 'frozen', False):
            self._config_dir = os.path.dirname(sys.executable)
        else:
            self._config_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._config_path = os.path.join(self._config_dir, "config.json")
        self._config = self._load_config()

        from core.karaoke_renderer import KaraokeStyleConfig
        self.style_config = KaraokeStyleConfig()

        self._init_ui()
        self._check_ffmpeg()

    # ── 配置读写 ──

    def _load_config(self):
        try:
            if os.path.exists(self._config_path):
                with open(self._config_path, "r", encoding="utf-8") as f:
                    import json
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _save_config(self):
        try:
            os.makedirs(self._config_dir, exist_ok=True)
            with open(self._config_path, "w", encoding="utf-8") as f:
                import json
                json.dump(self._config, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _check_ffmpeg(self):
        # 如果配置中已记录"无 FFmpeg 已提示"，不再弹窗
        if self._config.get("ffmpeg_missing_acknowledged"):
            if not check_ffmpeg():
                self._log("⚠️ FFmpeg未安装（已提示过），音视频功能不可用")
            return

        if not check_ffmpeg():
            btn = QMessageBox.critical(
                self, "环境检查 — FFmpeg 未安装",
                "未检测到 FFmpeg，音视频处理功能将不可用。\n\n"
                "下载地址：https://ffmpeg.org/download.html\n"
                "（下载后请将 ffmpeg.exe 所在目录添加到系统 PATH）\n\n"
                "安装完成后重启本软件即可。",
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Ignore
            )
            self._config["ffmpeg_missing_acknowledged"] = True
            self._save_config()
            self._log("⚠️ FFmpeg未安装 — 音视频功能不可用")

    # ═══════════════════════════════════════════════════════════════
    # UI 构建
    # ═══════════════════════════════════════════════════════════════

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(14, 10, 14, 10)

        # 标题
        title = QLabel("🎤 MV卡拉OK制作器")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #2c3e50;")
        main_layout.addWidget(title)

        # 步骤
        self.step_indicator = StepIndicator(["选择视频", "提取音频", "输入歌曲", "获取歌词", "渲染完成"])
        main_layout.addWidget(self.step_indicator)

        # 主分割器
        self.content_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.content_splitter)

        # ── 左侧 ──
        left = QWidget()
        left.setMinimumWidth(300)
        left.setMaximumWidth(440)
        lp = QVBoxLayout(left)
        lp.setContentsMargins(0, 0, 4, 0)
        lp.setSpacing(6)
        self.content_splitter.addWidget(left)

        # 视频
        fb = QGroupBox("📁 视频文件")
        fl = QVBoxLayout(fb)
        self.file_status = QLabel("请选择一个MV视频文件")
        self.file_status.setStyleSheet("color: #888; font-size: 13px;")
        fl.addWidget(self.file_status)
        sb = QPushButton("📂 选择视频文件")
        sb.setStyleSheet("QPushButton { background: #4a90d9; color: white; border: none; padding: 10px; border-radius: 6px; font-size: 14px; font-weight: bold; }"
                          "QPushButton:hover { background: #357abd; }")
        sb.clicked.connect(self._select_video)
        fl.addWidget(sb)
        self.file_detail = QLabel("")
        self.file_detail.setStyleSheet("color: #555; font-size: 12px;")
        fl.addWidget(self.file_detail)
        lp.addWidget(fb)

        # 歌曲
        sb2 = QGroupBox("🎵 歌曲信息")
        sl = QVBoxLayout(sb2)
        self.song_status = QLabel("提取音频后可输入歌曲信息")
        self.song_status.setStyleSheet("color: #888; font-size: 13px;")
        ir = QHBoxLayout()
        self.input_song_btn = QPushButton("✏️ 输入歌曲信息 (歌曲名 - 歌手名)")
        self.input_song_btn.setStyleSheet(STYLE_DISABLED)
        self.input_song_btn.setEnabled(False)
        self.input_song_btn.clicked.connect(self._input_song_info)
        ir.addWidget(self.input_song_btn)
        sl.addWidget(self.song_status)
        sl.addLayout(ir)
        self.song_display = QLabel("")
        self.song_display.setStyleSheet("color: #2c3e50; font-size: 14px; font-weight: bold; padding: 6px; background: #ebf5fb; border-radius: 4px;")
        self.song_display.setVisible(False)
        sl.addWidget(self.song_display)
        lp.addWidget(sb2)

        # 操作
        ab = QGroupBox("⚙️ 操作")
        al = QVBoxLayout(ab)
        self.fetch_btn = QPushButton("🔍 搜索并获取歌词")
        self.fetch_btn.setStyleSheet(STYLE_DISABLED)
        self.fetch_btn.setEnabled(False)
        self.fetch_btn.clicked.connect(self._fetch_lyrics)
        al.addWidget(self.fetch_btn)
        self.render_btn = QPushButton("🎬 渲染卡拉OK视频")
        self.render_btn.setStyleSheet(STYLE_DISABLED)
        self.render_btn.setEnabled(False)
        self.render_btn.clicked.connect(self._render_karaoke)
        al.addWidget(self.render_btn)
        lp.addWidget(ab)

        # 输出目录
        ob = QGroupBox("📁 输出目录")
        ol = QVBoxLayout(ob)
        or_ = QHBoxLayout()
        self.output_dir_label = QLabel("未选择（点击渲染时将弹出选择）")
        self.output_dir_label.setStyleSheet("color: #888; font-size: 12px; font-style: italic;")
        self.output_dir_label.setWordWrap(True)
        or_.addWidget(self.output_dir_label, 1)
        obtn = QPushButton("📂 选择")
        obtn.setStyleSheet("QPushButton { background: #5d6d7e; color: white; border: none; padding: 6px 12px; border-radius: 4px; }"
                            "QPushButton:hover { background: #4a5568; }")
        obtn.clicked.connect(self._select_output_dir)
        or_.addWidget(obtn)
        ol.addLayout(or_)
        self.save_ass_check = QCheckBox("输出歌词文件 (.ass)")
        self.save_ass_check.setChecked(False)
        self.save_ass_check.setStyleSheet("color: #888; font-size: 12px;")
        ol.addWidget(self.save_ass_check)
        clr = QPushButton("↩ 清除（使用视频目录）")
        clr.setStyleSheet("QPushButton { background: none; color: #888; border: 1px solid #ccc; padding: 4px 10px; border-radius: 4px; font-size: 11px; }"
                           "QPushButton:hover { color: #e74c3c; border-color: #e74c3c; }")
        clr.clicked.connect(self._clear_output_dir)
        ol.addWidget(clr)
        lp.addWidget(ob)

        # ── 右侧标签页 ──
        right = QWidget()
        rp = QVBoxLayout(right)
        rp.setContentsMargins(4, 0, 0, 0)
        rp.setSpacing(0)
        self.content_splitter.addWidget(right)
        self.content_splitter.setSizes([380, 760])

        self.right_tabs = QTabWidget()
        rp.addWidget(self.right_tabs)

        # == 标签1: 日志 ==
        lt = QWidget()
        ll = QVBoxLayout(lt)
        ll.setContentsMargins(4, 4, 4, 4)
        ll.setSpacing(6)
        lb = QGroupBox("📋 处理日志")
        li = QVBoxLayout(lb)
        self.status_text = QTextEdit()
        self.status_text.setReadOnly(True)
        self.status_text.setMinimumHeight(160)
        li.addWidget(self.status_text)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        li.addWidget(self.progress_bar)
        ll.addWidget(lb)
        ll.addStretch()
        self.right_tabs.addTab(lt, "📋 处理日志")

        # == 标签2: 歌词样式 ==
        self._build_style_tab()

        # == 标签3: 节拍对准 ==
        self._build_beat_alignment_tab()

        # 底部状态
        self.status_label = QLabel("就绪 — 选择一个视频文件开始")
        self.status_label.setStyleSheet("color: #888; font-size: 12px; padding: 4px 0; border-top: 1px solid #eee;")
        main_layout.addWidget(self.status_label)

        self._update_color_buttons()
        self._refresh_preview()

    def _build_style_tab(self):
        """构建歌词样式标签页"""
        from PyQt6.QtWidgets import QScrollArea

        st = QWidget()
        sl = QVBoxLayout(st)
        sl.setContentsMargins(4, 4, 4, 4)
        sl.setSpacing(6)

        # 预览区
        pb = QGroupBox("👁️ 实时预览")
        pi = QVBoxLayout(pb)
        pi.setContentsMargins(4, 4, 4, 4)
        self.preview_widget = KaraokePreviewWidget()
        pi.addWidget(self.preview_widget)
        sl.addWidget(pb)

        # 样式设置（可滚动）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        sf = QGroupBox("🎨 歌词样式设置")
        gf = QGridLayout(sf)
        gf.setSpacing(6)

        row = 0
        # 字体
        gf.addWidget(QLabel("字体:"), row, 0)
        self.font_combo = QFontComboBox()
        self.font_combo.setCurrentFont(QFont("Microsoft YaHei"))
        self.font_combo.currentFontChanged.connect(self._on_style_changed)
        gf.addWidget(self.font_combo, row, 1); row += 1

        # 字号 + 粗体斜体
        gf.addWidget(QLabel("当前句字号:"), row, 0)
        sr = QHBoxLayout()
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(12, 200)
        self.font_size_spin.setValue(56)
        self.font_size_spin.setSuffix(" pt")
        self.font_size_spin.valueChanged.connect(self._on_style_changed)
        sr.addWidget(self.font_size_spin)
        self.bold_check = QCheckBox("粗体")
        self.bold_check.setChecked(True)
        self.bold_check.stateChanged.connect(self._on_style_changed)
        sr.addWidget(self.bold_check)
        self.italic_check = QCheckBox("斜体")
        self.italic_check.stateChanged.connect(self._on_style_changed)
        sr.addWidget(self.italic_check)
        sr.addStretch()
        gf.addLayout(sr, row, 1); row += 1

        # 下一句字号比例
        gf.addWidget(QLabel("下一句字号比例:"), row, 0)
        nsr = QHBoxLayout()
        self.next_scale_spin = QDoubleSpinBox()
        self.next_scale_spin.setRange(0.3, 1.0)
        self.next_scale_spin.setSingleStep(0.05)
        self.next_scale_spin.setValue(0.7)
        self.next_scale_spin.valueChanged.connect(self._on_style_changed)
        nsr.addWidget(self.next_scale_spin)
        nsr.addWidget(QLabel("(× 当前句字号)"))
        nsr.addStretch()
        gf.addLayout(nsr, row, 1); row += 1

        # 颜色
        def _color_row(label, attr, row_idx):
            gf.addWidget(QLabel(label + ":"), row_idx, 0)
            cr = QHBoxLayout()
            btn = QPushButton()
            btn.setStyleSheet(STYLE_COLOR_BTN)
            btn.clicked.connect(attr)
            cr.addWidget(btn)
            lbl = QLabel("#FFF")
            cr.addWidget(lbl)
            cr.addStretch()
            gf.addLayout(cr, row_idx, 1)
            return btn, lbl

        self.primary_color_btn, self.primary_color_label = \
            _color_row("已唱颜色", self._pick_primary_color, row); row += 1
        self.secondary_color_btn, self.secondary_color_label = \
            _color_row("未唱颜色", self._pick_secondary_color, row); row += 1
        self.outline_color_btn, self.outline_color_label = \
            _color_row("轮廓颜色", self._pick_outline_color, row); row += 1

        # 预览行独立颜色（下一句预览专用）
        gf.addWidget(QLabel(""), row, 0)
        gf.addWidget(QLabel("<b>预览行颜色</b> (下一句预览样式)"), row, 1)
        row += 1
        self.next_primary_color_btn, self.next_primary_color_label = \
            _color_row("  预览已唱色", self._pick_next_primary_color, row); row += 1
        self.next_secondary_color_btn, self.next_secondary_color_label = \
            _color_row("  预览未唱色", self._pick_next_secondary_color, row); row += 1
        self.next_outline_color_btn, self.next_outline_color_label = \
            _color_row("  预览轮廓色", self._pick_next_outline_color, row); row += 1

        # 轮廓宽度
        gf.addWidget(QLabel("轮廓宽度:"), row, 0)
        owr = QHBoxLayout()
        self.outline_width_spin = QDoubleSpinBox()
        self.outline_width_spin.setRange(0.0, 10.0)
        self.outline_width_spin.setSingleStep(0.5)
        self.outline_width_spin.setValue(2.5)
        self.outline_width_spin.valueChanged.connect(self._on_style_changed)
        owr.addWidget(self.outline_width_spin)
        owr.addStretch()
        gf.addLayout(owr, row, 1); row += 1

        # 下一句透明度
        gf.addWidget(QLabel("下一句透明度:"), row, 0)
        nar = QHBoxLayout()
        self.next_alpha_slider = QSlider(Qt.Orientation.Horizontal)
        self.next_alpha_slider.setRange(20, 255)
        self.next_alpha_slider.setValue(140)
        self.next_alpha_slider.valueChanged.connect(self._on_style_changed)
        nar.addWidget(self.next_alpha_slider)
        self.next_alpha_label = QLabel("140")
        self.next_alpha_label.setFixedWidth(32)
        self.next_alpha_slider.valueChanged.connect(
            lambda v: self.next_alpha_label.setText(str(v)))
        nar.addWidget(self.next_alpha_label)
        gf.addLayout(nar, row, 1); row += 1

        # ── 位置控制（边缘比例 %，0=贴边，100=对面）──
        gf.addWidget(QLabel(""), row, 0)
        lh = QLabel("<b>位置偏移</b> (% 窗口边缘比例)")
        lh.setStyleSheet("margin-top:6px;")
        gf.addWidget(lh, row, 1)
        row += 1

        def _ratio_row(label, default_pct, row_idx):
            gf.addWidget(QLabel(label + ":"), row_idx, 0)
            sr2 = QHBoxLayout()
            sld = QSlider(Qt.Orientation.Horizontal)
            sld.setRange(0, 50)
            sld.setValue(default_pct)
            sld.setTickPosition(QSlider.TickPosition.TicksBelow)
            sld.setTickInterval(5)
            sld.valueChanged.connect(self._on_style_changed)
            sr2.addWidget(sld, 1)
            val = QLabel(f"{default_pct}%")
            val.setFixedWidth(45)
            val.setStyleSheet("font-size:11px;")
            sld.valueChanged.connect(lambda v, lbl=val: lbl.setText(f"{v}%"))
            sr2.addWidget(val)
            gf.addLayout(sr2, row_idx, 1)
            return sld

        self.cur_left_slider = _ratio_row("当前句左边缘距左侧", 5, row); row += 1
        self.cur_bottom_slider = _ratio_row("当前句底部距底部", 12, row); row += 1
        self.next_right_slider = _ratio_row("下一句右边缘距右侧", 5, row); row += 1
        self.next_bottom_slider = _ratio_row("下一句底部距底部", 5, row); row += 1

        sl.addWidget(sf)

        # 重置按钮
        rb = QPushButton("🔄 恢复默认样式")
        rb.setStyleSheet("QPushButton { background: none; color: #888; border: 1px solid #ccc; padding: 6px 14px; border-radius: 4px; }"
                          "QPushButton:hover { color: #e67e22; border-color: #e67e22; }")
        rb.clicked.connect(self._reset_style)

        # 用wrapper包裹 sf(grid) + 重置按钮，放入scroll
        wrapper = QWidget()
        wl = QVBoxLayout(wrapper)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(6)
        wl.addWidget(sf)
        wl.addWidget(rb)
        wl.addStretch()

        scroll.setWidget(wrapper)
        sl.addWidget(scroll, 1)  # stretch=1 占据剩余空间

        self.right_tabs.addTab(st, "🎨 歌词样式")

    # ═══════════════════════════════════════════════════════════════
    # 节拍对准标签页
    # ═══════════════════════════════════════════════════════════════

    def _build_beat_alignment_tab(self):
        """构建节拍对准标签页（标签3）"""
        from ui.beat_alignment_tab import BeatAlignmentTab

        self.beat_alignment_tab = BeatAlignmentTab()
        self.right_tabs.addTab(self.beat_alignment_tab, "🎵 节拍对准")

        # ── 信号连接 ──
        # 自动对准请求 → 执行 librosa 节拍检测 + TimelineAligner
        self.beat_alignment_tab.auto_align_requested.connect(
            self._on_auto_align_requested
        )
        # 对准结果应用 → 更新 lyrics_data
        self.beat_alignment_tab.alignment_applied.connect(
            self._on_alignment_applied
        )

    def _on_auto_align_requested(self, audio_path: str, lyrics: list):
        """响应节拍对准标签页的自动对准请求"""
        from core.timeline_aligner import TimelineAligner

        try:
            aligned = self._detect_beats_and_align(audio_path, lyrics)
            self.beat_alignment_tab.on_auto_align_result(aligned)
        except Exception as e:
            self._log(f"自动对准失败: {e}")
            self.beat_alignment_tab._align_status.setText(f"⚠️ {e}")
            self.beat_alignment_tab._align_status.setStyleSheet("color: #f38ba8;")
            self.beat_alignment_tab._auto_align_btn.setEnabled(True)
            self.beat_alignment_tab._auto_align_btn.setText("🎯 节拍自动对准")

    def _on_alignment_applied(self, aligned_lyrics: list):
        """用户确认对准结果，更新主窗口歌词数据"""
        if self.lyrics_data and "lrc" in self.lyrics_data:
            self.lyrics_data["lrc"] = aligned_lyrics
            self._log(f"✅ 节拍对准结果已应用 ({len(aligned_lyrics)}行)")
            self._refresh_preview()
            # 更新预览歌词
            if len(aligned_lyrics) >= 2:
                self.preview_widget.set_preview_text(
                    aligned_lyrics[0].get("text", ""),
                    aligned_lyrics[1].get("text", "")
                )
            elif aligned_lyrics:
                self.preview_widget.set_preview_text(
                    aligned_lyrics[0].get("text", ""), "(无下一句)"
                )

    # ═══════════════════════════════════════════════════════════════
    # 样式控制
    # ═══════════════════════════════════════════════════════════════

    def _on_style_changed(self):
        self._refresh_preview()

    def _pick_primary_color(self):
        c = QColorDialog.getColor(
            self._qcolor_from_ass(self.style_config.primary_color), self, "选择已唱颜色")
        if c.isValid():
            self.style_config.primary_color = self._qcolor_to_ass(c)
            self._auto_sync_preview_colors()
            self._update_color_buttons()
            self._refresh_preview()

    def _pick_secondary_color(self):
        c = QColorDialog.getColor(
            self._qcolor_from_ass(self.style_config.secondary_color), self, "选择未唱颜色")
        if c.isValid():
            self.style_config.secondary_color = self._qcolor_to_ass(c)
            self._auto_sync_preview_colors()
            self._update_color_buttons()
            self._refresh_preview()

    def _pick_outline_color(self):
        c = QColorDialog.getColor(
            self._qcolor_from_ass(self.style_config.outline_color), self, "选择轮廓颜色")
        if c.isValid():
            self.style_config.outline_color = self._qcolor_to_ass(c)
            self._auto_sync_preview_colors()
            self._update_color_buttons()
            self._refresh_preview()

    def _auto_sync_preview_colors(self):
        """修改主颜色时自动同步预览颜色（主色 + next_alpha 半透明）"""
        alpha = self.style_config.next_alpha
        for main_attr, next_attr in [
            ("primary_color", "next_primary_color"),
            ("secondary_color", "next_secondary_color"),
            ("outline_color", "next_outline_color"),
        ]:
            qc = self._qcolor_from_ass(getattr(self.style_config, main_attr))
            qc.setAlpha(255 - alpha)
            setattr(self.style_config, next_attr, self._qcolor_to_ass(qc))

    def _pick_next_primary_color(self):
        c = QColorDialog.getColor(
            self._qcolor_from_ass(self.style_config.next_primary_color), self, "选择预览已唱颜色")
        if c.isValid():
            self.style_config.next_primary_color = self._qcolor_to_ass(c)
            self._update_color_buttons()
            self._refresh_preview()

    def _pick_next_secondary_color(self):
        c = QColorDialog.getColor(
            self._qcolor_from_ass(self.style_config.next_secondary_color), self, "选择预览未唱颜色")
        if c.isValid():
            self.style_config.next_secondary_color = self._qcolor_to_ass(c)
            self._update_color_buttons()
            self._refresh_preview()

    def _pick_next_outline_color(self):
        c = QColorDialog.getColor(
            self._qcolor_from_ass(self.style_config.next_outline_color), self, "选择预览轮廓颜色")
        if c.isValid():
            self.style_config.next_outline_color = self._qcolor_to_ass(c)
            self._update_color_buttons()
            self._refresh_preview()

    def _update_color_buttons(self):
        p = self._qcolor_from_ass(self.style_config.primary_color)
        s = self._qcolor_from_ass(self.style_config.secondary_color)
        o = self._qcolor_from_ass(self.style_config.outline_color)
        self.primary_color_btn.setStyleSheet(STYLE_COLOR_BTN + f" background-color: {p.name()};")
        self.primary_color_label.setText(p.name().upper())
        self.secondary_color_btn.setStyleSheet(STYLE_COLOR_BTN + f" background-color: {s.name()};")
        self.secondary_color_label.setText(s.name().upper())
        self.outline_color_btn.setStyleSheet(STYLE_COLOR_BTN + f" background-color: {o.name()};")
        self.outline_color_label.setText(o.name().upper())
        np = self._qcolor_from_ass(self.style_config.next_primary_color)
        ns = self._qcolor_from_ass(self.style_config.next_secondary_color)
        no = self._qcolor_from_ass(self.style_config.next_outline_color)
        self.next_primary_color_btn.setStyleSheet(STYLE_COLOR_BTN + f" background-color: {np.name()};")
        self.next_primary_color_label.setText(np.name().upper())
        self.next_secondary_color_btn.setStyleSheet(STYLE_COLOR_BTN + f" background-color: {ns.name()};")
        self.next_secondary_color_label.setText(ns.name().upper())
        self.next_outline_color_btn.setStyleSheet(STYLE_COLOR_BTN + f" background-color: {no.name()};")
        self.next_outline_color_label.setText(no.name().upper())

    def _refresh_preview(self):
        """同步样式到预览"""
        self.style_config.font_name = self.font_combo.currentFont().family()
        self.style_config.font_size = self.font_size_spin.value()
        self.style_config.bold = self.bold_check.isChecked()
        self.style_config.italic = self.italic_check.isChecked()
        self.style_config.outline_width = self.outline_width_spin.value()
        self.style_config.next_alpha = self.next_alpha_slider.value()
        self._auto_sync_preview_colors()
        self.style_config.next_font_scale = self.next_scale_spin.value()
        self.style_config.current_left_ratio = self.cur_left_slider.value() / 100.0
        self.style_config.current_bottom_ratio = self.cur_bottom_slider.value() / 100.0
        self.style_config.next_right_ratio = self.next_right_slider.value() / 100.0
        self.style_config.next_bottom_ratio = self.next_bottom_slider.value() / 100.0

        primary = self._qcolor_from_ass(self.style_config.primary_color)
        secondary = self._qcolor_from_ass(self.style_config.secondary_color)
        outline = self._qcolor_from_ass(self.style_config.outline_color)
        next_primary = self._qcolor_from_ass(self.style_config.next_primary_color)
        next_secondary = self._qcolor_from_ass(self.style_config.next_secondary_color)
        next_outline = self._qcolor_from_ass(self.style_config.next_outline_color)

        self.preview_widget.set_style(
            self.style_config.font_name,
            self.style_config.font_size,
            primary, secondary, outline,
            self.style_config.next_alpha,
            self.style_config.next_font_scale,
            self.style_config.current_left_ratio,
            self.style_config.current_bottom_ratio,
            self.style_config.next_right_ratio,
            self.style_config.next_bottom_ratio,
            next_primary, next_secondary, next_outline,
        )

    def _reset_style(self):
        from core.karaoke_renderer import KaraokeStyleConfig
        self.style_config = KaraokeStyleConfig()
        self.font_combo.setCurrentFont(QFont(self.style_config.font_name))
        self.font_size_spin.setValue(self.style_config.font_size)
        self.bold_check.setChecked(self.style_config.bold)
        self.italic_check.setChecked(self.style_config.italic)
        self.outline_width_spin.setValue(self.style_config.outline_width)
        self.next_alpha_slider.setValue(self.style_config.next_alpha)
        self.next_scale_spin.setValue(self.style_config.next_font_scale)
        self.cur_left_slider.setValue(int(self.style_config.current_left_ratio * 100))
        self.cur_bottom_slider.setValue(int(self.style_config.current_bottom_ratio * 100))
        self.next_right_slider.setValue(int(self.style_config.next_right_ratio * 100))
        self.next_bottom_slider.setValue(int(self.style_config.next_bottom_ratio * 100))
        self._update_color_buttons()
        self._refresh_preview()

    @staticmethod
    def _qcolor_to_ass(qc: QColor) -> str:
        return f"&H{255 - qc.alpha():02X}{qc.blue():02X}{qc.green():02X}{qc.red():02X}"

    @staticmethod
    def _qcolor_from_ass(ac: str) -> QColor:
        try:
            if ac.startswith("&H") and len(ac) >= 10:
                h = ac[2:]
                return QColor(int(h[6:8], 16), int(h[4:6], 16),
                              int(h[2:4], 16), 255 - int(h[0:2], 16))
        except (ValueError, IndexError):
            pass
        return QColor(255, 255, 255)

    # ═══════════════════════════════════════════════════════════════
    # 输出目录
    # ═══════════════════════════════════════════════════════════════

    def _select_output_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录", self.output_dir or os.path.expanduser("~"))
        if d:
            self.output_dir = d
            self.output_dir_label.setText(d)
            self.output_dir_label.setStyleSheet("color: #27ae60; font-size: 12px; font-weight: bold;")
            self._log(f"输出目录: {d}")

    def _clear_output_dir(self):
        self.output_dir = ""
        self.output_dir_label.setText("未选择（点击渲染时将弹出选择）")
        self.output_dir_label.setStyleSheet("color: #888; font-size: 12px; font-style: italic;")
        self._log("输出目录已清除")

    # ═══════════════════════════════════════════════════════════════
    # 核心流程
    # ═══════════════════════════════════════════════════════════════

    def _select_video(self):
        fp, _ = QFileDialog.getOpenFileName(
            self, "选择MV视频文件", "",
            "视频文件 (*.mp4 *.avi *.mkv *.mov *.flv *.wmv);;所有文件 (*.*)")
        if not fp:
            return
        self.video_path = fp
        fn = os.path.basename(fp)
        fs = os.path.getsize(fp)
        self.file_status.setText(f"✅ 已选择: {fn}")
        self.file_detail.setText(f"大小: {fs/1024/1024:.1f} MB | {fp}")
        self.file_status.setStyleSheet("color: #27ae60; font-size: 13px; font-weight: bold;")
        self._log(f"已选择视频: {fn} ({fs/1024/1024:.1f} MB)")

        # 提取预览帧
        self._extract_preview_frame()
        self._extract_audio()

    def _extract_preview_frame(self):
        """提取视频首帧 + 分辨率用于预览"""
        from core.karaoke_renderer import KaraokeRenderer
        try:
            tmp = os.path.join(tempfile.gettempdir(), "karaoke_preview_frame.png")
            r = KaraokeRenderer()
            ok = r.extract_preview_frame(self.video_path, tmp, 2.0)
            if ok:
                self._preview_frame_path = tmp
                pm = QPixmap(tmp)
                if not pm.isNull():
                    # 获取实际视频分辨率
                    vw, vh = self._get_video_dimensions()
                    self.preview_widget.set_background(pm, vw, vh)
                    self._log("预览帧已提取")
        except Exception as e:
            self._log(f"预览帧提取失败: {e}")

    def _get_video_dimensions(self):
        """获取视频分辨率"""
        import subprocess as sp
        try:
            r = sp.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=width,height",
                 "-of", "csv=p=0", self.video_path],
                capture_output=True, text=True, timeout=15)
            if r.returncode == 0 and r.stdout.strip():
                parts = r.stdout.strip().split(",")
                if len(parts) == 2:
                    return int(parts[0]), int(parts[1])
        except Exception:
            pass
        return 1920, 1080

    def _extract_audio(self):
        self.step_indicator.set_step(1)
        self._set_processing_state(True)
        self._log("正在提取音频...")
        from core.audio_processor import extract_audio
        self.worker = WorkerThread(extract_audio, (self.video_path,))
        self.worker.finished.connect(self._on_audio_extracted)
        self.worker.error.connect(self._on_error)
        self.worker.start()

    def _on_audio_extracted(self, audio_path):
        self.audio_path = audio_path
        self._log(f"✅ 音频提取完成: {os.path.basename(audio_path)}")
        self.step_indicator.set_step(2)
        self.input_song_btn.setStyleSheet(STYLE_ACTIVE)
        self.input_song_btn.setEnabled(True)
        self.song_status.setText("请点击按钮输入歌曲信息 ↓")
        self.song_status.setStyleSheet("color: #2c3e50; font-size: 13px; font-weight: bold;")
        self._set_processing_state(False)

    def closeEvent(self, event):
        """窗口关闭时释放资源"""
        if hasattr(self, 'beat_alignment_tab'):
            self.beat_alignment_tab.cleanup()
        super().closeEvent(event)

    def _input_song_info(self):
        text, ok = QInputDialog.getText(
            self, "输入歌曲信息",
            "请输入 歌曲名 - 歌手名\n（中间用空格-空格分隔）\n\n示例: 青花瓷 - 周杰伦")
        if not ok or not text.strip():
            return
        text = text.strip()
        # 按 " - " 分割
        if " - " in text:
            parts = text.split(" - ", 1)
            title = parts[0].strip()
            artist = parts[1].strip() if len(parts) > 1 else "未知"
        else:
            # 无分隔符时整个当作歌曲名
            title = text
            artist = "未知"
        if not title:
            return
        self._set_song_info(title, artist)

    def _set_song_info(self, title: str, artist: str):
        self.song_info = {"title": title, "artist": artist}
        self.song_display.setText(f"🎵 {title} — {artist}")
        self.song_display.setVisible(True)
        self.song_status.setText("✅ 歌曲信息已设置")
        self.song_status.setStyleSheet("color: #27ae60; font-size: 13px;")
        self._log(f"歌曲信息: {title} — {artist}")
        self.fetch_btn.setStyleSheet(STYLE_ACTIVE)
        self.fetch_btn.setEnabled(True)
        self.step_indicator.set_step(3)

    def _fetch_lyrics(self):
        if not self.song_info:
            QMessageBox.warning(self, "提示", "请先输入歌曲信息")
            return
        self._set_processing_state(True)
        self._log(f"正在搜索歌词: {self.song_info['title']} {self.song_info['artist']}")
        from core.lyrics_fetcher import LyricsFetcher
        self.lyrics_fetcher = LyricsFetcher()
        self.worker = WorkerThread(
            self.lyrics_fetcher.search_all_sources,
            (self.song_info["title"], self.song_info["artist"]))
        self.worker.finished.connect(self._on_search_results)
        self.worker.error.connect(self._on_error)
        self.worker.start()

    def _on_search_results(self, all_results):
        all_songs = []
        for source, songs in all_results.items():
            for s in songs:
                s["_source"] = source
            all_songs.extend(songs)
            if songs:
                self._log(f"  {source}: {len(songs)} 首")
        if not all_songs:
            self._log("❌ 所有来源均未找到")
            QMessageBox.warning(self, "搜索失败", "未找到匹配歌曲")
            self._set_processing_state(False)
            return
        song_list = [f"[{s.get('_source','?')}] {s['title']} — {s['artist']}" for s in all_songs]
        choice, ok = QInputDialog.getItem(self, "选择歌曲", f"找到 {len(all_songs)} 首:", song_list, 0, False)
        if not ok:
            self._set_processing_state(False)
            return
        idx = song_list.index(choice)
        sel = all_songs[idx]
        source = sel.get("_source", "netease")
        self._log(f"已选择: [{source}] {sel['title']} — {sel['artist']}")
        uo, ut, ur = self._show_lyrics_type_dialog(sel["title"], sel["artist"])
        self.lyrics_type_prefs = {"orig": uo, "ts": ut, "roma": ur}
        extra = {}
        if "酷狗" in source or source == "kugou":
            extra = {"hash": sel.get("hash", ""), "album_audio_id": sel.get("album_audio_id", ""),
                     "title": sel["title"], "artist": sel["artist"]}
        elif "QQ" in source or source == "qqmusic":
            extra = {
                "songid": sel.get("songid", ""),
                "title": sel["title"],
                "artist": sel["artist"],
                "album": sel.get("album", ""),
                "duration": sel.get("duration", 0),
            }
        self.worker2 = WorkerThread(
            self.lyrics_fetcher.fetch_lyrics, (sel["id"], source, extra))
        self.worker2.finished.connect(self._on_lyrics_fetched)
        self.worker2.error.connect(self._on_error)
        self.worker2.start()

    def _show_lyrics_type_dialog(self, title, artist):
        dlg = QDialog(self)
        dlg.setWindowTitle("选择歌词类型")
        dlg.setMinimumWidth(320)
        lo = QVBoxLayout(dlg)
        lo.addWidget(QLabel(f"歌曲: {title} — {artist}\n\n请勾选需要的歌词类型:"))
        co = QCheckBox("原文 (Original)"); co.setChecked(True); co.setEnabled(False); lo.addWidget(co)
        ct = QCheckBox("译文 (Translation)"); ct.setChecked(True); lo.addWidget(ct)
        cr = QCheckBox("罗马音 (Romanization)"); cr.setChecked(True); lo.addWidget(cr)
        lo.addWidget(QLabel("提示：如服务器未返回对应数据则无效。"))
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btns.accepted.connect(dlg.accept); lo.addWidget(btns)
        dlg.exec()
        return co.isChecked(), ct.isChecked(), cr.isChecked()

    def _on_lyrics_fetched(self, lyrics_data):
        if not lyrics_data or not lyrics_data.get("lrc"):
            self._log("❌ 歌词获取失败")
            QMessageBox.warning(self, "获取失败", "未获取到歌词数据")
            self._set_processing_state(False)
            return
        self.lyrics_data = lyrics_data
        lc = len(lyrics_data["lrc"])
        wc = len(lyrics_data.get("word_lyrics", []))
        ht = "tlyric" in lyrics_data and lyrics_data["tlyric"]
        hr = "romalrc" in lyrics_data and lyrics_data["romalrc"]
        self._log(f"✅ 歌词获取成功! LRC: {lc}行, 逐词: {wc}个")

        self.status_text.append("--- 歌词预览 (前3行) ---")
        for lrc in lyrics_data["lrc"][:3]:
            self.status_text.append(f"  [{lrc['time']:.1f}s] {lrc['text']}")

        prefs = self.lyrics_type_prefs or {"orig": True, "ts": False, "roma": False}
        ut = prefs.get("ts", False) and ht
        ur = prefs.get("roma", False) and hr
        if ut and ur:
            self._merge_lyrics_three("lrc", "tlyric", "romalrc")
        elif ut:
            self._merge_lyrics("lrc", "tlyric")
        elif ur:
            self._merge_lyrics("lrc", "romalrc")

        lrc_list = self.lyrics_data.get("lrc", [])
        if len(lrc_list) >= 2:
            self.preview_widget.set_preview_text(
                lrc_list[0].get("text", ""), lrc_list[1].get("text", ""))
        elif lrc_list:
            self.preview_widget.set_preview_text(lrc_list[0].get("text", ""), "(无下一句)")

        # 加载数据到节拍对准标签页
        if self.audio_path and lrc_list:
            self.beat_alignment_tab.load_data(
                self.audio_path, lrc_list,
                word_lyrics=self.lyrics_data.get("word_lyrics", []))
            self._log("已加载到节拍对准标签页")

        self.render_btn.setStyleSheet(STYLE_ACTIVE)
        self.render_btn.setEnabled(True)
        self.step_indicator.set_step(4)
        self._set_processing_state(False)

    def _merge_lyrics(self, pk, sk):
        p = self.lyrics_data.get(pk, [])
        s = self.lyrics_data.get(sk, [])
        if not p or not s:
            return
        merged, si = [], 0
        for item in p:
            txt = item["text"]
            while si < len(s) and s[si]["time"] < item["time"]:
                si += 1
            # 在当前位置和前一个位置中找最接近的匹配
            best = None
            best_diff = 999.0
            for cand in (si, si - 1):
                if 0 <= cand < len(s):
                    diff = abs(s[cand]["time"] - item["time"])
                    if diff < 3.0 and diff < best_diff:
                        best = cand
                        best_diff = diff
            if best is not None:
                txt = f"{item['text']}\\N{s[best]['text']}"
            merged.append({"time": item["time"], "text": txt})
        self.lyrics_data["lrc"] = merged

    def _merge_lyrics_three(self, ok, tk, rk):
        o = self.lyrics_data.get(ok, [])
        t = self.lyrics_data.get(tk, [])
        r = self.lyrics_data.get(rk, [])
        if not o:
            return
        merged, ti, ri = [], 0, 0
        for item in o:
            txt = item["text"]
            if t:
                while ti < len(t) and t[ti]["time"] < item["time"]:
                    ti += 1
                best_t = None
                best_td = 999.0
                for cand in (ti, ti - 1):
                    if 0 <= cand < len(t):
                        d = abs(t[cand]["time"] - item["time"])
                        if d < 3.0 and d < best_td:
                            best_t = cand
                            best_td = d
                if best_t is not None:
                    txt += f"\\N{t[best_t]['text']}"
            if r:
                while ri < len(r) and r[ri]["time"] < item["time"]:
                    ri += 1
                best_r = None
                best_rd = 999.0
                for cand in (ri, ri - 1):
                    if 0 <= cand < len(r):
                        d = abs(r[cand]["time"] - item["time"])
                        if d < 3.0 and d < best_rd:
                            best_r = cand
                            best_rd = d
                if best_r is not None:
                    txt += f"\\N{r[best_r]['text']}"
            merged.append({"time": item["time"], "text": txt})
        self.lyrics_data["lrc"] = merged

    def _render_karaoke(self):
        if not self.video_path:
            QMessageBox.warning(self, "提示", "请先选择视频文件")
            return
        self._set_processing_state(True)
        self._log("开始渲染卡拉OK视频...")

        # 始终使用 LRC 行级时间轴（逐词时间轴是单字级别，不适合独立渲染）
        if self.lyrics_data:
            timeline = self.lyrics_data.get("lrc", [])
            self._log(f"使用LRC行时间轴 ({len(timeline)}行)")
        else:
            timeline = []

        if self.audio_path and timeline:
            timeline = self._detect_beats_and_align(self.audio_path, timeline)

        from core.karaoke_renderer import KaraokeRenderer
        self.karaoke_renderer = KaraokeRenderer()

        # 未选择输出目录时弹出文件夹选择
        if not self.output_dir:
            from PyQt6.QtWidgets import QFileDialog
            d = QFileDialog.getExistingDirectory(
                self, "选择输出目录",
                os.path.dirname(os.path.abspath(self.video_path)))
            if not d:
                self._log("已取消渲染：未选择输出目录")
                self._set_processing_state(False)
                return
            self.output_dir = d
            self.output_dir_label.setText(d)
            self.output_dir_label.setStyleSheet(
                "color: #27ae60; font-size: 12px; font-weight: bold;")

        out_dir = self.output_dir
        base = os.path.splitext(os.path.basename(self.video_path))[0]
        output_path = os.path.join(out_dir, f"{base}_karaoke.mp4")
        self._log(f"输出: {output_path}")

        self._sync_style_config()

        self.worker = WorkerThread(
            self.karaoke_renderer.render_karaoke,
            (self.video_path, timeline, output_path, self.style_config.clone()))
        self.worker.finished.connect(self._on_render_finished)
        self.worker.error.connect(self._on_error)
        self.worker.start()

    def _sync_style_config(self):
        self.style_config.font_name = self.font_combo.currentFont().family()
        self.style_config.font_size = self.font_size_spin.value()
        self.style_config.bold = self.bold_check.isChecked()
        self.style_config.italic = self.italic_check.isChecked()
        self.style_config.outline_width = self.outline_width_spin.value()
        self.style_config.next_alpha = self.next_alpha_slider.value()
        self._auto_sync_preview_colors()
        self.style_config.next_font_scale = self.next_scale_spin.value()
        self.style_config.current_left_ratio = self.cur_left_slider.value() / 100.0
        self.style_config.current_bottom_ratio = self.cur_bottom_slider.value() / 100.0
        self.style_config.next_right_ratio = self.next_right_slider.value() / 100.0
        self.style_config.next_bottom_ratio = self.next_bottom_slider.value() / 100.0
        self._log(
            f"歌词样式: {self.style_config.font_name} {self.style_config.font_size}pt "
            f"当前句(L={self.style_config.current_left_ratio:.0%},B={self.style_config.current_bottom_ratio:.0%}) "
            f"下一句(R={self.style_config.next_right_ratio:.0%},B={self.style_config.next_bottom_ratio:.0%})"
        )

    def _on_render_finished(self, output_path):
        fs = os.path.getsize(output_path)
        self._log(f"✅ 渲染完成! ({fs/1024/1024:.1f} MB)")
        QMessageBox.information(self, "完成",
            f"🎉 视频渲染完成!\n\n{output_path}\n\n{fs/1024/1024:.1f} MB")
        # 清理 ASS 文件（除非用户勾选保留）
        if (hasattr(self, 'save_ass_check') and not self.save_ass_check.isChecked()
                and self.karaoke_renderer):
            self.karaoke_renderer.clear_state()
        elif self.karaoke_renderer and self.karaoke_renderer.last_ass_path:
            self._log(f"歌词文件已保存: {self.karaoke_renderer.last_ass_path}")

        self.step_indicator.set_step(5)
        self._set_processing_state(False)

    def _detect_beats_and_align(self, audio_path, lyrics):
        try:
            import librosa
            import numpy as np
            self._log("正在检测音频节拍 (librosa)...")
            y, sr = librosa.load(audio_path, sr=22050, duration=600)
            tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
            beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()
            if not beat_times:
                return lyrics
            self._log(f"节拍检测完成: {len(beat_times)} 拍, ~{float(tempo):.0f} BPM")
            from core.timeline_aligner import TimelineAligner
            return TimelineAligner().align_lyrics(lyrics, beat_times)
        except Exception as e:
            self._log(f"节拍检测失败: {e}")
            return lyrics

    def _on_error(self, msg):
        self._log(f"❌ 错误: {msg}")
        QMessageBox.critical(self, "错误", msg)
        self._set_processing_state(False)

    def _set_processing_state(self, processing: bool):
        self.progress_bar.setVisible(processing)
        self.progress_bar.setRange(0, 0)
        self.fetch_btn.setEnabled(not processing)
        self.render_btn.setEnabled(not processing)

    def _log(self, msg: str):
        self.status_text.append(msg)
        sb = self.status_text.verticalScrollBar()
        sb.setValue(sb.maximum())
