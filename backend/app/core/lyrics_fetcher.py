"""
歌词获取模块

多源歌词搜索：网易云音乐 + QQ音乐 + 酷狗音乐
支持获取译文 (translation) 和罗马音 (romanization)

解密逻辑移植自 LDDC (https://github.com/chenmozhijin/LDDC)
"""
import base64
import hashlib
import json
import random
import re
import time
from typing import Dict, List, Optional

import requests

from .decryptor import (
    krc_decrypt,
    parse_krc_text,
    parse_qrc_text,
    parse_yrc_text,
    qrc_decrypt,
    # EAPI
    eapi_params_encrypt,
    eapi_response_decrypt,
    eapi_get_anonimous_username,
)


class LyricsFetcher:
    """歌词获取器 — 支持多源并行搜索 + 译文/罗马音 + 加密歌词解密"""

    # ── 网易云 EAPI 常量 ──
    NE_DEVICE_ID = "".join(random.choice("0123456789abcdef") for _ in range(32))

    # 生成随机的 clientSign
    @staticmethod
    def _ne_gen_client_sign() -> str:
        import secrets
        mac = ":".join(f"{secrets.randbelow(255):02X}" for _ in range(6))
        rand_str = "".join(secrets.choice(
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ") for _ in range(8))
        hash_part = secrets.token_hex(32)
        return f"{mac}@@@{rand_str}@@@@@@{hash_part}"

    @staticmethod
    def _ne_build_cookies(device_id: str = "") -> dict:
        import random as _r
        did = device_id or ""
        return {
            "os": "pc",
            "deviceId": did,
            "osver": f"Microsoft-Windows-10--build-{_r.randint(200,300)}00-64bit",
            "clientSign": LyricsFetcher._ne_gen_client_sign(),
            "channel": "netease",
            "mode": _r.choice([
                "MS-iCraft B760M WIFI", "ASUS ROG STRIX Z790",
                "MSI MAG B550 TOMAHAWK", "ASRock X670E Taichi",
            ]),
            "appver": "3.1.3.203419",
        }

    _ne_clientsign = _ne_gen_client_sign()
    NE_COOKIES = {
        "os": "pc",
        "deviceId": NE_DEVICE_ID,
        "osver": "Microsoft-Windows-10--build-22600-64bit",
        "clientSign": _ne_clientsign,
        "channel": "netease",
        "appver": "3.1.3.203419",
    }
    NE_ANON_USER = None  # 缓存匿名用户信息

    def __init__(self):
        self.session = requests.Session()
        self.session.trust_env = False  # 禁用系统代理，避免企业代理干扰
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 '
                          '(KHTML, like Gecko) Safari/537.36 Chrome/91.0.4472.164 '
                          'NeteaseMusicDesktop/3.1.3.203419',
            'Referer': 'https://music.163.com'
        })
        self._init_ne_anon()

    # ════════════════════════════════════════════════════════════
    # 公开接口
    # ════════════════════════════════════════════════════════════

    def search_all_sources(self, title: str, artist: str = "") -> Dict[str, List[Dict]]:
        """并行搜索所有源，返回 {source: [songs]}"""
        results = {}
        per_source = {}
        keywords = self._generate_keywords(title, artist)

        for keyword in keywords:
            for src_name, search_func in [
                ("QQ音乐", self._search_qq_music),
                ("酷狗音乐", self._search_kugou),
                ("网易云音乐", self._search_netease_eapi),
            ]:
                if src_name in per_source:
                    continue
                try:
                    songs = search_func(keyword)
                    if songs:
                        per_source[src_name] = {"keyword": keyword, "songs": songs}
                except Exception as e:
                    print(f"[歌词] {src_name}搜索异常: {e}")

            if len(per_source) >= 3:
                break

        for src_name, data in per_source.items():
            results[src_name] = data["songs"]
        return results

    def _generate_keywords(self, title: str, artist: str) -> List[str]:
        """生成多种搜索关键词组合"""
        keywords = []
        keywords.append(title)
        keywords.append(f"{title} {artist}")
        clean_title = re.sub(r'[〜~\-：:、，。！？\u3000]', ' ', title).strip()
        clean_title = re.sub(r'\s+', ' ', clean_title)
        if clean_title != title:
            keywords.append(f"{clean_title} {artist}")
            keywords.append(clean_title)
        for sep in ['〜', '~', '：', ':']:
            if sep in title:
                parts = title.split(sep, 1)
                if parts[0].strip() not in keywords:
                    keywords.append(parts[0].strip())
        if artist and artist != "未知":
            main_artist = artist.split("/")[0].strip()
            if main_artist:
                keywords.append(main_artist)
        seen = set()
        unique = []
        for k in keywords:
            k = k.strip()
            if k and k not in seen:
                seen.add(k)
                unique.append(k)
        return unique

    def search_song(self, title: str, artist: str = "") -> List[Dict]:
        """兼容旧接口：合并所有源结果"""
        all_results = self.search_all_sources(title, artist)
        merged = []
        for source, songs in all_results.items():
            for s in songs:
                s_copy = dict(s)
                s_copy["source"] = source
                merged.append(s_copy)
        return merged

    def fetch_lyrics(self, song_id: str, source: str = "netease",
                     extra: Optional[Dict] = None) -> Optional[Dict]:
        """
        获取歌词（含译文和罗马音），优先获取逐字歌词

        Args:
            song_id: 歌曲ID
            source: 来源 ("netease"/"qqmusic"/"kugou")
            extra: 额外参数（酷狗需要 hash/title/artist）

        Returns:
            { "lrc": [...], "word_lyrics": [...], "raw_lrc": "...",
              "tlyric": [...], "raw_tlyric": "...",
              "romalrc": [...], "raw_romalrc": "..." }
        """
        source_map = {
            "netease": "netease", "网易云音乐": "netease",
            "qqmusic": "qqmusic", "QQ音乐": "qqmusic",
            "kugou": "kugou", "酷狗音乐": "kugou",
        }
        s = source_map.get(source, "netease")
        extra = extra or {}

        if s == "netease":
            return self._fetch_netease_lyrics_eapi(song_id)
        elif s == "qqmusic":
            return self._fetch_qq_lyrics_qrc(song_id, extra=extra)
        elif s == "kugou":
            return self._fetch_kugou_lyrics_krc(
                song_id, extra.get("hash", ""),
                extra.get("title", ""), extra.get("artist", "")
            )
        return None

    def get_word_timeline(self, song_id: str, source: str = "netease",
                          extra: Optional[Dict] = None) -> List[Dict]:
        """获取逐词时间轴"""
        lyrics_data = self.fetch_lyrics(song_id, source, extra)
        if not lyrics_data:
            return []

        if lyrics_data.get("word_lyrics"):
            return lyrics_data["word_lyrics"]

        return self._generate_word_timeline(lyrics_data.get("lrc", []))

    # ════════════════════════════════════════════════════════════
    # 网易云音乐 — EAPI 加密搜索 + 获取
    # ════════════════════════════════════════════════════════════

    def _init_ne_anon(self):
        """初始化网易云匿名用户（EAPI 需要）"""
        if LyricsFetcher.NE_ANON_USER is not None:
            return
        # 先标记为失败，避免重复尝试
        LyricsFetcher.NE_ANON_USER = False
        try:
            path = "/eapi/register/anonimous"
            cl_sign = self._ne_gen_client_sign()
            headers = {
                "clientSign": cl_sign,
                "os": self.NE_COOKIES["os"],
                "appver": self.NE_COOKIES["appver"],
                "deviceId": self.NE_COOKIES["deviceId"],
                "requestId": 0,
                "osver": self.NE_COOKIES["osver"],
            }
            params = {
                "username": eapi_get_anonimous_username(self.NE_DEVICE_ID),
                "e_r": True,
                "header": json.dumps(headers, separators=(',', ':')),
            }
            encrypted = eapi_params_encrypt(path.replace("eapi", "api"), params)
            resp = self.session.post(
                "https://interface.music.163.com" + path,
                headers={
                    "accept": "*/*",
                    "content-type": "application/x-www-form-urlencoded",
                    "origin": "orpheus://orpheus",
                    "user-agent": self.session.headers.get("User-Agent", ""),
                },
                data=encrypted,
                timeout=10,
            )
            if resp.status_code == 200:
                data = eapi_response_decrypt(resp.content)
                if data.get("code") == 200:
                    LyricsFetcher.NE_ANON_USER = {
                        "user_id": data.get("userId"),
                        "expire": int(time.time()) + 864000,
                    }
                    # 记录 cookies
                    for k, v in resp.cookies.items():
                        self.session.cookies.set(k, v)
        except Exception:
            print("[歌词] 网易云EAPI匿名登录失败，将使用旧API")
            # NE_ANON_USER = False already set above

    def _ne_eapi_request(self, path: str, params: dict) -> Optional[dict]:
        """通过 EAPI 请求网易云接口"""
        params["e_r"] = True
        params["header"] = json.dumps({
            "os": self.NE_COOKIES["os"],
            "appver": self.NE_COOKIES["appver"],
            "deviceId": self.NE_COOKIES["deviceId"],
            "clientSign": self.NE_COOKIES.get("clientSign", ""),
            "requestId": 0,
            "osver": self.NE_COOKIES["osver"],
        }, separators=(',', ':'))

        encrypted = eapi_params_encrypt(path.replace("eapi", "api"), params)

        try:
            resp = self.session.post(
                "https://interface.music.163.com" + path,
                headers={
                    "accept": "*/*",
                    "content-type": "application/x-www-form-urlencoded",
                    "origin": "orpheus://orpheus",
                    "user-agent": self.session.headers.get("User-Agent", ""),
                },
                data=encrypted,
                timeout=10,
            )
            if resp.status_code != 200:
                return None
            return eapi_response_decrypt(resp.content)
        except Exception:
            return None

    def _search_netease_eapi(self, keyword: str) -> List[Dict]:
        """EAPI 搜索网易云音乐（更可靠），失败回退到旧API"""
        # 如果 EAPI 未初始化成功，直接走旧API节省时间
        if not isinstance(LyricsFetcher.NE_ANON_USER, dict):
            return self._search_netease_old(keyword)

        params = {
            "keyword": keyword,
            "limit": "20",
            "offset": "0",
            "scene": "NORMAL",
            "needCorrect": "true",
        }
        data = self._ne_eapi_request("/eapi/search/song/list/page", params)
        if not data or data.get("code") != 200:
            return self._search_netease_old(keyword)

        songs = []
        resources = data.get("data", {}).get("resources", [])
        for song in resources:
            info = song.get("baseInfo", {}).get("simpleSongData", {})
            if not info:
                continue
            artists = " / ".join([a.get("name", "") for a in info.get("ar", [])])
            title = info.get("name", "")
            artist_m = self._match_score(artists, keyword)
            title_m = self._match_score(title, keyword)
            songs.append({
                "id": str(info.get("id", "")),
                "title": title,
                "artist": artists,
                "album": info.get("al", {}).get("name", ""),
                "_score": max(title_m, artist_m * 0.8),
            })

        songs.sort(key=lambda x: x["_score"], reverse=True)
        return songs

    def _search_netease_old(self, keyword: str) -> List[Dict]:
        """旧API搜索网易云音乐（备用）"""
        url = "https://music.163.com/api/search/get"
        params = {"s": keyword, "type": 1, "offset": 0, "limit": 15}
        try:
            resp = self.session.get(url, params=params, timeout=5)
            if resp.status_code != 200:
                return []
            data = resp.json()
            songs = []
            for song in data.get("result", {}).get("songs", []):
                artists = " / ".join([a["name"] for a in song.get("artists", [])])
                title_m = self._match_score(song["name"], keyword)
                artist_m = self._match_score(artists, keyword)
                songs.append({
                    "id": str(song["id"]),
                    "title": song["name"],
                    "artist": artists,
                    "album": song.get("album", {}).get("name", ""),
                    "_score": max(title_m, artist_m * 0.8),
                })
            songs.sort(key=lambda x: x["_score"], reverse=True)
            return songs
        except Exception:
            return []

    def _fetch_netease_lyrics_eapi(self, song_id: str) -> Optional[Dict]:
        """
        通过 EAPI 获取网易云歌词（含逐字、译文、罗马音）
        """
        # EAPI 未初始化成功时直接走旧API
        if not isinstance(LyricsFetcher.NE_ANON_USER, dict):
            return self._fetch_netease_lyrics_old(song_id)

        params = {"id": int(song_id), "lv": "-1", "tv": "-1", "rv": "-1", "yv": "-1"}
        data = self._ne_eapi_request("/eapi/song/lyric/v1", params)

        # EAPI 失败时回退到旧API
        if not data or data.get("code") != 200:
            return self._fetch_netease_lyrics_old(song_id)

        result = {}

        # 逐字歌词优先 (yrc)
        word_lyrics = []
        if "yrc" in data and data["yrc"].get("lyric"):
            word_lyrics = parse_yrc_text(data["yrc"]["lyric"])
        # 备选逐词歌词 (klyric)
        if not word_lyrics and "klyric" in data and data["klyric"].get("lyric"):
            word_lyrics = self._parse_word_lyrics(data["klyric"]["lyric"])

        # 原文 LRC
        lrc_text = ""
        if "lrc" in data and "lyric" in data["lrc"]:
            lrc_text = data["lrc"]["lyric"]

        # 译文
        tlyric_text = ""
        if "tlyric" in data and "lyric" in data["tlyric"]:
            tlyric_text = data["tlyric"]["lyric"]
            if tlyric_text.strip() in ("", "[00:00.00]纯音乐，请欣赏"):
                tlyric_text = ""

        # 罗马音
        romalrc_text = ""
        if "romalrc" in data and "lyric" in data["romalrc"]:
            romalrc_text = data["romalrc"]["lyric"]
            if romalrc_text.strip() in ("", "[00:00.00]纯音乐，请欣赏"):
                romalrc_text = ""

        lrc_lyrics = self._parse_lrc_lyrics(lrc_text)
        tlyric_lyrics = self._parse_lrc_lyrics(tlyric_text) if tlyric_text else []
        romalrc_lyrics = self._parse_lrc_lyrics(romalrc_text) if romalrc_text else []

        result = {
            "lrc": lrc_lyrics,
            "word_lyrics": word_lyrics,
            "raw_lrc": lrc_text,
        }
        if tlyric_lyrics:
            result["tlyric"] = tlyric_lyrics
            result["raw_tlyric"] = tlyric_text
        if romalrc_lyrics:
            result["romalrc"] = romalrc_lyrics
            result["raw_romalrc"] = romalrc_text

        return result

    def _fetch_netease_lyrics_old(self, song_id: str) -> Optional[Dict]:
        """旧API获取网易云歌词（备用）"""
        url = f"https://music.163.com/api/song/lyric?id={song_id}&lv=-1&kv=-1&tv=-1&rv=-1&yv=-1"
        try:
            resp = self.session.get(url, timeout=10)
            if resp.status_code != 200:
                return None
            data = resp.json()
        except Exception:
            return None

        lrc_text = data.get("lrc", {}).get("lyric", "")

        # 逐词歌词
        word_lyrics = []
        if "klyric" in data and "lyric" in data["klyric"]:
            word_lyrics = self._parse_word_lyrics(data["klyric"]["lyric"])
        elif "yrc" in data and "lyric" in data["yrc"]:
            word_lyrics = parse_yrc_text(data["yrc"]["lyric"])

        tlyric_text = ""
        if "tlyric" in data and "lyric" in data["tlyric"]:
            tlyric_text = data["tlyric"]["lyric"]
            if tlyric_text.strip() in ("", "[00:00.00]纯音乐，请欣赏"):
                tlyric_text = ""

        romalrc_text = ""
        if "romalrc" in data and "lyric" in data["romalrc"]:
            romalrc_text = data["romalrc"]["lyric"]
            if romalrc_text.strip() in ("", "[00:00.00]纯音乐，请欣赏"):
                romalrc_text = ""

        lrc_lyrics = self._parse_lrc_lyrics(lrc_text)
        tlyric_lyrics = self._parse_lrc_lyrics(tlyric_text) if tlyric_text else []
        romalrc_lyrics = self._parse_lrc_lyrics(romalrc_text) if romalrc_text else []

        result = {
            "lrc": lrc_lyrics,
            "word_lyrics": word_lyrics,
            "raw_lrc": lrc_text,
        }
        if tlyric_lyrics:
            result["tlyric"] = tlyric_lyrics
            result["raw_tlyric"] = tlyric_text
        if romalrc_lyrics:
            result["romalrc"] = romalrc_lyrics
            result["raw_romalrc"] = romalrc_text
        return result

    # ════════════════════════════════════════════════════════════
    # QQ音乐 — QRC 解密获取逐字歌词
    # ════════════════════════════════════════════════════════════

    def _search_qq_music(self, keyword: str) -> List[Dict]:
        """搜索QQ音乐 — 使用 QQ Music Lite API（u.y.qq.com）"""
        comm = {
            "ct": 11, "cv": "1003006", "v": "1003006",
            "os_ver": "15", "phonetype": "24122RKC7C",
            "tmeAppID": "qqmusiclight", "nettype": "NETWORK_WIFI",
        }
        param = {
            "search_id": str(random.randint(1, 20) * 18014398509481984
                             + round(time.time() * 1000) % 86400000),
            "remoteplace": "search.android.keyboard",
            "query": keyword,
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
        try:
            resp = self.session.post(
                "https://u.y.qq.com/cgi-bin/musicu.fcg",
                data=body.encode(),
                headers={"content-type": "application/json",
                         "user-agent": "okhttp/3.14.9"},
                timeout=8,
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
            if data.get("code") != 0:
                return []
            items = data.get("request", {}).get("data", {}).get("body", {}).get("item_song", [])
            songs = []
            for item in items:
                singers = "/".join([s.get("name", "") for s in item.get("singer", [])])
                songs.append({
                    "id": item.get("mid", ""),           # songmid (字母ID)
                    "title": item.get("title", ""),
                    "subtitle": item.get("subtitle", ""),
                    "artist": singers,
                    "album": item.get("album", {}).get("name", ""),
                    "songid": str(item.get("id", "")),   # 数字ID（歌词API需要）
                    "duration": int(item.get("interval", 0) * 1000),  # 毫秒
                })
            return songs
        except Exception:
            return []

    def _fetch_qq_lyrics_qrc(self, song_mid: str, extra: Optional[Dict] = None) -> Optional[Dict]:
        """
        获取QQ音乐歌词 — 优先使用 QRC 逐字格式
        extra 应包含: songid(数字ID), title, artist, album, duration(毫秒)
        """
        extra = extra or {}
        song_id = extra.get("songid", "")
        title = extra.get("title", "")
        artist = extra.get("artist", "")
        album = extra.get("album", "")
        duration = extra.get("duration", 0)

        # 如果有完整信息，直接调用 QRC API
        if song_id and title:
            qrc_result = self._fetch_qq_qrc_api(
                song_mid, song_id, title, artist, album, duration)
            if qrc_result:
                return qrc_result

        # 回退：旧API获取 base64 LRC
        return self._fetch_qq_lyrics_base64(song_mid)

    def _get_qq_song_info(self, song_mid: str) -> Optional[Dict]:
        """通过 QQ Music API 获取歌曲详细信息（数字ID、时长、专辑等）"""
        # 使用歌曲详情接口
        url = "https://u.y.qq.com/cgi-bin/musicu.fcg"
        data = json.dumps({
            "comm": {"ct": 11, "cv": "1003006", "v": "1003006",
                     "tmeAppID": "qqmusiclight", "nettype": "NETWORK_WIFI"},
            "request": {
                "method": "GetMusicInfoBySongMid",
                "module": "music.musichallSong.SongDataInfo",
                "param": {"songMid": song_mid},
            },
        }, ensure_ascii=False, separators=(",", ":"))

        try:
            resp = self.session.post(url, data=data.encode(),
                                     headers={"content-type": "application/json",
                                              "user-agent": "okhttp/3.14.9"},
                                     timeout=10)
            if resp.status_code != 200:
                return None
            resp_data = resp.json()
            req_data = resp_data.get("request", {}).get("data", {})
            if not req_data:
                return None

            singers = req_data.get("singer", [])
            artist = " / ".join([s.get("name", "") for s in singers if s.get("name")])

            return {
                "id": str(req_data.get("id", "")),
                "mid": song_mid,
                "title": req_data.get("title", ""),
                "artist": artist,
                "album": req_data.get("album", {}).get("name", ""),
                "duration": req_data.get("interval", 0) * 1000,
            }
        except Exception:
            return None

    def _fetch_qq_qrc_api(self, song_mid: str, song_id: str, title: str,
                          artist: str, album: str, duration: int) -> Optional[Dict]:
        """
        通过 QQ Music Lite / PlayLyricInfo 接口获取 QRC 加密歌词

        LDDC 逆向的 API 参数:
          crypt=1, qrc=1, trans=1, roma=1
          albumName/singerName/songName 都 base64 编码
        """
        from base64 import b64encode

        if not song_id or not title:
            return None

        # 获取 session（复用或有缓存）
        session_info = self._get_qq_session()
        if not session_info:
            return None

        comm = {
            "ct": 11, "cv": "1003006", "v": "1003006",
            "os_ver": "15", "phonetype": "24122RKC7C",
            "tmeAppID": "qqmusiclight",
            "nettype": "NETWORK_WIFI",
            "uid": session_info.get("uid", "0"),
            "sid": session_info.get("sid", ""),
            "userip": session_info.get("userip", ""),
        }

        param = {
            "albumName": b64encode(album.encode()).decode() if album else b64encode(b"").decode(),
            "crypt": 1,
            "ct": 19,
            "cv": 2111,
            "interval": duration // 1000 if duration else 0,
            "lrc_t": 0,
            "qrc": 1,
            "qrc_t": 0,
            "roma": 1,
            "roma_t": 0,
            "singerName": b64encode(artist.encode()).decode() if artist else b64encode(b"").decode(),
            "songID": int(song_id),
            "songName": b64encode(title.encode()).decode(),
            "trans": 1,
            "trans_t": 0,
            "type": 0,
        }

        request_body = json.dumps({
            "comm": comm,
            "request": {
                "method": "GetPlayLyricInfo",
                "module": "music.musichallSong.PlayLyricInfo",
                "param": param,
            },
        }, ensure_ascii=False, separators=(",", ":"))

        try:
            resp = self.session.post(
                "https://u.y.qq.com/cgi-bin/musicu.fcg",
                data=request_body.encode("utf-8"),
                headers={
                    "content-type": "application/json",
                    "accept-encoding": "gzip",
                    "user-agent": "okhttp/3.14.9",
                },
                timeout=15,
            )
            if resp.status_code != 200:
                return None

            resp_data = resp.json()
            if resp_data.get("code") != 0:
                return None

            lyric_data = resp_data.get("request", {}).get("data", {})
            result = {}

            # 原文 QRC
            qrc = lyric_data.get("lyric", "")
            qrc_t = lyric_data.get("qrc_t") or lyric_data.get("lrc_t", "0")
            if qrc and qrc_t != "0":
                decrypted = qrc_decrypt(qrc)
                if decrypted:
                    _, lrc_lines, word_lyrics = parse_qrc_text(decrypted)
                    if word_lyrics:
                        result["word_lyrics"] = word_lyrics
                    if lrc_lines:
                        result["lrc"] = lrc_lines
                        result["raw_lrc"] = self._words_to_lrc_text(word_lyrics) if word_lyrics else ""

            # 译文
            trans = lyric_data.get("trans", "")
            trans_t = lyric_data.get("trans_t", "0")
            if trans and trans_t != "0":
                decrypted = qrc_decrypt(trans)
                if decrypted:
                    _, ts_lines, _ = parse_qrc_text(decrypted)
                    if ts_lines:
                        # 译文行的时间与原文对齐
                        result["tlyric"] = [{"time": l["time"], "text": l["text"]} for l in ts_lines]
                        result["raw_tlyric"] = "\n".join(
                            f"[{int(l['time'])//60:02d}:{int(l['time'])%60:02d}.{int((l['time']%1)*100):02d}] {l['text']}"
                            for l in ts_lines
                        )

            # 罗马音
            roma = lyric_data.get("roma", "")
            roma_t = lyric_data.get("roma_t", "0")
            if roma and roma_t != "0":
                decrypted = qrc_decrypt(roma)
                if decrypted:
                    _, roma_lines, roma_words = parse_qrc_text(decrypted)
                    if roma_lines:
                        # 行文本：逐词用空格分隔，这样 ASS \kf 能逐音节填充
                        result["romalrc"] = [
                            {"time": l["time"],
                             "text": " ".join(w["text"] for w in l.get("words", l["text"].split()))
                             if l.get("words") else l["text"]}
                            for l in roma_lines
                        ]
                        result["raw_romalrc"] = "\n".join(
                            f"[{int(l['time'])//60:02d}:{int(l['time'])%60:02d}.{int((l['time']%1)*100):02d}] "
                            f"{result['romalrc'][i]['text']}"
                            for i, l in enumerate(roma_lines)
                        )
                    if roma_words:
                        result["romalrc_words"] = roma_words

            # 备用：从 word_lyrics 生成 LRC
            if result.get("word_lyrics") and not result.get("lrc"):
                result["lrc"] = self._words_to_lrc(result["word_lyrics"])
                result["raw_lrc"] = self._words_to_lrc_text(result["word_lyrics"])

            if result.get("word_lyrics") or result.get("lrc"):
                return result

        except Exception as e:
            print(f"[歌词] QQ QRC API 调用失败: {e}")

        return None

    def _get_qq_session(self) -> Optional[Dict]:
        """获取 QQ Music API session"""
        try:
            data = json.dumps({
                "comm": {
                    "ct": 11, "cv": "1003006", "v": "1003006",
                    "tmeAppID": "qqmusiclight", "nettype": "NETWORK_WIFI",
                },
                "request": {
                    "method": "GetSession",
                    "module": "music.getSession.session",
                    "param": {"caller": 0, "uid": "0", "vkey": 0},
                },
            }, separators=(",", ":"))

            resp = self.session.post(
                "https://u.y.qq.com/cgi-bin/musicu.fcg",
                data=data.encode("utf-8"),
                headers={"content-type": "application/json",
                         "user-agent": "okhttp/3.14.9"},
                timeout=10,
            )
            if resp.status_code != 200:
                return None
            resp_data = resp.json()
            return resp_data.get("request", {}).get("data", {}).get("session")
        except Exception:
            return None

    def _qrc_to_lrc_text(self, qrc_xml: str) -> str:
        """将 QRC XML 内容转为标准 LRC 文本（用于译文/罗马音）"""
        import re as _re
        match = _re.search(r'<Lyric_1 LyricType="1" LyricContent="(?P<content>.*?)"/>', qrc_xml, _re.DOTALL)
        if not match:
            return ""

        lines = []
        for raw_line in match.group("content").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            line_match = re.match(r"^\[(\d+),(\d+)\](.*)$", line)
            if line_match:
                start_ms = int(line_match.group(1))
                minutes = start_ms // 60000
                seconds = (start_ms % 60000) // 1000
                millis = start_ms % 1000
                content = line_match.group(3)
                # 去除逐字时间戳
                content = re.sub(r'\(\d+,\d+\)', '', content)
                lines.append(f"[{minutes:02d}:{seconds:02d}.{millis:02d}] {content.strip()}")
            elif re.match(r"^\[\w+:", line):
                lines.append(line)
        return "\n".join(lines)

    def _words_to_lrc(self, word_timeline: List[Dict]) -> List[Dict]:
        """从逐字时间轴生成 LRC 行列表"""
        if not word_timeline:
            return []

        # 按行分组
        lines = []
        current_line = {"start": word_timeline[0]["start"], "text": ""}
        gap_threshold = 0.3  # 字间隔 >0.3秒视为换行

        for w in word_timeline:
            if current_line["text"]:
                # current_line["end"] 保存了上一轮最后一个字的结束时间
                if w["start"] - current_line["end"] > gap_threshold:
                    # 新行：current_line 的 end 已是正确值，直接保存
                    lines.append(current_line)
                    current_line = {"start": w["start"], "text": w["text"]}
                else:
                    current_line["text"] += w["text"]
            else:
                current_line["text"] = w["text"]
            current_line["end"] = w["end"]

        if current_line["text"]:
            lines.append(current_line)

        return [{"time": l["start"], "text": l["text"]} for l in lines]

    def _words_to_lrc_text(self, word_timeline: List[Dict]) -> str:
        """从逐字时间轴生成 LRC 文本"""
        lrc_lines = self._words_to_lrc(word_timeline)
        lines = []
        for l in lrc_lines:
            minutes = int(l["time"]) // 60
            seconds = int(l["time"]) % 60
            millis = int((l["time"] - int(l["time"])) * 100)
            lines.append(f"[{minutes:02d}:{seconds:02d}.{millis:02d}] {l['text']}")
        return "\n".join(lines)

    def _fetch_qq_lyrics_base64(self, song_mid: str) -> Optional[Dict]:
        """旧API：base64 LRC（备用）"""
        url = "https://c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg"
        params = {"songmid": song_mid, "format": "json"}
        headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://y.qq.com'}
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            if resp.status_code != 200:
                return None
            data = resp.json()
        except Exception:
            return None

        result = {}
        if "lyric" in data:
            lrc_text = base64.b64decode(data["lyric"]).decode('utf-8')
            result["lrc"] = self._parse_lrc_lyrics(lrc_text)
            result["raw_lrc"] = lrc_text
        if "trans" in data:
            try:
                trans_text = base64.b64decode(data["trans"]).decode('utf-8')
                trans_lyrics = self._parse_lrc_lyrics(trans_text)
                if trans_lyrics:
                    result["tlyric"] = trans_lyrics
                    result["raw_tlyric"] = trans_text
            except Exception:
                pass
        if "roma" in data:
            try:
                roma_text = base64.b64decode(data["roma"]).decode('utf-8')
                roma_lyrics = self._parse_lrc_lyrics(roma_text)
                if roma_lyrics:
                    result["romalrc"] = roma_lyrics
                    result["raw_romalrc"] = roma_text
            except Exception:
                pass
        return result if result.get("lrc") else None

    # ════════════════════════════════════════════════════════════
    # 酷狗音乐 — KRC 解密获取逐字歌词
    # ════════════════════════════════════════════════════════════

    def _search_kugou(self, keyword: str) -> List[Dict]:
        """搜索酷狗音乐"""
        url = "http://songsearch.kugou.com/song_search_v2"
        params = {"keyword": keyword, "page": 1, "pagesize": 10}
        try:
            resp = requests.get(url, params=params, timeout=8)
            if resp.status_code != 200:
                return self._search_kugou_fallback(keyword)
            data = resp.json()
            songs = []
            for info in data.get("data", {}).get("lists", []):
                songs.append({
                    "id": str(info.get("ID", info.get("MixSongID", ""))),
                    "hash": info.get("FileHash", ""),
                    "album_audio_id": str(info.get("Audioid", info.get("ID", ""))),
                    "title": info.get("SongName", ""),
                    "artist": info.get("SingerName", ""),
                    "album": info.get("AlbumName", ""),
                    "duration": info.get("Duration", 0),
                })
            return songs
        except Exception as e:
            print(f"[歌词] 酷狗v2搜索异常: {e}")
            return self._search_kugou_fallback(keyword)

    def _search_kugou_fallback(self, keyword: str) -> List[Dict]:
        """酷狗搜索备用"""
        domain = random.choice([
            "mobiles.kugou.com", "msearchcdn.kugou.com",
            "mobilecdnbj.kugou.com", "msearch.kugou.com"
        ])
        url = f"http://{domain}/api/v3/search/song"
        params = {
            "showtype": "14", "highlight": "", "pagesize": "10",
            "tag_aggr": "1", "plat": "0", "sver": "5",
            "keyword": keyword, "correct": "1", "api_ver": "1",
            "version": "9108", "page": "1"
        }
        try:
            resp = requests.get(url, params=params, timeout=8)
            if resp.status_code != 200:
                return []
            data = resp.json()
            songs = []
            for info in data.get("data", {}).get("info", []):
                songs.append({
                    "id": str(info.get("album_audio_id", "")),
                    "hash": info.get("hash", ""),
                    "title": info.get("songname", ""),
                    "artist": info.get("singername", ""),
                    "album": info.get("album_name", ""),
                    "duration": info.get("duration", 0),
                })
            return songs
        except Exception:
            return []

    def _search_kugou_v2(self, keyword: str) -> List[Dict]:
        """酷狗 v2 API 搜索（带签名）"""
        import hashlib
        mid = hashlib.md5(str(int(time.time() * 1000)).encode()).hexdigest()
        url = "http://complexsearch.kugou.com/v2/search/song"
        params = {
            "keyword": keyword, "page": 1, "pagesize": 10, "sorttype": "0",
            "userid": "0", "appid": "3116", "token": "",
            "clienttime": int(time.time()), "iscorrection": "1",
            "uuid": "-", "mid": mid, "dfid": "-", "clientver": "11070",
            "platform": "AndroidFilter",
        }
        sign_src = ("LnT6xpN3khm36zse0QzvmgTZ3waWdRSA"
                    + "".join(sorted(f"{k}={v}" for k, v in params.items()))
                    + "LnT6xpN3khm36zse0QzvmgTZ3waWdRSA")
        params["signature"] = hashlib.md5(sign_src.encode()).hexdigest()
        headers = {"KG-Rec": "1", "KG-RC": "1", "mid": mid,
                   "x-router": "complexsearch.kugou.com",
                   "User-Agent": "Android14-1070-11070-201-0-SearchSong-wifi"}
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=8)
            if resp.status_code != 200:
                return []
            data = resp.json()
            songs = []
            for info in data.get("data", {}).get("lists", []):
                songs.append({
                    "id": str(info.get("ID", "")),
                    "hash": info.get("FileHash", ""),
                    "title": info.get("SongName", ""),
                    "artist": " / ".join(s.get("name", "") for s in info.get("Singers", []) if s.get("name")),
                    "album": info.get("AlbumName", ""),
                    "duration": info.get("Duration", 0) * 1000,
                })
            return songs
        except Exception:
            return []

    def _fetch_kugou_lyrics_krc(self, song_id: str, song_hash: str = "",
                                 title: str = "", artist: str = "") -> Optional[Dict]:
        """
        获取酷狗歌词 — 优先使用 KRC 格式解密

        算法（来自 LDDC）:
          1. 请求 fmt=krc 获取 KRC 加密数据
          2. 跳过前4字节头
          3. XOR 解密: data[i] ^= KRC_KEY[i % len(KRC_KEY)]
          4. zlib.decompress
          5. 解析 KRC 格式获取逐字时间轴

        回退：fmt=lrc 纯文本
        """
        # 构造带签名的请求（LDDC 逆向的酷狗 API 认证）
        search_url = "https://lyrics.kugou.com/v1/search"
        keyword = f"{artist} - {title}" if artist else title
        params = {
            "keyword": keyword, "lrctxt": "1", "man": "no",
            "appid": "3116", "clientver": "11070",
        }
        # 只在有值时加入 hash/ID，避免空值干扰
        if song_id:
            params["album_audio_id"] = song_id
        if song_hash:
            params["hash"] = song_hash
        # 计算签名
        sorted_str = "".join(
            f"{k}={json.dumps(v) if isinstance(v, dict) else v}"
            for k, v in sorted(params.items())
        )
        sign_src = "LnT6xpN3khm36zse0QzvmgTZ3waWdRSA" + sorted_str + "LnT6xpN3khm36zse0QzvmgTZ3waWdRSA"
        params["signature"] = hashlib.md5(sign_src.encode()).hexdigest()

        mid = hashlib.md5(str(int(time.time() * 1000)).encode()).hexdigest()
        headers = {
            "User-Agent": "Android14-1070-11070-201-0-Lyric-wifi",
            "KG-Rec": "1", "KG-RC": "1", "mid": mid,
        }
        try:
            resp = self.session.get(search_url, params=params, headers=headers, timeout=8)
            if resp.status_code != 200:
                return None
            data = resp.json()
            candidates = data.get("candidates", [])
            if not candidates:
                return None

            lyric_id = candidates[0].get("id")
            accesskey = candidates[0].get("accesskey")
            if not lyric_id or not accesskey:
                return None

            dl_url = "http://lyrics.kugou.com/download"
            dl_params_base = {
                "accesskey": accesskey, "charset": "utf8",
                "client": "mobi", "id": lyric_id, "ver": "1",
            }

            # ── 方案一：KRC 格式解密（逐字歌词） ──
            dl_params = {**dl_params_base, "fmt": "krc"}
            dl_resp = self.session.get(dl_url, params=dl_params, timeout=8)
            if dl_resp.status_code == 200:
                dl_data = dl_resp.json()
                content = dl_data.get("content", "")
                if content:
                    try:
                        raw_krc = base64.b64decode(content)
                        decrypted = krc_decrypt(raw_krc)
                        if decrypted:
                            tags, word_lyrics, roma_words, ts_lines = parse_krc_text(decrypted)
                            if word_lyrics:
                                result = {
                                    "word_lyrics": word_lyrics,
                                    "lrc": self._words_to_lrc(word_lyrics),
                                    "raw_lrc": self._words_to_lrc_text(word_lyrics),
                                }
                                # 罗马音（逐字 → 转为行格式）
                                if roma_words:
                                    result["romalrc"] = self._words_to_lrc(roma_words)
                                # 译文（逐行 LRC 格式）
                                if ts_lines:
                                    result["tlyric"] = ts_lines
                                if result.get("lrc"):
                                    return result

                            raw_lrc = self._krc_to_lrc_text(decrypted)
                            if raw_lrc.strip():
                                lrc_lyrics = self._parse_lrc_lyrics(raw_lrc)
                                result2 = {
                                    "lrc": lrc_lyrics,
                                    "word_lyrics": [],
                                    "raw_lrc": raw_lrc,
                                }
                                if roma_words:
                                    result2["romalrc"] = self._words_to_lrc(roma_words)
                                if ts_lines:
                                    result2["tlyric"] = ts_lines
                                return result2
                    except Exception as e:
                        print(f"[歌词] KRC 解密失败: {e}")

            # ── 方案二：LRC 纯文本 ──
            dl_params = {**dl_params_base, "fmt": "lrc"}
            dl_resp = self.session.get(dl_url, params=dl_params, timeout=8)
            if dl_resp.status_code != 200:
                return None
            dl_data = dl_resp.json()
            content = dl_data.get("content", "")
            if not content:
                return None

            raw_text = base64.b64decode(content)
            raw_lrc = raw_text.decode("utf-8", errors="replace")

            if not raw_lrc.strip():
                return None

            lrc_lyrics = self._parse_lrc_lyrics(raw_lrc)
            return {
                "lrc": lrc_lyrics, "word_lyrics": [], "raw_lrc": raw_lrc,
            }

        except Exception as e:
            print(f"[歌词] 酷狗歌词获取异常: {e}")
            return None

    def _krc_to_lrc_text(self, krc_text: str) -> str:
        """将解密后的 KRC 文本转为 LRC 文本"""
        lines = []
        for raw_line in krc_text.splitlines():
            line = raw_line.strip()
            if not line or not line.startswith("["):
                continue
            if re.match(r"^\[\w+:", line):
                lines.append(line)
                continue
            line_match = re.match(r"^\[(\d+),(\d+)\](.*)$", line)
            if line_match:
                start_ms = int(line_match.group(1))
                minutes = start_ms // 60000
                seconds = (start_ms % 60000) // 1000
                millis = start_ms % 1000
                content = line_match.group(3)
                content = re.sub(r'<\d+,\d+,\d+>[^<]*', '', content)
                content = re.sub(r'<[^>]+>', '', content)
                if content.strip():
                    lines.append(f"[{minutes:02d}:{seconds:02d}.{millis:02d}] {content.strip()}")
        return "\n".join(lines)

    # ════════════════════════════════════════════════════════════
    # 歌词解析工具
    # ════════════════════════════════════════════════════════════

    def _parse_lrc_lyrics(self, lrc_text: str) -> List[Dict]:
        """解析LRC格式歌词"""
        pattern = re.compile(r'\[(\d{2}):(\d{2})\.(\d{2,3})\](.*)')
        lyrics = []
        for line in lrc_text.split("\n"):
            match = pattern.match(line)
            if match:
                minutes = int(match.group(1))
                seconds = int(match.group(2))
                raw_ms = match.group(3)
                milliseconds = int(raw_ms) * 10 if len(raw_ms) == 2 else int(raw_ms)
                text = match.group(4).strip()
                if text and not text.startswith(("作词", "作曲", "编曲", "制作")):
                    timestamp = minutes * 60 + seconds + milliseconds / 1000
                    lyrics.append({"time": timestamp, "text": text})
        return lyrics

    def _parse_word_lyrics(self, word_lyric_text: str) -> List[Dict]:
        """解析逐词歌词（网易云 klyric）"""
        pattern = re.compile(r'\[(\d+),(\d+)\](.*?)(?=\[\d+|\Z)')
        words = []
        for match in pattern.finditer(word_lyric_text):
            start_time = int(match.group(1)) / 1000
            end_time = int(match.group(2)) / 1000
            text = match.group(3).strip()
            if text:
                words.append({"start": start_time, "end": end_time, "text": text})
        return words

    def _match_score(self, text: str, keyword: str) -> float:
        """文本匹配度（0-100）"""
        if not text or not keyword:
            return 0
        text_l = text.lower()
        kw_l = keyword.lower()
        if text_l == kw_l:
            return 100
        if kw_l in text_l:
            return 80
        words = kw_l.split()
        if words:
            matched = sum(1 for w in words if w in text_l)
            return (matched / len(words)) * 60
        return 0

    def _generate_word_timeline(self, lrc_lyrics: List[Dict]) -> List[Dict]:
        """从LRC歌词近似生成逐词时间轴"""
        word_timeline = []
        for i, lyric in enumerate(lrc_lyrics):
            text = lyric["text"]
            start_time = lyric["time"]
            end_time = lrc_lyrics[i + 1]["time"] if i < len(lrc_lyrics) - 1 else start_time + 5
            duration = end_time - start_time
            char_duration = duration / len(text) if len(text) > 0 else 0
            for j, char in enumerate(text):
                if char.strip():
                    word_timeline.append({
                        "start": start_time + j * char_duration,
                        "end": start_time + (j + 1) * char_duration,
                        "text": char
                    })
        return word_timeline
