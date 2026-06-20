"""测试特定歌曲搜索"""
import sys
sys.path.insert(0, r"F:\PythonAPP\Self-service karaoke\backend\app")

from core.lyrics_fetcher import LyricsFetcher

f = LyricsFetcher()

# 用户测试用例
title = "Scream 〜万魔殿パンデモニウム：煉獄編〜"
artist = "祖堅正慶 / AKINO"

print(f"搜索: {title} — {artist}")
print("=" * 60)

results = f.search_all_sources(title, artist)

if not results:
    print("❌ 所有源均无结果")
else:
    for source, songs in results.items():
        print(f"\n[{source}] {len(songs)} 首:")
        for i, s in enumerate(songs[:5]):
            print(f"  {i+1}. {s['title']} / {s['artist']}")

# 测试生成的关键词
print("\n\n生成的搜索关键词:")
keywords = f._generate_keywords(title, artist)
for k in keywords:
    print(f"  - {k}")
