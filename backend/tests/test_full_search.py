"""测试：完整搜索 + 歌词获取"""
import sys
sys.path.insert(0, "F:\\PythonAPP\\Self-service karaoke\\backend\\app")
from core.lyrics_fetcher import LyricsFetcher

f = LyricsFetcher()

print("=== 完整多源搜索 ===")
results = f.search_all_sources("青花瓷", "周杰伦")
for source, songs in results.items():
    print(f"[{source}] {len(songs)} 首:")
    for s in songs[:3]:
        title = s.get("title", "?")
        artist = s.get("artist", "?")
        sid = s.get("id", "?")[:20]
        print(f"   - {title} / {artist}  id={sid}")

print()
print("=== 酷狗歌词获取 ===")
kugou_songs = results.get("酷狗音乐", [])
if kugou_songs:
    s = kugou_songs[0]
    print(f"选择: {s['title']} / {s['artist']}  hash={s.get('hash','')[:10]}")
    lyrics = f._fetch_kugou_lyrics_krc(
        s.get("id", ""), s.get("hash", ""),
        s.get("title", ""), s.get("artist", "")
    )
    if lyrics:
        lrc_list = lyrics.get("lrc", [])
        words = lyrics.get("word_lyrics", [])
        print(f"lrc: {len(lrc_list)} 行, words: {len(words)} 个")
        if lrc_list:
            print(f"前3行: {[x['text'] for x in lrc_list[:3]]}")
        if words:
            print(f"前5字: {[x['text'] for x in words[:5]]}")
    else:
        print("返回 None")
else:
    print("没有酷狗结果")

print()
print("=== 网易云歌词获取 (旧API) ===")
lyrics = f._fetch_netease_lyrics_old("186016")
if lyrics:
    lrc_list = lyrics.get("lrc", [])
    words = lyrics.get("word_lyrics", [])
    has_ts = "tlyric" in lyrics
    has_roma = "romalrc" in lyrics
    print(f"lrc: {len(lrc_list)} 行, words: {len(words)} 个, 译文: {has_ts}, 罗马音: {has_roma}")
    if lrc_list:
        print(f"前3行: {[x['text'] for x in lrc_list[:3]]}")
else:
    print("返回 None")

print()
print("=== test passed ===")
