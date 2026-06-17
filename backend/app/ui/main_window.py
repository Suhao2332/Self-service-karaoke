"""
桌面应用主窗口
使用PyQt6实现
"""
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *
import sys
import os

from core.lyrics_fetcher import LyricsFetcher
from core.song_identifier import SongIdentifier
from core.karaoke_renderer import KaraokeRenderer
from core.audio_processor import extract_audio

class MainWindow(QMainWindow):
    """主窗口"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MV卡拉OK制作器")
        self.setMinimumSize(1200, 800)
        
        # 初始化核心模块
        self.lyrics_fetcher = LyricsFetcher()
        self.song_identifier = SongIdentifier()
        self.karaoke_renderer = KaraokeRenderer()
        
        # 设置UI
        self.setup_ui()
    
    def setup_ui(self):
        """设置UI布局"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout(central_widget)
        
        # 顶部工具栏
        toolbar = self.create_toolbar()
        layout.addWidget(toolbar)
        
        # 主要内容区域
        content_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 左侧：视频预览
        self.video_widget = QVideoWidget()
        content_splitter.addWidget(self.video_widget)
        
        # 右侧：歌词编辑
        self.lyrics_editor = QTextEdit()
        self.lyrics_editor.setPlaceholderText("歌词将在这里显示...")
        content_splitter.addWidget(self.lyrics_editor)
        
        layout.addWidget(content_splitter)
        
        # 底部控制栏
        controls = self.create_controls()
        layout.addWidget(controls)
    
    def create_toolbar(self):
        """创建工具栏"""
        toolbar = QToolBar()
        
        # 上传按钮
        upload_btn = QAction("上传MV", self)
        upload_btn.triggered.connect(self.upload_video)
        toolbar.addAction(upload_btn)
        
        # 识别歌曲按钮
        identify_btn = QAction("识别歌曲", self)
        identify_btn.triggered.connect(self.identify_song)
        toolbar.addAction(identify_btn)
        
        # 获取歌词按钮
        fetch_btn = QAction("获取歌词", self)
        fetch_btn.triggered.connect(self.fetch_lyrics)
        toolbar.addAction(fetch_btn)
        
        # 渲染按钮
        render_btn = QAction("渲染卡拉OK", self)
        render_btn.triggered.connect(self.render_karaoke)
        toolbar.addAction(render_btn)
        
        # 导出按钮
        export_btn = QAction("导出视频", self)
        export_btn.triggered.connect(self.export_video)
        toolbar.addAction(export_btn)
        
        return toolbar
    
    def create_controls(self):
        """创建控制栏"""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        
        # 播放控制
        self.play_btn = QPushButton("播放")
        self.play_btn.clicked.connect(self.toggle_play)
        layout.addWidget(self.play_btn)
        
        # 进度条
        self.progress_slider = QSlider(Qt.Orientation.Horizontal)
        layout.addWidget(self.progress_slider)
        
        # 时间显示
        self.time_label = QLabel("00:00 / 00:00")
        layout.addWidget(self.time_label)
        
        # 音量控制
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setMaximum(100)
        self.volume_slider.setValue(50)
        layout.addWidget(self.volume_slider)
        
        return widget
    
    def upload_video(self):
        """上传视频文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择MV视频", "", 
            "视频文件 (*.mp4 *.avi *.mkv *.mov)"
        )
        
        if file_path:
            self.video_path = file_path
            self.video_widget.setSource(QUrl.fromLocalFile(file_path))
            self.statusBar().showMessage(f"已加载: {os.path.basename(file_path)}")
    
    def identify_song(self):
        """识别歌曲"""
        if not hasattr(self, 'video_path'):
            QMessageBox.warning(self, "警告", "请先上传视频")
            return
        
        # 提取音频
        audio_path = extract_audio(self.video_path)
        
        # 识别歌曲
        song_info = self.song_identifier.identify_from_audio(audio_path)
        
        if song_info:
            self.song_info = song_info
            QMessageBox.information(
                self, "识别结果",
                f"歌曲: {song_info['title']}\n"
                f"歌手: {song_info['artist']}\n"
                f"专辑: {song_info['album']}"
            )
        else:
            # 手动输入
            title, ok = QInputDialog.getText(self, "手动输入", "请输入歌曲名称:")
            if ok and title:
                artist, ok = QInputDialog.getText(self, "手动输入", "请输入歌手名称:")
                if ok:
                    self.song_info = {"title": title, "artist": artist}
    
    def fetch_lyrics(self):
        """获取歌词"""
        if not hasattr(self, 'song_info'):
            QMessageBox.warning(self, "警告", "请先识别歌曲")
            return
        
        # 搜索歌曲
        songs = self.lyrics_fetcher.search_song(
            self.song_info["title"],
            self.song_info["artist"]
        )
        
        if songs:
            # 选择歌曲
            song_list = [f"{s['title']} - {s['artist']}" for s in songs]
            song_choice, ok = QInputDialog.getItem(
                self, "选择歌曲", "请选择匹配的歌曲:",
                song_list, 0, False
            )
            
            if ok and song_choice:
                idx = song_list.index(song_choice)
                song_id = songs[idx]["id"]
                
                # 获取歌词
                lyrics_data = self.lyrics_fetcher.fetch_lyrics(song_id)
                if lyrics_data:
                    self.lyrics_data = lyrics_data
                    self.lyrics_editor.setText(lyrics_data["raw_lrc"])
                    QMessageBox.information(self, "成功", "歌词获取成功")
        else:
            QMessageBox.warning(self, "失败", "未找到歌词")
    
    def render_karaoke(self):
        """渲染卡拉OK视频"""
        if not hasattr(self, 'lyrics_data'):
            QMessageBox.warning(self, "警告", "请先获取歌词")
            return
        
        # 获取逐词时间轴
        word_timeline = self.lyrics_fetcher.get_word_timeline(
            self.song_info.get("id")
        )
        
        # 渲染
        output_path = self.karaoke_renderer.render_karaoke(
            self.video_path,
            word_timeline if word_timeline else self.lyrics_data["lrc"]
        )
        
        self.output_path = output_path
        QMessageBox.information(self, "成功", f"卡拉OK视频已生成: {output_path}")
    
    def export_video(self):
        """导出视频"""
        if not hasattr(self, 'output_path'):
            QMessageBox.warning(self, "警告", "请先渲染卡拉OK视频")
            return
        
        save_path, _ = QFileDialog.getSaveFileName(
            self, "保存视频", "", "视频文件 (*.mp4)"
        )
        
        if save_path:
            import shutil
            shutil.copy(self.output_path, save_path)
            QMessageBox.information(self, "成功", f"视频已保存到: {save_path}")
    
    def toggle_play(self):
        """切换播放/暂停"""
        if self.video_widget.isPlaying():
            self.video_widget.pause()
            self.play_btn.setText("播放")
        else:
            self.video_widget.play()
            self.play_btn.setText("暂停")
"""
主窗口UI模块
"""
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QTextEdit,
    QProgressBar, QMessageBox, QLineEdit, QGroupBox,
    QFormLayout, QSpinBox, QDoubleSpinBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
import os

class WorkerThread(QThread):
    """工作线程，避免UI卡顿"""
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

class MainWindow(QMainWindow):
    """主窗口"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MV卡拉OK制作器")
        self.setMinimumSize(800, 600)
        
        # 文件路径
        self.video_path = ""
        self.audio_path = ""
        self.output_path = ""
        
        # 初始化UI
        self._init_ui()
    
    def _init_ui(self):
        """初始化UI组件"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        
        # 文件选择区域
        file_group = QGroupBox("文件选择")
        file_layout = QVBoxLayout(file_group)
        
        # 视频文件选择
        video_layout = QHBoxLayout()
        self.video_label = QLabel("未选择视频文件")
        self.video_label.setStyleSheet("color: gray;")
        select_video_btn = QPushButton("选择视频文件")
        select_video_btn.clicked.connect(self._select_video)
        video_layout.addWidget(self.video_label, 1)
        video_layout.addWidget(select_video_btn)
        file_layout.addLayout(video_layout)
        
        # 输出路径选择
        output_layout = QHBoxLayout()
        self.output_label = QLabel("输出路径（可选）")
        self.output_label.setStyleSheet("color: gray;")
        select_output_btn = QPushButton("选择输出路径")
        select_output_btn.clicked.connect(self._select_output)
        output_layout.addWidget(self.output_label, 1)
        output_layout.addWidget(select_output_btn)
        file_layout.addLayout(output_layout)
        
        main_layout.addWidget(file_group)
        
        # 操作按钮区域
        action_group = QGroupBox("操作")
        action_layout = QVBoxLayout(action_group)
        
        self.extract_audio_btn = QPushButton("1. 提取音频")
        self.extract_audio_btn.clicked.connect(self._extract_audio)
        self.extract_audio_btn.setEnabled(False)
        action_layout.addWidget(self.extract_audio_btn)
        
        self.identify_song_btn = QPushButton("2. 识别歌曲")
        self.identify_song_btn.clicked.connect(self._identify_song)
        self.identify_song_btn.setEnabled(False)
        action_layout.addWidget(self.identify_song_btn)
        
        self.fetch_lyrics_btn = QPushButton("3. 获取歌词")
        self.fetch_lyrics_btn.clicked.connect(self._fetch_lyrics)
        self.fetch_lyrics_btn.setEnabled(False)
        action_layout.addWidget(self.fetch_lyrics_btn)
        
        self.render_btn = QPushButton("4. 渲染卡拉OK")
        self.render_btn.clicked.connect(self._render_karaoke)
        self.render_btn.setEnabled(False)
        action_layout.addWidget(self.render_btn)
        
        main_layout.addWidget(action_group)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)
        
        # 状态信息
        self.status_text = QTextEdit()
        self.status_text.setReadOnly(True)
        self.status_text.setMaximumHeight(200)
        main_layout.addWidget(self.status_text)
        
        # 手动调整区域
        adjust_group = QGroupBox("手动调整")
        adjust_layout = QFormLayout(adjust_group)
        
        self.time_offset_spin = QDoubleSpinBox()
        self.time_offset_spin.setRange(-10.0, 10.0)
        self.time_offset_spin.setSingleStep(0.1)
        self.time_offset_spin.setValue(0.0)
        self.time_offset_spin.setSuffix(" 秒")
        adjust_layout.addRow("时间偏移:", self.time_offset_spin)
        
        apply_offset_btn = QPushButton("应用偏移")
        apply_offset_btn.clicked.connect(self._apply_time_offset)
        adjust_layout.addRow("", apply_offset_btn)
        
        main_layout.addWidget(adjust_group)
    
    def _select_video(self):
        """选择视频文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择视频文件", "",
            "视频文件 (*.mp4 *.avi *.mkv *.mov *.flv);;所有文件 (*.*)"
        )
        
        if file_path:
            self.video_path = file_path
            self.video_label.setText(os.path.basename(file_path))
            self.video_label.setStyleSheet("color: black;")
            self.extract_audio_btn.setEnabled(True)
            self._log(f"已选择视频: {file_path}")
    
    def _select_output(self):
        """选择输出路径"""
        dir_path = QFileDialog.getExistingDirectory(
            self, "选择输出目录"
        )
        
        if dir_path:
            self.output_path = dir_path
            self.output_label.setText(dir_path)
            self.output_label.setStyleSheet("color: black;")
            self._log(f"输出目录: {dir_path}")
    
    def _extract_audio(self):
        """提取音频"""
        if not self.video_path:
            QMessageBox.warning(self, "警告", "请先选择视频文件")
            return
        
        self._set_processing_state(True)
        self._log("开始提取音频...")
        
        # 创建工作线程
        from backend.app.core.audio_processor import extract_audio
        self.worker = WorkerThread(extract_audio, (self.video_path,))
        self.worker.finished.connect(self._on_audio_extracted)
        self.worker.error.connect(self._on_error)
        self.worker.start()
    
    def _on_audio_extracted(self, audio_path):
        """音频提取完成回调"""
        self.audio_path = audio_path
        self._log(f"音频提取完成: {audio_path}")
        self.identify_song_btn.setEnabled(True)
        self._set_processing_state(False)
    
    def _identify_song(self):
        """识别歌曲"""
        if not self.audio_path:
            QMessageBox.warning(self, "警告", "请先提取音频")
            return
        
        self._set_processing_state(True)
        self._log("开始识别歌曲...")
        
        from backend.app.core.song_identifier import SongIdentifier
        identifier = SongIdentifier()
        self.worker = WorkerThread(identifier.identify_from_audio, (self.audio_path,))
        self.worker.finished.connect(self._on_song_identified)
        self.worker.error.connect(self._on_error)
        self.worker.start()
    
    def _on_song_identified(self, song_info):
        """歌曲识别完成回调"""
        if song_info:
            self._log(f"识别结果: {song_info.get('title', '未知')} - "
                     f"{song_info.get('artist', '未知')}")
            self.fetch_lyrics_btn.setEnabled(True)
        else:
            self._log("歌曲识别失败，请手动输入歌曲信息")
        self._set_processing_state(False)
    
    def _fetch_lyrics(self):
        """获取歌词"""
        self._set_processing_state(True)
        self._log("开始获取歌词...")
        
        from backend.app.core.lyrics_fetcher import LyricsFetcher
        fetcher = LyricsFetcher()
        # 这里简化处理，实际需要用户选择歌曲
        self.worker = WorkerThread(fetcher.search_song, ("",))
        self.worker.finished.connect(self._on_lyrics_fetched)
        self.worker.error.connect(self._on_error)
        self.worker.start()
    
    def _on_lyrics_fetched(self, lyrics):
        """歌词获取完成回调"""
        if lyrics:
            self._log(f"获取到 {len(lyrics)} 条歌词")
            self.render_btn.setEnabled(True)
        else:
            self._log("未获取到歌词")
        self._set_processing_state(False)
    
    def _render_karaoke(self):
        """渲染卡拉OK"""
        if not self.video_path:
            QMessageBox.warning(self, "警告", "请先选择视频文件")
            return
        
        self._set_processing_state(True)
        self._log("开始渲染卡拉OK视频...")
        
        from backend.app.core.karaoke_renderer import KaraokeRenderer
        renderer = KaraokeRenderer()
        # 简化处理，实际需要传入歌词数据
        self.worker = WorkerThread(renderer.render_karaoke, (self.video_path, []))
        self.worker.finished.connect(self._on_render_finished)
        self.worker.error.connect(self._on_error)
        self.worker.start()
    
    def _on_render_finished(self, output_path):
        """渲染完成回调"""
        self._log(f"卡拉OK视频已生成: {output_path}")
        QMessageBox.information(self, "完成", f"视频已保存到:\n{output_path}")
        self._set_processing_state(False)
    
    def _apply_time_offset(self):
        """应用时间偏移"""
        offset = self.time_offset_spin.value()
        self._log(f"应用时间偏移: {offset} 秒")
        # 实际实现需要找到ASS文件路径
        QMessageBox.information(self, "提示", "时间偏移功能需要先渲染字幕文件")
    
    def _on_error(self, error_msg):
        """错误处理"""
        self._log(f"错误: {error_msg}")
        QMessageBox.critical(self, "错误", error_msg)
        self._set_processing_state(False)
    
    def _set_processing_state(self, processing: bool):
        """设置处理状态"""
        self.progress_bar.setVisible(processing)
        self.progress_bar.setRange(0, 0)  # 不确定进度
        self.extract_audio_btn.setEnabled(not processing)
        self.identify_song_btn.setEnabled(not processing)
        self.fetch_lyrics_btn.setEnabled(not processing)
        self.render_btn.setEnabled(not processing)
    
    def _log(self, message: str):
        """记录日志"""
        self.status_text.append(message)
        # 自动滚动到底部
        scrollbar = self.status_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
