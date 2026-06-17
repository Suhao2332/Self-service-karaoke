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
