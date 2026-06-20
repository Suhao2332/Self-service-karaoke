"""测试 QQ Music Lite API 搜索"""
import sys, json, random, time
sys.path.insert(0, "F:\\PythonAPP\\Self-service karaoke\\backend\\app")
import requests

comm = {
    "ct": 11, "cv": "1003006", "v": "1003006",
    "os_ver": "15", "phonetype": "24122RKC7C",
    "tmeAppID": "qqmusiclight", "nettype": "NETWORK_WIFI",
}
param = {
    "search_id": str(random.randint(1,20) * 18014398509481984 + round(time.time()*1000)%86400000),
    "remoteplace": "search.android.keyboard",
    "query": "青花瓷 周杰伦",
    "search_type": 0,
    "num_per_page": 10, "page_num": 1,
    "highlight": 0, "nqc_flag": 0, "page_id": 1, "grp": 1,
}
body = json.dumps({
    "comm": comm,
    "request": {
        "method": "DoSearchForQQMusicLite",
        "module": "music.search.SearchCgiService",
        "param": param,
    }
}, ensure_ascii=False, separators=(",", ":"))

resp = requests.post(
    "https://u.y.qq.com/cgi-bin/musicu.fcg",
    data=body.encode(),
    headers={
        "content-type": "application/json",
        "user-agent": "okhttp/3.14.9",
    },
    timeout=10
)
print("Status:", resp.status_code)
data = resp.json()
code = data.get("code", -1)
req_code = data.get("request", {}).get("code", -1)
print("Code:", code, "ReqCode:", req_code)

if code == 0:
    items = data.get("request", {}).get("data", {}).get("body", {}).get("item_song", [])
    print("Songs:", len(items))
    for item in items[:3]:
        singers = "/".join([s.get("name", "") for s in item.get("singer", [])])
        mid = item.get("mid", "")
        song_id = item.get("id", "")
        print(f"  title={item.get('title')} / {singers}  id={song_id}  mid={mid}")
else:
    print("Full response:", json.dumps(data, ensure_ascii=False)[:500])
