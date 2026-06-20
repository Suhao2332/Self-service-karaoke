"""
音频播放器模块
基于 pygame.mixer 实现音频播放/暂停/停止/定位

支持 WAV 格式音频的精确 seek 定位：
  将音频加载为 numpy 数组，seek 时从目标位置切片生成新的 Sound 对象。
  配合 QTimer 轮询播放位置，实现进度同步。
"""
import os
import time
import numpy as np
import pygame

# pygame.mixer 全局只初始化一次
_mixer_initialized = False


def _ensure_mixer(sample_rate: int = 44100):
    """
    确保 pygame.mixer 已初始化。
    若已初始化且参数匹配则跳过; 若参数不匹配则 quit 后重新 init。
    """
    global _mixer_initialized
    if _mixer_initialized:
        # 检查当前参数是否匹配
        try:
            cur_freq = pygame.mixer.get_init()
            if cur_freq and cur_freq[0] == sample_rate:
                return
            # 参数不匹配：需要重新 init
            pygame.mixer.quit()
            _mixer_initialized = False
        except pygame.error:
            _mixer_initialized = False

    if not _mixer_initialized:
        try:
            pygame.mixer.init(frequency=sample_rate, size=-16, channels=1,
                              allowedchanges=0)
            _mixer_initialized = True
        except pygame.error as e:
            # 音频设备不可用（无音频输出）
            _mixer_initialized = False
            raise RuntimeError(f"音频设备初始化失败: {e}")


