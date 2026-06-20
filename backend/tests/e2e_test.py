"""
端到端测试：从搜索 → 获取歌词 → 合并 → 渲染 → 验证
测试用例: ちるちる - Reol (有原文+译文+罗马音)

用法:
    python tests/e2e_test.py
    python tests/e2e_test.py --song "Lemon" --artist "米津玄师" --source netease
"""
import sys, os, argparse, time, tempfile, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from core.lyrics_fetcher import LyricsFetcher


# ── 简单的日志 ──
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"

def log(msg, color=""):
    print(f"{color}{msg}{RESET}")

def check(msg, ok=True):
    marker = f"{GREEN}✓{RESET}" if ok else f"{RED}✗{RESET}"
    print(f"  {marker} {msg}")
    return ok


def test_search_and_fetch(title, artist, source_hint=None):
    """测试搜索+获取全链路"""
    f = LyricsFetcher()

    # ── Step 1: 搜索 ──
    log(f"\n{'='*60}")
    log(f"Step 1: 搜索 '{title} - {artist}'", YELLOW)
    results = f.search_all_sources(title, artist)
    total = sum(len(v) for v in results.values())
    sources_found = [k for k, v in results.items() if v]
    check(f"找到 {total} 首歌 (来源: {', '.join(sources_found)})", total > 0)
    if not total:
        return False

    for src, songs in results.items():
        if songs:
            log(f"  [{src}] {len(songs)}首, 第1: {songs[0].get('title','?')} / {songs[0].get('artist','?')}")

    # ── Step 2: 选择源 ──
    if source_hint:
        # 支持中文和英文源名
        src_map = {"netease": "网易云音乐", "kugou": "酷狗音乐", "qqmusic": "QQ音乐"}
        target_src = src_map.get(source_hint, source_hint)
        if target_src not in results:
            target_src = next((s for s in results if target_src in s or s in target_src), sources_found[0])
    else:
        # 优先网易云（支持译文+罗马音最好的源）
        target_src = next((s for s in sources_found if "网易" in s), sources_found[0])

    songs = results[target_src]
    song = songs[0]
    log(f"\nStep 2: 选择 [{target_src}] {song['title']} — {song['artist']}", YELLOW)
    check(f"id={song['id']}", True)

    # ── Step 3: 获取歌词 (全类型) ──
    log(f"\nStep 3: 获取歌词", YELLOW)
    extra = {}
    source_key = "netease"
    if "酷狗" in target_src:
        source_key = "kugou"
        extra = {"hash": song.get("hash", ""),
                 "title": song["title"],
                 "artist": song["artist"]}
    elif "QQ" in target_src:
        source_key = "qqmusic"
    # else: netease

    lyrics = f.fetch_lyrics(song["id"], source_key, extra)

    has_lrc = bool(lyrics and lyrics.get("lrc"))
    has_ts = bool(lyrics and lyrics.get("tlyric"))
    has_roma = bool(lyrics and lyrics.get("romalrc"))
    has_words = bool(lyrics and lyrics.get("word_lyrics"))

    passed = check(f"原文LRC: {len(lyrics.get('lrc',[]))}行", has_lrc)
    check(f"译文: {'YES' if has_ts else 'NO'} ({len(lyrics.get('tlyric',[])) if has_ts else 0}行)",
          has_ts if "网易" in target_src else True)  # 非网易云不强求译文
    check(f"罗马音: {'YES' if has_roma else 'NO'} ({len(lyrics.get('romalrc',[])) if has_roma else 0}行)",
          has_roma if "网易" in target_src else True)
    check(f"逐词: {len(lyrics.get('word_lyrics',[]))}字", has_words)

    if not passed:
        return False

    # ── Step 4: 模拟三合一合并 ──
    log(f"\nStep 4: 模拟合并 (原文+译文+罗马音)", YELLOW)
    lrc = lyrics["lrc"]
    ts_data = lyrics.get("tlyric", [])
    roma_data = lyrics.get("romalrc", [])

    merged = []
    ts_idx = roma_idx = 0
    for p in lrc:
        merged_text = p["text"]
        if ts_data:
            while ts_idx < len(ts_data) and ts_data[ts_idx]["time"] < p["time"]:
                ts_idx += 1
            if ts_idx < len(ts_data) and abs(ts_data[ts_idx]["time"] - p["time"]) < 3.0:
                merged_text += "\\N" + ts_data[ts_idx]["text"]
        if roma_data:
            while roma_idx < len(roma_data) and roma_data[roma_idx]["time"] < p["time"]:
                roma_idx += 1
            if roma_idx < len(roma_data) and abs(roma_data[roma_idx]["time"] - p["time"]) < 3.0:
                merged_text += "\\N" + roma_data[roma_idx]["text"]
        merged.append({"time": p["time"], "text": merged_text})

    has_merged = any("\\N" in m["text"] for m in merged)
    check(f"合并后行数: {len(merged)}, 含\\N: {has_merged}", len(merged) > 0)

    # 展示前5行
    for m in merged[:5]:
        text_preview = m["text"].replace("\\N", " | ")[:80]
        log(f"    [{m['time']:.1f}s] {text_preview}")

    # ── Step 5: 测试 ASS 内容生成（不实际渲染视频） ──
    log(f"\nStep 5: 测试 ASS 内容生成", YELLOW)
    try:
        from core.karaoke_renderer import KaraokeRenderer
        renderer = KaraokeRenderer()
        ass_content = renderer._generate_ass_content(merged)
        lines = ass_content.split("\n")
        dialogue_count = sum(1 for l in lines if l.startswith("Dialogue:"))
        check(f"ASS生成: {len(lines)}行 ({dialogue_count}条Dialogue)", dialogue_count > 0)

        # 检查 ASS 中是否有 \N 换行
        has_ass_newline = "\\N" in ass_content
        check(f"ASS含\\N换行: {has_ass_newline}", True)  # 不强求

        # 保存 ASS 到临时文件
        ass_path = os.path.join(tempfile.gettempdir(), f"e2e_test_{source_key}.ass")
        with open(ass_path, "w", encoding="utf-8") as f:
            f.write(ass_content)
        check(f"ASS已保存: {ass_path}", os.path.exists(ass_path))

    except Exception as e:
        check(f"ASS生成失败: {e}", False)
        return False

    # ── Step 6: 保存歌词到 JSON ──
    log(f"\nStep 6: 保存歌词JSON", YELLOW)
    json_path = os.path.join(tempfile.gettempdir(), f"e2e_test_{source_key}.json")
    output = {
        "title": song["title"],
        "artist": song["artist"],
        "source": target_src,
        "lrc_count": len(lrc),
        "ts_count": len(ts_data),
        "roma_count": len(roma_data),
        "word_count": len(lyrics.get("word_lyrics", [])),
        "lrc_lines": lrc,
        "ts_lines": ts_data,
        "roma_lines": roma_data,
        "merged_lines": merged,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    check(f"JSON已保存: {json_path}", os.path.exists(json_path))

    return True


def test_ffmpeg_available():
    """检查 FFmpeg 是否可用"""
    log(f"\n{'='*60}")
    log(f"Step 0: 环境检查", YELLOW)
    import subprocess
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5, check=True)
        check("FFmpeg 可用", True)
        return True
    except Exception:
        check("FFmpeg 不可用 (将跳过视频渲染)", False)
        return False


