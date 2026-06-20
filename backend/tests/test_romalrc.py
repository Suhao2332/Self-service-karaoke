"""测试罗马音歌词"""
import sys
sys.path.insert(0, "F:\\PythonAPP\\Self-service karaoke\\backend\\app")
from core.lyrics_fetcher import LyricsFetcher

f = LyricsFetcher()

# 找可能有罗马音的歌曲 (Lemon - 米津玄师)
results = f.search_all_sources("lemon", "米津玄师")

for src, songs in results.items():
    if not songs:
        continue
    s = songs[0]
    title = s.get("title", "?")
    artist = s.get("artist", "?")
    sid = s.get("id", "?")
    print(f"[{src}] {title} / {artist} id={sid[:20] if len(sid)>20 else sid}")

    if "网易" in src:
        lyrics = f._fetch_netease_lyrics_old(sid)
        if lyrics:
            has_roma = "romalrc" in lyrics and lyrics["romalrc"]
            has_ts = "tlyric" in lyrics and lyrics["tlyric"]
            print(f"  译文: {has_ts}, 罗马音: {has_roma}")
            if has_roma:
                print(f"  romalrc 前3行: {[(x['time'], x['text'][:20]) for x in lyrics['romalrc'][:3]]}")
        else:
            print("  lyrics = None")

print()
print("=== 测试有罗马音的ID ===")
# 用已知有罗马音的歌曲 (残酷な天使のテーゼ - 高橋洋子)
lyrics2 = f._fetch_netease_lyrics_old("461524")
if lyrics2:
    has_roma = "romalrc" in lyrics2 and lyrics2["romalrc"]
    has_ts = "tlyric" in lyrics2 and lyrics2["tlyric"]
    print(f"残酷な天使: 译文={has_ts}, 罗马音={has_roma}")
    if has_roma:
        print(f"  romalrc 前:{[(x['time'], x['text'][:20]) for x in lyrics2['romalrc'][:3]]}")