class AudioPlayer:
    """
    音频播放器 — 封装 pygame.mixer

    用法:
        player = AudioPlayer("audio.wav")
        player.play()
        player.seek(10.0)
        player.pause()
        player.resume()
        pos = player.get_pos()   # 当前播放秒数
        player.stop()
    """

    def __init__(self, audio_path: str = ""):
        self._audio_path = ""
        self._data: np.ndarray = np.array([], dtype=np.float32)
        self._sample_rate: int = 44100
        self._duration: float = 0.0

        # 当前播放状态
        self._channel: pygame.mixer.Channel | None = None
        self._sound: pygame.mixer.Sound | None = None
        self._playing = False
        self._paused = False
        self._seek_offset: float = 0.0  # 当前切片在完整音频中的起始秒数
        self._play_start_wall: float = 0.0  # 最近一次 play() 时的 wall-clock
        self._mixer_ok = False  # mixer 是否可用

        # 尝试初始化 mixer（不抛出异常）
        try:
            _ensure_mixer(self._sample_rate)
            self._mixer_ok = True
        except RuntimeError:
            self._mixer_ok = False

        if audio_path:
            self.load(audio_path)

    # ── 加载 ────────────────────────────────────────────────

    def load(self, audio_path: str):
        """加载 WAV 音频文件"""
        if not os.path.isfile(audio_path):
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")

        self.stop()
        self._audio_path = audio_path
        self._load_audio_data(audio_path)

    def _load_audio_data(self, path: str):
        """用 soundfile 读取音频数据（librosa 的依赖已自带 soundfile）"""
        import soundfile as sf
        data, sr = sf.read(path)
        if len(data.shape) > 1:
            data = data.mean(axis=1)  # 混音为单声道
        self._data = data.astype(np.float32)
        self._sample_rate = int(sr)
        self._duration = len(data) / sr if sr > 0 else 0.0

        # 如 mixer 参数与音频采样率不匹配，重新初始化
        if self._mixer_ok:
            try:
                _ensure_mixer(self._sample_rate)
            except RuntimeError:
                self._mixer_ok = False

    # ── 播放控制 ────────────────────────────────────────────

    def play(self):
        """从头播放"""
        if self._duration <= 0 or not self._mixer_ok:
            return
        self.stop()
        self._seek_offset = 0.0
        self._do_play_from(0.0)

    def play_from(self, start_sec: float):
        """从指定秒数开始播放"""
        if self._duration <= 0 or not self._mixer_ok:
            return
        self.stop()
        start_sec = max(0.0, min(start_sec, self._duration))
        self._seek_offset = start_sec
        self._do_play_from(start_sec)

    def pause(self):
        """暂停 — 记录当前位置以便恢复时继续"""
        if self._channel and self._playing and not self._paused:
            # 先记录当前 wall-clock 位置
            self._seek_offset = self.get_pos()
            try:
                self._channel.pause()
            except pygame.error:
                pass
            self._paused = True

    def resume(self):
        """恢复播放 — 从暂停位置继续，时钟续接"""
        if self._channel and self._paused:
            try:
                self._channel.unpause()
            except pygame.error:
                pass
            self._paused = False
            # 重置时钟基准，让 get_pos() 从 _seek_offset 继续递增
            self._play_start_wall = time.time()

    def stop(self):
        """停止播放"""
        if self._channel:
            try:
                self._channel.stop()
            except pygame.error:
                pass
        self._channel = None
        self._sound = None
        self._playing = False
        self._paused = False
        self._seek_offset = 0.0

    def seek(self, target_sec: float):
        """跳转到指定秒数（停止当前播放，从目标位置重新播放）"""
        if self._duration <= 0 or not self._mixer_ok:
            return
        target_sec = max(0.0, min(target_sec, self._duration))

        if not self._playing:
            # 停止状态：仅更新偏移量，不启动播放
            self._seek_offset = target_sec
            return

        was_playing = not self._paused

        self._seek_offset = target_sec
        self._do_play_from(target_sec)

        if not was_playing and self._channel:
            try:
                self._channel.pause()
            except pygame.error:
                pass
            self._paused = True
            self._playing = True

    # ── 内部 ────────────────────────────────────────────────

    def _do_play_from(self, start_sec: float):
        """从 start_sec 切片并播放"""
        if not self._mixer_ok or len(self._data) == 0:
            return

        # 先停掉旧播放，防止音频重叠
        if self._channel:
            try:
                self._channel.stop()
            except pygame.error:
                pass
        self._channel = None
        self._sound = None

        start_sample = int(start_sec * self._sample_rate)
        if start_sample >= len(self._data):
            return

        try:
            segment = self._data[start_sample:]
            # 归一化到 int16 范围 (pygame Sound 需要)
            seg_norm = segment / (np.max(np.abs(segment)) + 1e-8) if np.max(np.abs(segment)) > 0 else segment
            segment_int16 = (seg_norm * 32767).clip(-32768, 32767).astype(np.int16)

            self._sound = pygame.sndarray.make_sound(segment_int16)
            result = self._sound.play()
            if result is None:
                # 所有声道繁忙，尝试等待一个声道释放
                pygame.mixer.set_num_channels(8)
                result = self._sound.play()
            self._channel = result
            self._playing = result is not None
            self._paused = False
            self._play_start_wall = time.time()
        except pygame.error as e:
            self._channel = None
            self._playing = False
            self._paused = False

    # ── 查询 ────────────────────────────────────────────────

    def get_pos(self) -> float:
        """
        当前播放位置（秒）。
        基于 wall-clock 追踪，不依赖 pygame 内部时钟，更可靠。
        """
        if not self._playing or not self._channel:
            return self._seek_offset if self._playing else 0.0

        if self._paused:
            return self._seek_offset

        # 用 wall-clock 计算经过时间
        elapsed = time.time() - self._play_start_wall
        segment_duration = self._duration - self._seek_offset
        if elapsed >= segment_duration:
            # 播放已结束
            self._playing = False
            return self._duration

        return self._seek_offset + elapsed

    def is_playing(self) -> bool:
        return self._playing and not self._paused

    def is_paused(self) -> bool:
        return self._paused

    def is_available(self) -> bool:
        """音频播放器是否可用（mixer 初始化成功）"""
        return self._mixer_ok

    def get_duration(self) -> float:
        return self._duration

    def get_audio_path(self) -> str:
        return self._audio_path

    # ── 析构 ────────────────────────────────────────────────

    def close(self):
        self.stop()
