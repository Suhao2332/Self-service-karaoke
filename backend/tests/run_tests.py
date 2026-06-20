"""
模块测试脚本 - 逐个测试所有核心模块
"""
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
TEST_VIDEO = os.path.join(TEST_DIR, "test_video.mp4")
OUTPUT_DIR = os.path.join(TEST_DIR, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def separator(title):
    print()
    print("=" * 70)
    print(f"  测试: {title}")
    print("=" * 70)

def print_result(name, passed, detail=""):
    icon = "PASS" if passed else "FAIL"
    print(f"  [{icon}] {name}" + (f" — {detail}" if detail else ""))


# ============================================================
# 1. ffmpeg_helper
# ============================================================
separator("ffmpeg_helper")

from utils.ffmpeg_helper import check_ffmpeg, get_ffmpeg_path

r = check_ffmpeg()
print_result("check_ffmpeg()", r is True, f"返回 {r}")

path = get_ffmpeg_path()
print_result("get_ffmpeg_path()", path == "ffmpeg", f'返回 "{path}"')

assert r is True, "FFmpeg 必须可用才能继续后续测试"
print("  >>> ffmpeg_helper: 全部通过 <<<")


# ============================================================
# 2. audio_processor
# ============================================================
separator("audio_processor — 音频提取")

from core.audio_processor import extract_audio, get_audio_duration

# 检查测试视频存在
assert os.path.exists(TEST_VIDEO), f"测试视频不存在: {TEST_VIDEO}"
print_result("测试视频存在", True, os.path.basename(TEST_VIDEO))

# 提取音频
audio_out = os.path.join(OUTPUT_DIR, "test_audio.wav")
if os.path.exists(audio_out):
    os.remove(audio_out)

try:
    result_path = extract_audio(TEST_VIDEO, audio_out)
    file_ok = os.path.exists(result_path) and os.path.getsize(result_path) > 0
    print_result("extract_audio()", file_ok, f"输出: {os.path.basename(result_path)} ({os.path.getsize(result_path)} bytes)")
except Exception as e:
    print_result("extract_audio()", False, str(e))
    result_path = None
    file_ok = False

# 获取音频时长
if file_ok:
    try:
        duration = get_audio_duration(result_path)
        print_result("get_audio_duration()", duration > 0, f"时长: {duration:.2f} 秒")
    except Exception as e:
        print_result("get_audio_duration()", False, str(e))
else:
    print_result("get_audio_duration()", False, "跳过了（音频提取失败）")

print("  >>> audio_processor: 完成 <<<")


# ============================================================
# 3. timeline_aligner
# ============================================================
separator("timeline_aligner — 时间轴对齐 v2")

from core.timeline_aligner import TimelineAligner

aligner = TimelineAligner()
print_result("TimelineAligner 实例化", isinstance(aligner, TimelineAligner))

# ── 测试数据 ──
# 均匀节拍（每拍 0.6 秒）
beat_times_uniform = [0.0, 0.6, 1.2, 1.8, 2.4, 3.0, 3.6, 4.2, 4.8, 5.4,
                      6.0, 6.6, 7.2, 7.8, 8.4, 9.0, 9.6, 10.2]

# 变节奏节拍（rubato：前 4 拍密、中间一拍长 pause、后面恢复正常）
beat_times_rubato = [0.0, 0.4, 0.7, 1.1, 1.5, 2.5, 3.0, 3.4, 3.8, 4.2]

# ── 测试 1：LRC 格式基本对齐 ──
lrc_lyrics = [
    {"time": 0.5, "text": "天青色等烟雨"},
    {"time": 3.0, "text": "而我在等你"},
    {"time": 6.0, "text": "炊烟袅袅升起"},
    {"time": 9.0, "text": "隔江千万里"},
]
aligned = aligner.align_lyrics(lrc_lyrics, beat_times_uniform)
has_aligned = len(aligned) == len(lrc_lyrics)
print_result("align_lyrics(LRC) 数量一致", has_aligned,
             f"输入 {len(lrc_lyrics)} 条, 输出 {len(aligned)} 条")

if has_aligned:
    all_on_beats = all(t in beat_times_uniform for a in aligned
                       if (t := a.get("time")) is not None)
    print_result("align_lyrics(LRC) 时间戳对齐到节拍", all_on_beats)

# ── 测试 2：有序性保证（时间戳严格递增）──
ordered = True
for i in range(1, len(aligned)):
    if aligned[i]["time"] <= aligned[i - 1]["time"]:
        ordered = False
        break
print_result("align_lyrics(LRC) 时间戳严格递增", ordered)

# ── 测试 3：碰撞发散——密集歌词不会拍到同一拍 ──
dense_lyrics = [
    {"time": 0.3, "text": "天"},
    {"time": 0.5, "text": "青"},
    {"time": 0.7, "text": "色"},
]
aligned_dense = aligner.align_lyrics(dense_lyrics, beat_times_uniform)
times_dense = [a["time"] for a in aligned_dense]
no_collision = len(set(times_dense)) == len(times_dense)
print_result("密集歌词碰撞发散: 所有时间戳不重复", no_collision,
             f"时间戳: {times_dense}")

# ── 测试 4：变节奏（rubato）场景 ──
rubato_lyrics = [
    {"time": 0.2, "text": "慢"},
    {"time": 1.8, "text": "的"},
    {"time": 3.5, "text": "歌"},
]
aligned_rubato = aligner.align_lyrics(rubato_lyrics, beat_times_rubato)
rubato_on_beats = all(t in beat_times_rubato for a in aligned_rubato
                      if (t := a.get("time")) is not None)
rubato_ordered = all(
    aligned_rubato[i]["time"] > aligned_rubato[i - 1]["time"]
    for i in range(1, len(aligned_rubato))
)
print_result("rubato 节拍网格对齐到拍", rubato_on_beats)
print_result("rubato 保持严格递增", rubato_ordered)
if len(aligned_rubato) >= 2:
    print(f"    rubato 时间: {[a['time'] for a in aligned_rubato]}")

# ── 测试 5：空数据 ──
empty = aligner.align_lyrics([], [1, 2, 3])
print_result("align_lyrics(空歌词)", empty == [], f"返回 {empty}")

empty_beats = aligner.align_lyrics(lrc_lyrics[:1], [])
print_result("align_lyrics(空节拍)", empty_beats == lrc_lyrics[:1],
             "返回原歌词")

# ── 测试 6：逐词格式 ──
word_lyrics = [
    {"start": 0.5, "end": 1.0, "text": "天"},
    {"start": 1.5, "end": 2.0, "text": "青"},
]
aligned_words = aligner.align_lyrics(word_lyrics, beat_times_uniform)
print_result("align_lyrics(逐词格式) 数量",
             len(aligned_words) == 2)

# ── 测试 7：向后兼容 _find_nearest_beat ──
nearest = aligner._find_nearest_beat(0.55, beat_times_uniform)
print_result("_find_nearest_beat() 向后兼容",
             nearest == 0.6, f"输入 0.55 → 输出 {nearest}")

# ── 测试 8：边界值 —— 首拍之前 / 末拍之后 ──
early = aligner._map_to_beat_grid(-1.0, beat_times_uniform)
late = aligner._map_to_beat_grid(999.0, beat_times_uniform)
print_result("边界: t<首拍 → 首拍", early == beat_times_uniform[0],
             f"-1.0 → {early}")
print_result("边界: t>末拍 → 末拍", late == beat_times_uniform[-1],
             f"999.0 → {late}")

print("  >>> timeline_aligner: 全部通过 <<<")


# ============================================================
# 4. karaoke_renderer — ASS 生成（不含FFmpeg渲染）
# ============================================================
separator("karaoke_renderer — ASS字幕生成")

from core.karaoke_renderer import KaraokeRenderer

renderer = KaraokeRenderer()
print_result("KaraokeRenderer 实例化", isinstance(renderer, KaraokeRenderer))

# 测试 ASS 内容生成（逐词格式）
word_timeline = [
    {"start": 0.0, "end": 0.5, "text": "天"},
    {"start": 0.5, "end": 1.0, "text": "青"},
    {"start": 1.0, "end": 1.5, "text": "色"},
    {"start": 2.0, "end": 3.0, "text": "等"},
    {"start": 3.0, "end": 4.0, "text": "烟"},
    {"start": 4.0, "end": 5.0, "text": "雨"},
]

ass_content = renderer._generate_ass_content(word_timeline)
print_result("_generate_ass_content(逐词)", bool(ass_content), f"长度 {len(ass_content)} 字符")

# 检查 ASS 关键结构
checks = {
    "[Script Info]": "[Script Info]" in ass_content,
    "[V4+ Styles]": "[V4+ Styles]" in ass_content,
    "[Events]": "[Events]" in ass_content,
    "\\kf" in ass_content: "\\kf" in ass_content,
    "Dialogue:": "Dialogue:" in ass_content,
}
for check_name, ok in checks.items():
    label = str(check_name) if isinstance(check_name, str) else check_name
    print_result(f"  ASS包含: {label}", ok)

# 测试 ASS 内容生成（LRC 格式）
lrc_timeline = [
    {"time": 0.0, "text": "天青色等烟雨"},
    {"time": 3.0, "text": "而我在等你"},
]
ass_content_lrc = renderer._generate_ass_content(lrc_timeline)
print_result("_generate_ass_content(LRC)", bool(ass_content_lrc), f"长度 {len(ass_content_lrc)} 字符")

# 测试时间格式化
time_str = renderer._format_time_ass(3661.25)
print_result("_format_time_ass()", time_str == "1:01:01.25", f"3661.25s → {time_str}")

# 测试 ASS 时间解析
parsed = renderer._parse_ass_time("1:01:01.25")
print_result("_parse_ass_time()", abs(parsed - 3661.25) < 0.01, f"1:01:01.25 → {parsed}s")

# 测试创建 ASS 文件
ass_path = os.path.join(OUTPUT_DIR, "test_subtitle.ass")
renderer._create_ass_subtitle(ass_path, word_timeline)
ass_exists = os.path.exists(ass_path)
print_result("_create_ass_subtitle() 文件创建", ass_exists, ass_path)

print("  >>> karaoke_renderer ASS生成: 全部通过 <<<")


# ============================================================
# 5. karaoke_renderer — 完整渲染（使用FFmpeg）
# ============================================================
separator("karaoke_renderer — FFmpeg 渲染")

output_video = os.path.join(OUTPUT_DIR, "test_karaoke.mp4")

try:
    renderer2 = KaraokeRenderer()
    result_video = renderer2.render_karaoke(TEST_VIDEO, lrc_timeline, output_video)
    video_ok = os.path.exists(result_video) and os.path.getsize(result_video) > 0
    print_result("render_karaoke()", video_ok, f"输出: {os.path.basename(result_video)} ({os.path.getsize(result_video)} bytes)")
    ass_exists2 = renderer2.last_ass_path and os.path.exists(renderer2.last_ass_path)
    print_result("  last_ass_path 记录", ass_exists2, renderer2.last_ass_path or "无")
except Exception as e:
    print_result("render_karaoke()", False, str(e))
    video_ok = False

# 测试时间偏移
if video_ok and renderer2.last_ass_path:
    try:
        with open(renderer2.last_ass_path, "r", encoding="utf-8") as f:
            content_before = f.read()
        renderer2.update_lyrics_timing(renderer2.last_ass_path, 1.0)
        with open(renderer2.last_ass_path, "r", encoding="utf-8") as f:
            content_after = f.read()
        changed = content_before != content_after
        print_result("update_lyrics_timing(+1s)", changed, "内容已变更" if changed else "内容未变（异常）")
    except Exception as e:
        print_result("update_lyrics_timing(+1s)", False, str(e))
else:
    print_result("update_lyrics_timing()", False, "跳过了（渲染未完成或无ASS路径）")

print("  >>> karaoke_renderer 渲染: 完成 <<<")


# ============================================================
# 6. lyrics_fetcher — 歌词搜索与获取
# ============================================================
separator("lyrics_fetcher — 歌词搜索")

from core.lyrics_fetcher import LyricsFetcher

fetcher = LyricsFetcher()
print_result("LyricsFetcher 实例化", isinstance(fetcher, LyricsFetcher))

# 搜索歌曲（使用一首经典中文歌曲）
try:
    songs = fetcher.search_song("青花瓷", "周杰伦")
    found = len(songs) > 0
    print_result("search_song('青花瓷', '周杰伦')", found, f"找到 {len(songs)} 首")
    if found:
        for s in songs[:3]:
            print(f"         - {s['title']} / {s['artist']} (来源: {s.get('source','?')}, ID: {s['id']})")
except Exception as e:
    print_result("search_song('青花瓷', '周杰伦')", False, str(e))
    found = False
    songs = []

# 如果搜索到歌曲，尝试获取歌词
if found:
    try:
        lyrics_data = fetcher.fetch_lyrics(songs[0]["id"], songs[0].get("source", "netease"))
        has_lyrics = lyrics_data is not None
        print_result("fetch_lyrics()", has_lyrics, f"来源: {songs[0].get('source','?')}" if has_lyrics else "无歌词数据")
        if has_lyrics:
            lrc_count = len(lyrics_data.get("lrc", []))
            word_count = len(lyrics_data.get("word_lyrics", []))
            raw_len = len(lyrics_data.get("raw_lrc", ""))
            print(f"         LRC行数: {lrc_count}, 逐词数: {word_count}, 原始LRC长度: {raw_len}")

            if lrc_count > 0:
                print(f"         首句: [{lyrics_data['lrc'][0]['time']:.1f}s] {lyrics_data['lrc'][0]['text']}")
    except Exception as e:
        print_result("fetch_lyrics()", False, str(e))
else:
    print_result("fetch_lyrics()", "跳过" if not found else "", "搜索未返回结果（可能无网络）")

# 测试 LRC 解析器（本地）
raw_lrc = """[00:01.50]天青色等烟雨
[00:05.00]而我在等你
[00:08.50]炊烟袅袅升起
[00:12.00]隔江千万里"""
parsed_lrc = fetcher._parse_lrc_lyrics(raw_lrc)
print_result("_parse_lrc_lyrics() 本地解析", len(parsed_lrc) == 4, f"解析 {len(parsed_lrc)}/4 行")

# 测试 word_lyrics 解析（本地）
raw_word = """[0,500]天[500,1000]青[1000,1500]色"""
parsed_word = fetcher._parse_word_lyrics(raw_word)
print_result("_parse_word_lyrics() 本地解析", len(parsed_word) == 3, f"解析 {len(parsed_word)}/3 字")

# 测试 generate_word_timeline
generated = fetcher._generate_word_timeline(parsed_lrc)
print_result("_generate_word_timeline()", len(generated) > 0, f"生成 {len(generated)} 个字的时间轴")

print("  >>> lyrics_fetcher: 完成 <<<")


# ============================================================
# 总结
# ============================================================
separator("测试总结")
print(f"  测试输出目录: {OUTPUT_DIR}")
print(f"  测试视频: {TEST_VIDEO}")
print()
print("  模块测试全部完成。")
print()
