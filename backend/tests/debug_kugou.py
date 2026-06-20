"""调试Kugou v2 API返回的数据结构和歌词查询"""
import requests, sys, json
sys.path.insert(0, r"F:\PythonAPP\Self-service karaoke\backend\app")

# 1. 先搜索看v2 API返回什么
print("=== Kugou v2 API 原始响应 ===")
url = "http://songsearch.kugou.com/song_search_v2"
params = {"keyword": "Scream 〜万魔殿パンデモニウム：煉獄編〜", "page": 1, "pagesize": 10}
r = requests.get(url, params=params, timeout=8)
data = r.json()
lists = data.get("data", {}).get("lists", [])
if lists:
    first = lists[0]
    print("首条结果所有字段:")
    for k, v in first.items():
        print(f"  {k}: {v}")

    # 2. 测试直接用hash查歌词
    file_hash = first.get("FileHash", "")
    print(f"\n=== 用FileHash查询歌词: {file_hash} ===")
    
    # 方法1: 只用hash
    try:
        r2 = requests.get("https://lyrics.kugou.com/v1/search", 
                         params={"hash": file_hash, "keyword": first.get("SongName",""), 
                                 "lrctxt": "1", "man": "no"},
                         timeout=8)
        print(f"  仅用hash: HTTP {r2.status_code}")
        if r2.status_code == 200:
            j2 = r2.json()
            candidates = j2.get("candidates", [])
            print(f"  candidates: {len(candidates)}")
            if candidates:
                print(f"  首个: id={candidates[0].get('id')}, accesskey={candidates[0].get('accesskey')}")
    except Exception as e:
        print(f"  仅用hash失败: {e}")

    # 方法2: 用hash + keyword
    try:
        keyword = f"{first.get('SingerName','')} - {first.get('SongName','')}"
        r3 = requests.get("https://lyrics.kugou.com/v1/search",
                         params={"hash": file_hash, "keyword": keyword,
                                 "lrctxt": "1", "man": "no"},
                         timeout=8)
        print(f"  hash+keyword: HTTP {r3.status_code}")
        if r3.status_code == 200:
            j3 = r3.json()
            candidates = j3.get("candidates", [])
            print(f"  candidates: {len(candidates)}")
            if candidates:
                print(f"  首个: id={candidates[0].get('id')}, accesskey={candidates[0].get('accesskey')}")
    except Exception as e:
        print(f"  hash+keyword失败: {e}")
else:
    print("无结果")
