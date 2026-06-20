"""测试酷狗 KRC 罗马音/译文提取"""
import sys
sys.path.insert(0, "F:\\PythonAPP\\Self-service karaoke\\backend\\app")
from core.lyrics_fetcher import LyricsFetcher

f = LyricsFetcher()

print("=== 测试：ちるちる - Reol (酷狗) ===")
results = f._search_kugou("ちるちる Reol")
kugou_songs = results
if kugou_songs:
    s = kugou_songs[0]
    print(f"选择: {s['title']} / {s['artist']}")

    lyrics = f._fetch_kugou_lyrics_krc(
        s.get("id", ""), s.get("hash", ""),
        s.get("title", ""), s.get("artist", "")
    )
    if lyrics:
        has_roma = "romalrc" in lyrics and lyrics["romalrc"]
        has_ts = "tlyric" in lyrics and lyrics["tlyric"]
        print(f"lrc: {len(lyrics.get('lrc',[]))}行")
        print(f"word_lyrics: {len(lyrics.get('word_lyrics',[]))}字")
        print(f"罗马音: {has_roma} ({len(lyrics.get('romalrc',[]))}行)")
        print(f"译文: {has_ts} ({len(lyrics.get('tlyric',[]))}行)")
        if has_roma:
            print(f"romalrc前3: {lyrics['romalrc'][:3]}")
        if has_ts:
            print(f"tlyric前3: {lyrics['tlyric'][:3]}")
    else:
        print("lyrics=None")
else:
    print("no results")

print()
print("=== 测试：Lemon - 米津玄师 (酷狗) ===")
results2 = f._search_kugou("Lemon 米津玄师")
if results2:
    s2 = results2[0]
    print(f"选择: {s2['title']}")
    lyrics2 = f._fetch_kugou_lyrics_krc(
        s2.get("id", ""), s2.get("hash", ""),
        s2.get("title", ""), s2.get("artist", "")
    )
    if lyrics2:
        has_roma = "romalrc" in lyrics2 and lyrics2["romalrc"]
        has_ts = "tlyric" in lyrics2 and lyrics2["tlyric"]
        print(f"lrc: {len(lyrics2.get('lrc',[]))}行, 罗马音: {has_roma} ({len(lyrics2.get('romalrc',[]))}行), 译文: {has_ts} ({len(lyrics2.get('tlyric',[]))}行)")
        if has_roma:
            print(f"romalrc前3: {lyrics2['romalrc'][:3]}")
        if has_ts:
            print(f"tlyric前3: {lyrics2['tlyric'][:3]}")
