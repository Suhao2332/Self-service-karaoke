"""调试：酷狗歌词获取链路"""
import sys, json, hashlib, time
sys.path.insert(0, "F:\\PythonAPP\\Self-service karaoke\\backend\\app")
import base64, requests
from core.decryptor import krc_decrypt, parse_krc_text

session = requests.Session()
mid = hashlib.md5(str(int(time.time() * 1000)).encode()).hexdigest()

keyword = "周杰伦 - 青花瓷"
print("=== Test: 带 appid/clientver/signature 搜索 (仿LDDC) ===")
params = {
    "album_audio_id": "338778483",
    "hash": "55DCA7E63CA9D88F79E0B6411C048F1D",
    "keyword": keyword,
    "lrctxt": "1",
    "man": "no",
    "appid": "3116",
    "clientver": "11070",
}
sorted_items = sorted(params.items())
sorted_str = "".join([f"{k}={json.dumps(v) if isinstance(v, dict) else v}" for k, v in sorted_items])
sign_src = "LnT6xpN3khm36zse0QzvmgTZ3waWdRSA" + sorted_str + "LnT6xpN3khm36zse0QzvmgTZ3waWdRSA"
params["signature"] = hashlib.md5(sign_src.encode()).hexdigest()
headers = {
    "User-Agent": "Android14-1070-11070-201-0-Lyric-wifi",
    "KG-Rec": "1", "KG-RC": "1", "mid": mid,
}
resp = session.get("https://lyrics.kugou.com/v1/search", params=params, headers=headers, timeout=8)
print(f"Status: {resp.status_code}")
txt = resp.text
print(f"Body长度: {len(txt)}")
print(f"Body前200: {txt[:200]}")
if txt.strip():
    data = resp.json()
    cans = data.get("candidates", [])
    print(f"候选: {len(cans)}")
    if cans:
        c = cans[0]
        lyric_id = c.get("id")
        accesskey = c.get("accesskey")
        print(f"id={lyric_id}, accesskey={accesskey}")
        
        # 下载 KRC
        print("\n=== 下载KRC ===")
        dl_params = {"accesskey": accesskey, "charset": "utf8", "client": "mobi", "fmt": "krc", "id": lyric_id, "ver": "1"}
        dl_resp = session.get("http://lyrics.kugou.com/download", params=dl_params, timeout=8)
        print(f"Status: {dl_resp.status_code}")
        dl_data = dl_resp.json()
        content = dl_data.get("content", "")
        print(f"content长度: {len(content)}")
        if content:
            raw = base64.b64decode(content)
            print(f"raw前16字节: {raw[:16].hex()}")
            dec = krc_decrypt(raw)
            if dec:
                print(f"解密成功! 前200: {dec[:200]}")
            else:
                print("解密失败")