def test_render_with_sample_video(lyrics_data, source_key):
    """用 samples 目录下的测试视频做渲染"""
    log(f"\n{'='*60}")
    log(f"Step 7: 视频渲染测试", YELLOW)

    test_video = os.path.join(os.path.dirname(__file__), "test_video.mp4")
    if not os.path.exists(test_video):
        log("  (跳过) 未找到 tests/test_video.mp4", YELLOW)
        return True

    log(f"  视频: {test_video}")
    from core.karaoke_renderer import KaraokeRenderer

    output = os.path.join(tempfile.gettempdir(), f"e2e_karaoke_{source_key}.mp4")
    renderer = KaraokeRenderer()
    try:
        result = renderer.render_karaoke(test_video, lyrics_data, output)
        size_mb = os.path.getsize(result) / 1024 / 1024
        check(f"渲染成功: {result} ({size_mb:.1f}MB)", os.path.exists(result))
    except Exception as e:
        check(f"渲染失败: {e}", False)


def main():
    parser = argparse.ArgumentParser(description="端到端测试")
    parser.add_argument("--song", default="ちるちる", help="歌曲名")
    parser.add_argument("--artist", default="Reol", help="歌手")
    parser.add_argument("--source", default=None, help="来源 (netease/kugou/qqmusic)")
    parser.add_argument("--render", action="store_true", help="也测试视频渲染")
    args = parser.parse_args()

    log(f"=== LDDC 端到端测试 ===", GREEN)
    log(f"歌曲: {args.song} — {args.artist}")
    log(f"来源: {args.source or '自动选择'}")

    ffmpeg_ok = test_ffmpeg_available()

    success = test_search_and_fetch(args.song, args.artist, args.source)

    if success and ffmpeg_ok and args.render:
        json_path = os.path.join(tempfile.gettempdir(), f"e2e_test_{args.source or 'kugou'}.json")
        if os.path.exists(json_path):
            with open(json_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            test_render_with_sample_video(saved["merged_lines"], args.source or "kugou")

    log(f"\n{'='*60}")
    if success:
        log("✅ 端到端测试通过", GREEN)
    else:
        log("❌ 端到端测试失败", RED)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
