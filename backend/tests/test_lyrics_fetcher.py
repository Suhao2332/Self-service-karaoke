"""测试歌词获取器 + 解密模块"""
import sys
sys.path.insert(0, r"F:\PythonAPP\Self-service karaoke\backend\app")
import json

from core.lyrics_fetcher import LyricsFetcher
from core.decryptor import (
    qrc_decrypt,
    krc_decrypt,
    parse_qrc_text,
    parse_krc_text,
    parse_yrc_text,
    eapi_params_encrypt,
    eapi_response_decrypt,
)

f = LyricsFetcher()

print("=" * 60)
print("1. 多源搜索测试")
print("=" * 60)
results = f.search_all_sources("青花瓷", "周杰伦")
for source, songs in results.items():
    print(f"[{source}] {len(songs)} 首:")
    for s in songs[:2]:
        print(f'   - {s["title"]} / {s["artist"]}')

print()
print("=" * 60)
print("2. LRC 解析测试")
print("=" * 60)
lrc = f._parse_lrc_lyrics("[00:01.50]hello world\n[00:05.00]test ok")
print(f"  LRC解析: {len(lrc)} lines -> {lrc}")

print()
print("=" * 60)
print("3. 逐词解析测试")
print("=" * 60)
word = f._parse_word_lyrics("[0,500]hello[500,1000]world")
print(f"  逐词解析: {len(word)} words -> {word}")

print()
print("=" * 60)
print("4. QRC 解密逻辑测试 (已知加密hex)")
print("=" * 60)
# 这些是 LDDC 的标准加密测试向量
test_qrc_hex = ""
if test_qrc_hex:
    result = qrc_decrypt(test_qrc_hex)
    print(f"  QRC解密结果: {result}")
else:
    print("  [跳过] 需要加密测试数据，仅验证函数导入")

# 验证 qrc_decrypt 在空输入时返回 None
assert qrc_decrypt(b"") is None, "空数据应返回 None"
assert qrc_decrypt("") is None, "空字符串应返回 None"
print("  QRC 空输入防护: OK")

print()
print("=" * 60)
print("5. KRC 解密逻辑测试")
print("=" * 60)
# 验证 krc_decrypt 在空输入时返回 None
assert krc_decrypt(b"") is None, "空数据应返回 None"
print("  KRC 空输入防护: OK")

# 构造一个测试用 KRC 数据
# KRC 文件结构: krc18(5字节头) | XOR加密的zlib压缩数据
# 解密时跳过前4字节(krc1)，第5字节('8')是zlib头被XOR后的值
import zlib
test_text = "[ti:test]\n[00:01,00]test lyrics\n"
compressed = zlib.compress(test_text.encode())
krc_key = b"@Gaw^2tGQ61-\xce\xd2ni"
# 正确构造: b"krc1" + (compressed[i] ^ key[i])...
encrypted = bytearray(b"krc1")
for i, b in enumerate(compressed):
    encrypted.append(b ^ krc_key[i % len(krc_key)])
decrypted = krc_decrypt(bytes(encrypted))
assert decrypted == test_text, f"KRC 解密不匹配: {decrypted!r} != {test_text!r}"
print("  KRC 加解密循环测试: OK")

print()
print("=" * 60)
print("6. KRC 文本解析测试")
print("=" * 60)
tags, words = parse_krc_text(test_text)
print(f"  标签: {tags}")
print(f"  字数: {len(words)} -> {words[:2]}")

print()
print("=" * 60)
print("7. YRC 文本解析测试")
print("=" * 60)
yrc_text = "[0,5000](0,500,0)测(500,1000,0)试(1500,2000,0)中"
yrc_words = parse_yrc_text(yrc_text)
print(f"  YRC字数: {len(yrc_words)} -> {yrc_words}")
assert len(yrc_words) > 0, "YRC解析应返回结果"
print("  YRC解析: OK")

print()
print("=" * 60)
print("8. EAPI 加密逻辑测试")
print("=" * 60)
# 测试 EAPI 参数加密（不发送请求，只验证构造）
params = {"id": 123, "lv": "-1"}
encrypted = eapi_params_encrypt("/api/song/lyric/v1", params)
assert encrypted.startswith("params="), f"EAPI 加密结果格式错误: {encrypted[:30]}"
print(f"  EAPI 参数加密: OK (长度={len(encrypted)})")

# 验证EAPI响应的空数据防护
import traceback
try:
    # 空数据应抛异常而非崩溃
    eapi_response_decrypt(b"")
    print("  [注意] 空数据未抛异常(某些实现可能容忍)")
except Exception as ex:
    print(f"  空数据防护: OK ({type(ex).__name__})")

print()
print("=" * 60)
print("9. 网易云歌词获取测试（回退到旧API）")
print("=" * 60)
lyrics = f._fetch_netease_lyrics_old("186016")
if lyrics:
    print(f"  歌词行数: {len(lyrics.get('lrc', []))}")
    print(f"  逐词行数: {len(lyrics.get('word_lyrics', []))}")
    print(f"  有译文: {'tlyric' in lyrics}")
    print(f"  有罗马音: {'romalrc' in lyrics}")
else:
    print("  [跳过] 网络失败或歌曲不可用")

print()
print("=" * 60)
print("10. 统一获取入口测试")
print("=" * 60)
result = f.fetch_lyrics("186016", "netease")
if result:
    print(f"  歌词行数: {len(result.get('lrc', []))}")
    print(f"  逐词数: {len(result.get('word_lyrics', []))}")
    print(f"  逐词时间轴: {result.get('word_lyrics', [])[:2]}")
else:
    print("  [跳过] 网络失败")

print()
print("所有测试完成!")
