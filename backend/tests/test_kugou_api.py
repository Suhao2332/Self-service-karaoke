"""测试Kugou搜索API的不同端点"""
import requests
import sys
sys.path.insert(0, r"F:\PythonAPP\Self-service karaoke\backend\app")
from core.lyrics_fetcher import LyricsFetcher

# ========== 测试1: 用实际的用户用例测试LyricsFetcher ==========
print("=" * 60)
print("测试1: LyricsFetcher.search_all_sources")
print("=" * 60)

f = LyricsFetcher()
title = "Scream 〜万魔殿パンデモニウム：煉獄編〜"
artist = "祖堅正慶 / AKINO"

results = f.search_all_sources(title, artist)
for source, songs in results.items():
    print(f"\n[{source}] {len(songs)} 首:")
    for i, s in enumerate(songs[:5]):
        print(f"  {i+1}. {s['title']} / {s['artist']}")

# ========== 测试2: 直接调用不同的Kugou API端点 ==========
print("\n" + "=" * 60)
print("测试2: 直接测试Kugou API端点")
print("=" * 60)

def test_kugou_api(name, url, params, headers=None):
    try:
        r = requests.get(url, params=params, headers=headers or {}, timeout=8)
        if r.status_code != 200:
            print(f"  [{name}] HTTP {r.status_code}")
            return []
        data = r.json()
        songs = []
        # v2格式
        lists = data.get("data", {}).get("lists", [])
        if lists:
            for s in lists:
                songs.append(f"{s.get('SongName','?')} / {s.get('SingerName','?')}")
        # complexsearch格式
        lists2 = data.get("data", {}).get("lists", [])
        if lists2:
            for s in lists2:
                singers = s.get("Singers", [{}])
                singer_name = singers[0].get("name", "") if singers else ""
                songs.append(f"{s.get('SongName','?')} / {singer_name}")
        return songs
    except Exception as e:
        print(f"  [{name}] Error: {e}")
        return []

# 测试不同的关键词变体
keywords = [
    "Scream 祖堅正慶",
    "Scream 〜万魔殿パンデモニウム：煉獄編〜",
    "Scream 万魔殿パンデモニウム",
    "Scream",
]

for kw in keywords:
    print(f"\n关键词: {kw}")
    # API v2
    songs = test_kugou_api("v2", "http://songsearch.kugou.com/song_search_v2",
                           {"keyword": kw, "page": 1, "pagesize": 5})
    for s in songs[:3]:
        print(f"  v2: {s}")

    # API mobiles
    import random
    domain = random.choice(["mobiles.kugou.com", "msearchcdn.kugou.com"])
    songs2 = test_kugou_api("mobile", f"http://{domain}/api/v3/search/song",
                           {"keyword": kw, "page": 1, "pagesize": 5, "showtype": "14"})
    for s in songs2[:3]:
        print(f"  mobile: {s}")
