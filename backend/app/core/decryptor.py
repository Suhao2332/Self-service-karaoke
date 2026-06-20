"""
歌词解密模块

移植自 LDDC (https://github.com/chenmozhijin/LDDC)
原始许可证: GPL-3.0-only, Copyright (C) 2024-2025 沉默の金 <cmzj@cmzj.org>

支持的加密格式:
  - QRC  (QQ音乐逐字歌词): TripleDES + zlib
  - KRC  (酷狗音乐歌词):   XOR + zlib
  - QMC1 (本地QRC文件):    查表XOR
  - EAPI (网易云传输加密):  AES-ECB + MD5
"""
import hashlib
import json
import struct
import zlib
from base64 import b64decode, b64encode
from typing import Optional


# ═══════════════════════════════════════════════════════════════
# QRC 解密 — QQ音乐逐字歌词
# 算法: 自定义 TripleDES (C# 风格位操作, 15轮) + zlib.decompress
# 移植自 LDDC tripledes.py
# ═══════════════════════════════════════════════════════════════

QRC_KEY = b"!@#)(*$%123ZXC!@!@#)(NHL"

ENCRYPT = 1
DECRYPT = 0

# LDDC 自定义 S-box (不同于标准 DES S-box)
_sbox = (
    (14, 4, 13, 1, 2, 15, 11, 8, 3, 10, 6, 12, 5, 9, 0, 7,
     0, 15, 7, 4, 14, 2, 13, 1, 10, 6, 12, 11, 9, 5, 3, 8,
     4, 1, 14, 8, 13, 6, 2, 11, 15, 12, 9, 7, 3, 10, 5, 0,
     15, 12, 8, 2, 4, 9, 1, 7, 5, 11, 3, 14, 10, 0, 6, 13),
    (15, 1, 8, 14, 6, 11, 3, 4, 9, 7, 2, 13, 12, 0, 5, 10,
     3, 13, 4, 7, 15, 2, 8, 15, 12, 0, 1, 10, 6, 9, 11, 5,
     0, 14, 7, 11, 10, 4, 13, 1, 5, 8, 12, 6, 9, 3, 2, 15,
     13, 8, 10, 1, 3, 15, 4, 2, 11, 6, 7, 12, 0, 5, 14, 9),
    (10, 0, 9, 14, 6, 3, 15, 5, 1, 13, 12, 7, 11, 4, 2, 8,
     13, 7, 0, 9, 3, 4, 6, 10, 2, 8, 5, 14, 12, 11, 15, 1,
     13, 6, 4, 9, 8, 15, 3, 0, 11, 1, 2, 12, 5, 10, 14, 7,
     1, 10, 13, 0, 6, 9, 8, 7, 4, 15, 14, 3, 11, 5, 2, 12),
    (7, 13, 14, 3, 0, 6, 9, 10, 1, 2, 8, 5, 11, 12, 4, 15,
     13, 8, 11, 5, 6, 15, 0, 3, 4, 7, 2, 12, 1, 10, 14, 9,
     10, 6, 9, 0, 12, 11, 7, 13, 15, 1, 3, 14, 5, 2, 8, 4,
     3, 15, 0, 6, 10, 10, 13, 8, 9, 4, 5, 11, 12, 7, 2, 14),
    (2, 12, 4, 1, 7, 10, 11, 6, 8, 5, 3, 15, 13, 0, 14, 9,
     14, 11, 2, 12, 4, 7, 13, 1, 5, 0, 15, 10, 3, 9, 8, 6,
     4, 2, 1, 11, 10, 13, 7, 8, 15, 9, 12, 5, 6, 3, 0, 14,
     11, 8, 12, 7, 1, 14, 2, 13, 6, 15, 0, 9, 10, 4, 5, 3),
    (12, 1, 10, 15, 9, 2, 6, 8, 0, 13, 3, 4, 14, 7, 5, 11,
     10, 15, 4, 2, 7, 12, 9, 5, 6, 1, 13, 14, 0, 11, 3, 8,
     9, 14, 15, 5, 2, 8, 12, 3, 7, 0, 4, 10, 1, 13, 11, 6,
     4, 3, 2, 12, 9, 5, 15, 10, 11, 14, 1, 7, 6, 0, 8, 13),
    (4, 11, 2, 14, 15, 0, 8, 13, 3, 12, 9, 7, 5, 10, 6, 1,
     13, 0, 11, 7, 4, 9, 1, 10, 14, 3, 5, 12, 2, 15, 8, 6,
     1, 4, 11, 13, 12, 3, 7, 14, 10, 15, 6, 8, 0, 5, 9, 2,
     6, 11, 13, 8, 1, 4, 10, 7, 9, 5, 0, 15, 14, 2, 3, 12),
    (13, 2, 8, 4, 6, 15, 11, 1, 10, 9, 3, 14, 5, 0, 12, 7,
     1, 15, 13, 8, 10, 3, 7, 4, 12, 5, 6, 11, 0, 14, 9, 2,
     7, 11, 4, 1, 9, 12, 14, 2, 0, 6, 10, 13, 15, 3, 5, 8,
     2, 1, 14, 7, 4, 10, 8, 13, 15, 12, 9, 0, 3, 5, 6, 11),
)


def _bitnum(a: bytearray, b: int, c: int) -> int:
    return ((a[(b // 32) * 4 + 3 - (b % 32) // 8] >> (7 - b % 8)) & 1) << c


def _bitnum_intr(a: int, b: int, c: int) -> int:
    return ((a >> (31 - b)) & 1) << c


def _bitnum_intl(a: int, b: int, c: int) -> int:
    return ((a << b) & 0x80000000) >> c


def _sbox_bit(a: int) -> int:
    return (a & 32) | ((a & 31) >> 1) | ((a & 1) << 4)


def _initial_permutation(input_data: bytearray) -> tuple:
    return (
        (_bitnum(input_data, 57, 31) | _bitnum(input_data, 49, 30) |
         _bitnum(input_data, 41, 29) | _bitnum(input_data, 33, 28) |
         _bitnum(input_data, 25, 27) | _bitnum(input_data, 17, 26) |
         _bitnum(input_data, 9, 25) | _bitnum(input_data, 1, 24) |
         _bitnum(input_data, 59, 23) | _bitnum(input_data, 51, 22) |
         _bitnum(input_data, 43, 21) | _bitnum(input_data, 35, 20) |
         _bitnum(input_data, 27, 19) | _bitnum(input_data, 19, 18) |
         _bitnum(input_data, 11, 17) | _bitnum(input_data, 3, 16) |
         _bitnum(input_data, 61, 15) | _bitnum(input_data, 53, 14) |
         _bitnum(input_data, 45, 13) | _bitnum(input_data, 37, 12) |
         _bitnum(input_data, 29, 11) | _bitnum(input_data, 21, 10) |
         _bitnum(input_data, 13, 9) | _bitnum(input_data, 5, 8) |
         _bitnum(input_data, 63, 7) | _bitnum(input_data, 55, 6) |
         _bitnum(input_data, 47, 5) | _bitnum(input_data, 39, 4) |
         _bitnum(input_data, 31, 3) | _bitnum(input_data, 23, 2) |
         _bitnum(input_data, 15, 1) | _bitnum(input_data, 7, 0)),
        (_bitnum(input_data, 56, 31) | _bitnum(input_data, 48, 30) |
         _bitnum(input_data, 40, 29) | _bitnum(input_data, 32, 28) |
         _bitnum(input_data, 24, 27) | _bitnum(input_data, 16, 26) |
         _bitnum(input_data, 8, 25) | _bitnum(input_data, 0, 24) |
         _bitnum(input_data, 58, 23) | _bitnum(input_data, 50, 22) |
         _bitnum(input_data, 42, 21) | _bitnum(input_data, 34, 20) |
         _bitnum(input_data, 26, 19) | _bitnum(input_data, 18, 18) |
         _bitnum(input_data, 10, 17) | _bitnum(input_data, 2, 16) |
         _bitnum(input_data, 60, 15) | _bitnum(input_data, 52, 14) |
         _bitnum(input_data, 44, 13) | _bitnum(input_data, 36, 12) |
         _bitnum(input_data, 28, 11) | _bitnum(input_data, 20, 10) |
         _bitnum(input_data, 12, 9) | _bitnum(input_data, 4, 8) |
         _bitnum(input_data, 62, 7) | _bitnum(input_data, 54, 6) |
         _bitnum(input_data, 46, 5) | _bitnum(input_data, 38, 4) |
         _bitnum(input_data, 30, 3) | _bitnum(input_data, 22, 2) |
         _bitnum(input_data, 14, 1) | _bitnum(input_data, 6, 0)))


def _inverse_permutation(s0: int, s1: int) -> bytearray:
    data = bytearray(8)
    data[3] = (_bitnum_intr(s1, 7, 7) | _bitnum_intr(s0, 7, 6) | _bitnum_intr(s1, 15, 5) |
               _bitnum_intr(s0, 15, 4) | _bitnum_intr(s1, 23, 3) | _bitnum_intr(s0, 23, 2) |
               _bitnum_intr(s1, 31, 1) | _bitnum_intr(s0, 31, 0))
    data[2] = (_bitnum_intr(s1, 6, 7) | _bitnum_intr(s0, 6, 6) | _bitnum_intr(s1, 14, 5) |
               _bitnum_intr(s0, 14, 4) | _bitnum_intr(s1, 22, 3) | _bitnum_intr(s0, 22, 2) |
               _bitnum_intr(s1, 30, 1) | _bitnum_intr(s0, 30, 0))
    data[1] = (_bitnum_intr(s1, 5, 7) | _bitnum_intr(s0, 5, 6) | _bitnum_intr(s1, 13, 5) |
               _bitnum_intr(s0, 13, 4) | _bitnum_intr(s1, 21, 3) | _bitnum_intr(s0, 21, 2) |
               _bitnum_intr(s1, 29, 1) | _bitnum_intr(s0, 29, 0))
    data[0] = (_bitnum_intr(s1, 4, 7) | _bitnum_intr(s0, 4, 6) | _bitnum_intr(s1, 12, 5) |
               _bitnum_intr(s0, 12, 4) | _bitnum_intr(s1, 20, 3) | _bitnum_intr(s0, 20, 2) |
               _bitnum_intr(s1, 28, 1) | _bitnum_intr(s0, 28, 0))
    data[7] = (_bitnum_intr(s1, 3, 7) | _bitnum_intr(s0, 3, 6) | _bitnum_intr(s1, 11, 5) |
               _bitnum_intr(s0, 11, 4) | _bitnum_intr(s1, 19, 3) | _bitnum_intr(s0, 19, 2) |
               _bitnum_intr(s1, 27, 1) | _bitnum_intr(s0, 27, 0))
    data[6] = (_bitnum_intr(s1, 2, 7) | _bitnum_intr(s0, 2, 6) | _bitnum_intr(s1, 10, 5) |
               _bitnum_intr(s0, 10, 4) | _bitnum_intr(s1, 18, 3) | _bitnum_intr(s0, 18, 2) |
               _bitnum_intr(s1, 26, 1) | _bitnum_intr(s0, 26, 0))
    data[5] = (_bitnum_intr(s1, 1, 7) | _bitnum_intr(s0, 1, 6) | _bitnum_intr(s1, 9, 5) |
               _bitnum_intr(s0, 9, 4) | _bitnum_intr(s1, 17, 3) | _bitnum_intr(s0, 17, 2) |
               _bitnum_intr(s1, 25, 1) | _bitnum_intr(s0, 25, 0))
    data[4] = (_bitnum_intr(s1, 0, 7) | _bitnum_intr(s0, 0, 6) | _bitnum_intr(s1, 8, 5) |
               _bitnum_intr(s0, 8, 4) | _bitnum_intr(s1, 16, 3) | _bitnum_intr(s0, 16, 2) |
               _bitnum_intr(s1, 24, 1) | _bitnum_intr(s0, 24, 0))
    return data


def _f(state: int, key: list) -> int:
    t1 = (_bitnum_intl(state, 31, 0) | ((state & 0xf0000000) >> 1) |
          _bitnum_intl(state, 4, 5) | _bitnum_intl(state, 3, 6) |
          ((state & 0x0f000000) >> 3) | _bitnum_intl(state, 8, 11) |
          _bitnum_intl(state, 7, 12) | ((state & 0x00f00000) >> 5) |
          _bitnum_intl(state, 12, 17) | _bitnum_intl(state, 11, 18) |
          ((state & 0x000f0000) >> 7) | _bitnum_intl(state, 16, 23))
    t2 = (_bitnum_intl(state, 15, 0) | ((state & 0x0000f000) << 15) |
          _bitnum_intl(state, 20, 5) | _bitnum_intl(state, 19, 6) |
          ((state & 0x00000f00) << 13) | _bitnum_intl(state, 24, 11) |
          _bitnum_intl(state, 23, 12) | ((state & 0x000000f0) << 11) |
          _bitnum_intl(state, 28, 17) | _bitnum_intl(state, 27, 18) |
          ((state & 0x0000000f) << 9) | _bitnum_intl(state, 0, 23))
    lrgstate = ((t1 >> 24) & 0xff, (t1 >> 16) & 0xff, (t1 >> 8) & 0xff,
                (t2 >> 24) & 0xff, (t2 >> 16) & 0xff, (t2 >> 8) & 0xff)
    lrgstate = [lrgstate[i] ^ key[i] for i in range(6)]
    state2 = ((_sbox[0][_sbox_bit(lrgstate[0] >> 2)] << 28) |
              (_sbox[1][_sbox_bit(((lrgstate[0] & 0x03) << 4) | (lrgstate[1] >> 4))] << 24) |
              (_sbox[2][_sbox_bit(((lrgstate[1] & 0x0f) << 2) | (lrgstate[2] >> 6))] << 20) |
              (_sbox[3][_sbox_bit(lrgstate[2] & 0x3f)] << 16) |
              (_sbox[4][_sbox_bit(lrgstate[3] >> 2)] << 12) |
              (_sbox[5][_sbox_bit(((lrgstate[3] & 0x03) << 4) | (lrgstate[4] >> 4))] << 8) |
              (_sbox[6][_sbox_bit(((lrgstate[4] & 0x0f) << 2) | (lrgstate[5] >> 6))] << 4) |
              _sbox[7][_sbox_bit(lrgstate[5] & 0x3f)])
    return (_bitnum_intl(state2, 15, 0) | _bitnum_intl(state2, 6, 1) |
            _bitnum_intl(state2, 19, 2) | _bitnum_intl(state2, 20, 3) |
            _bitnum_intl(state2, 28, 4) | _bitnum_intl(state2, 11, 5) |
            _bitnum_intl(state2, 27, 6) | _bitnum_intl(state2, 16, 7) |
            _bitnum_intl(state2, 0, 8) | _bitnum_intl(state2, 14, 9) |
            _bitnum_intl(state2, 22, 10) | _bitnum_intl(state2, 25, 11) |
            _bitnum_intl(state2, 4, 12) | _bitnum_intl(state2, 17, 13) |
            _bitnum_intl(state2, 30, 14) | _bitnum_intl(state2, 9, 15) |
            _bitnum_intl(state2, 1, 16) | _bitnum_intl(state2, 7, 17) |
            _bitnum_intl(state2, 23, 18) | _bitnum_intl(state2, 13, 19) |
            _bitnum_intl(state2, 31, 20) | _bitnum_intl(state2, 26, 21) |
            _bitnum_intl(state2, 2, 22) | _bitnum_intl(state2, 8, 23) |
            _bitnum_intl(state2, 18, 24) | _bitnum_intl(state2, 12, 25) |
            _bitnum_intl(state2, 29, 26) | _bitnum_intl(state2, 5, 27) |
            _bitnum_intl(state2, 21, 28) | _bitnum_intl(state2, 10, 29) |
            _bitnum_intl(state2, 3, 30) | _bitnum_intl(state2, 24, 31))


def _crypt(input_data: bytearray, key: list) -> bytearray:
    s0, s1 = _initial_permutation(input_data)
    for idx in range(15):
        previous_s1 = s1
        s1 = _f(s1, key[idx]) ^ s0
        s0 = previous_s1
    s0 = _f(s1, key[15]) ^ s0
    return _inverse_permutation(s0, s1)


def _key_schedule(key: bytes, mode: int) -> list:
    schedule = [[0] * 6 for _ in range(16)]
    key_rnd_shift = (1, 1, 2, 2, 2, 2, 2, 2, 1, 2, 2, 2, 2, 2, 2, 1)
    key_perm_c = (56, 48, 40, 32, 24, 16, 8, 0, 57, 49, 41, 33, 25, 17, 9,
                  1, 58, 50, 42, 34, 26, 18, 10, 2, 59, 51, 43, 35)
    key_perm_d = (62, 54, 46, 38, 30, 22, 14, 6, 61, 53, 45, 37, 29, 21, 13,
                  5, 60, 52, 44, 36, 28, 20, 12, 4, 27, 19, 11, 3)
    key_compression = (13, 16, 10, 23, 0, 4, 2, 27, 14, 5, 20, 9, 22, 18, 11,
                       3, 25, 7, 15, 6, 26, 19, 12, 1, 40, 51, 30, 36, 46, 54,
                       29, 39, 50, 44, 32, 47, 43, 48, 38, 55, 33, 52, 45, 41,
                       49, 35, 28, 31)
    c = sum(_bitnum(key, key_perm_c[i], 31 - i) for i in range(28))
    d = sum(_bitnum(key, key_perm_d[i], 31 - i) for i in range(28))
    for i in range(16):
        c = ((c << key_rnd_shift[i]) | (c >> (28 - key_rnd_shift[i]))) & 0xfffffff0
        d = ((d << key_rnd_shift[i]) | (d >> (28 - key_rnd_shift[i]))) & 0xfffffff0
        togen = 15 - i if mode == DECRYPT else i
        for j in range(6):
            schedule[togen][j] = 0
        for j in range(24):
            schedule[togen][j // 8] |= _bitnum_intr(c, key_compression[j], 7 - (j % 8))
        for j in range(24, 48):
            schedule[togen][j // 8] |= _bitnum_intr(d, key_compression[j] - 27, 7 - (j % 8))
    return schedule


def _tripledes_key_setup(key: bytes, mode: int) -> list:
    if mode == ENCRYPT:
        return [_key_schedule(key[0:], ENCRYPT),
                _key_schedule(key[8:], DECRYPT),
                _key_schedule(key[16:], ENCRYPT)]
    return [_key_schedule(key[16:], DECRYPT),
            _key_schedule(key[8:], ENCRYPT),
            _key_schedule(key[0:], DECRYPT)]


def _tripledes_crypt(data: bytearray, key: list) -> bytearray:
    for i in range(3):
        data = _crypt(data, key[i])
    return data


def _qrc_tripledes_decrypt(encrypted_text_byte: bytearray) -> bytearray:
    """使用 LDDC 自定义 TripleDES 解密 QRC 数据"""
    data = bytearray()
    schedule = _tripledes_key_setup(QRC_KEY, DECRYPT)
    for i in range(0, len(encrypted_text_byte), 8):
        data += _tripledes_crypt(encrypted_text_byte[i:i + 8], schedule)
    return data


def qrc_decrypt(encrypted_data) -> Optional[str]:
    """
    解密 QRC 格式歌词 (QQ音乐逐字歌词)

    使用 LDDC 的 15 轮自定义 TripleDES + zlib.decompress
    key: !@#)(*$%123ZXC!@!@#)(NHL
    """
    if not encrypted_data:
        return None
    try:
        if isinstance(encrypted_data, str):
            encrypted_data = encrypted_data.strip()
            data_bytes = bytearray.fromhex(encrypted_data)
        elif isinstance(encrypted_data, bytearray):
            data_bytes = encrypted_data
        elif isinstance(encrypted_data, bytes):
            data_bytes = bytearray(encrypted_data)
        else:
            return None

        decrypted = _qrc_tripledes_decrypt(data_bytes)
        result = zlib.decompress(bytes(decrypted))
        return result.decode('utf-8')
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════
# KRC 解密 — 酷狗音乐歌词
# 算法: XOR + zlib.decompress
# ═══════════════════════════════════════════════════════════════

KRC_KEY = b"@Gaw^2tGQ61-\xce\xd2ni"
KRC_HEADER = b"krc18"


def krc_decrypt(encrypted_data: bytes) -> Optional[str]:
    """
    解密 KRC 格式歌词 (酷狗音乐歌词)

    算法:
      1. 去除前4字节头 (krc18 中的 'krc1')
      2. 每个字节与 KRC_KEY 循环 XOR
      3. zlib.decompress

    Args:
        encrypted_data: KRC 加密的二进制数据

    Returns:
        解密后的 XML/文本格式歌词，失败返回 None
    """
    if not encrypted_data:
        return None

    try:
        data = bytearray(encrypted_data)

        # 跳过4字节头
        if len(data) > 4:
            data = data[4:]

        # XOR 解密
        key_len = len(KRC_KEY)
        for i in range(len(data)):
            data[i] ^= KRC_KEY[i % key_len]

        # zlib 解压
        result = zlib.decompress(bytes(data))
        return result.decode('utf-8')
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════
# QMC1 解密 — 本地 QRC 文件（QQ音乐下载的本地加密歌词）
# 算法: 查表 XOR
# ═══════════════════════════════════════════════════════════════

QMC1_PRIVKEY = bytes([
    0xc3, 0x4a, 0xd6, 0xca, 0x90, 0x67, 0xf7, 0x52,
    0xd8, 0xa1, 0x66, 0x62, 0x9f, 0x5b, 0x09, 0x00,
    0xc3, 0x5e, 0x95, 0x23, 0x9f, 0x13, 0x11, 0x7e,
    0xd8, 0x92, 0x3f, 0xbc, 0x90, 0xbb, 0x74, 0x0e,
    0xc3, 0x47, 0x74, 0x3d, 0x90, 0xaa, 0x3f, 0x51,
    0xd8, 0xf4, 0x11, 0x84, 0x9f, 0xde, 0x95, 0x1d,
    0xc3, 0xc6, 0x09, 0xd5, 0x9f, 0xfa, 0x66, 0xf9,
    0xd8, 0xf0, 0xf7, 0xa0, 0x90, 0xa1, 0xd6, 0xf3,
    0xc3, 0xf3, 0xd6, 0xa1, 0x90, 0xa0, 0xf7, 0xf0,
    0xd8, 0xf9, 0x66, 0xfa, 0x9f, 0xd5, 0x09, 0xc6,
    0xc3, 0x1d, 0x95, 0xde, 0x9f, 0x84, 0x11, 0xf4,
    0xd8, 0x51, 0x3f, 0xaa, 0x90, 0x3d, 0x74, 0x47,
    0xc3, 0x0e, 0x74, 0xbb, 0x90, 0xbc, 0x3f, 0x92,
    0xd8, 0x7e, 0x11, 0x13, 0x9f, 0x23, 0x95, 0x5e,
    0xc3, 0x00, 0x09, 0x5b, 0x9f, 0x62, 0x66, 0xa1,
    0xd8, 0x52, 0xf7, 0x67, 0x90, 0xca, 0xd6, 0x4a,
])

QRC_MAGIC_HEADER = b"\x98%\xb0\xac\xe3\x02\x83h\xe8\xfcl"


def qmc1_decrypt(data: bytearray) -> None:
    """
    QMC1 解密 (就地修改)

    用于解密本地 .qrc 文件的 QMC1 层加密。
    之后还需去除 11 字节头，再执行 qrc_decrypt。

    Args:
        data: 待解密的字节数组 (就地修改)
    """
    key_len = len(QMC1_PRIVKEY)
    for i in range(len(data)):
        idx = (i % 0x7FFF) & 0x7F if i > 0x7FFF else i & 0x7F
        data[i] ^= QMC1_PRIVKEY[idx]


def decrypt_local_qrc(file_data: bytes) -> Optional[str]:
    """
    解密本地 .qrc 歌词文件

    步骤:
      1. QMC1 XOR 解密
      2. 去除前 11 字节头
      3. TripleDES + zlib (即 qrc_decrypt)

    Args:
        file_data: .qrc 文件的原始字节

    Returns:
        解密后的歌词文本
    """
    try:
        data = bytearray(file_data)
        qmc1_decrypt(data)
        # 去除 11 字节头
        if len(data) > 11:
            data = data[11:]
        return qrc_decrypt(bytes(data))
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════
# EAPI 加密/解密 — 网易云音乐传输加密
# 算法: AES-ECB + MD5 签名
# ═══════════════════════════════════════════════════════════════

EAPI_KEY = b"e82ckenh8dichen8"
EAPI_DEVICEID_XOR_KEY = "3go8&$8*3*3h0k(2)2"


def _pkcs7_pad(data: bytes, block_size: int = 16) -> bytes:
    pad_len = block_size - (len(data) % block_size)
    return data + bytes([pad_len] * pad_len)


def _pkcs7_unpad(data: bytes) -> bytes:
    pad_len = data[-1]
    if pad_len < 1 or pad_len > 16:
        raise ValueError("无效的 PKCS7 padding")
    return data[:-pad_len]


# ── AES S-Box ──
_AES_SBOX = [
    0x63, 0x7c, 0x77, 0x7b, 0xf2, 0x6b, 0x6f, 0xc5, 0x30, 0x01, 0x67, 0x2b, 0xfe, 0xd7, 0xab, 0x76,
    0xca, 0x82, 0xc9, 0x7d, 0xfa, 0x59, 0x47, 0xf0, 0xad, 0xd4, 0xa2, 0xaf, 0x9c, 0xa4, 0x72, 0xc0,
    0xb7, 0xfd, 0x93, 0x26, 0x36, 0x3f, 0xf7, 0xcc, 0x34, 0xa5, 0xe5, 0xf1, 0x71, 0xd8, 0x31, 0x15,
    0x04, 0xc7, 0x23, 0xc3, 0x18, 0x96, 0x05, 0x9a, 0x07, 0x12, 0x80, 0xe2, 0xeb, 0x27, 0xb2, 0x75,
    0x09, 0x83, 0x2c, 0x1a, 0x1b, 0x6e, 0x5a, 0xa0, 0x52, 0x3b, 0xd6, 0xb3, 0x29, 0xe3, 0x2f, 0x84,
    0x53, 0xd1, 0x00, 0xed, 0x20, 0xfc, 0xb1, 0x5b, 0x6a, 0xcb, 0xbe, 0x39, 0x4a, 0x4c, 0x58, 0xcf,
    0xd0, 0xef, 0xaa, 0xfb, 0x43, 0x4d, 0x33, 0x85, 0x45, 0xf9, 0x02, 0x7f, 0x50, 0x3c, 0x9f, 0xa8,
    0x51, 0xa3, 0x40, 0x8f, 0x92, 0x9d, 0x38, 0xf5, 0xbc, 0xb6, 0xda, 0x21, 0x10, 0xff, 0xf3, 0xd2,
    0xcd, 0x0c, 0x13, 0xec, 0x5f, 0x97, 0x44, 0x17, 0xc4, 0xa7, 0x7e, 0x3d, 0x64, 0x5d, 0x19, 0x73,
    0x60, 0x81, 0x4f, 0xdc, 0x22, 0x2a, 0x90, 0x88, 0x46, 0xee, 0xb8, 0x14, 0xde, 0x5e, 0x0b, 0xdb,
    0xe0, 0x32, 0x3a, 0x0a, 0x49, 0x06, 0x24, 0x5c, 0xc2, 0xd3, 0xac, 0x62, 0x91, 0x95, 0xe4, 0x79,
    0xe7, 0xc8, 0x37, 0x6d, 0x8d, 0xd5, 0x4e, 0xa9, 0x6c, 0x56, 0xf4, 0xea, 0x65, 0x7a, 0xae, 0x08,
    0xba, 0x78, 0x25, 0x2e, 0x1c, 0xa6, 0xb4, 0xc6, 0xe8, 0xdd, 0x74, 0x1f, 0x4b, 0xbd, 0x8b, 0x8a,
    0x70, 0x3e, 0xb5, 0x66, 0x48, 0x03, 0xf6, 0x0e, 0x61, 0x35, 0x57, 0xb9, 0x86, 0xc1, 0x1d, 0x9e,
    0xe1, 0xf8, 0x98, 0x11, 0x69, 0xd9, 0x8e, 0x94, 0x9b, 0x1e, 0x87, 0xe9, 0xce, 0x55, 0x28, 0xdf,
    0x8c, 0xa1, 0x89, 0x0d, 0xbf, 0xe6, 0x42, 0x68, 0x41, 0x99, 0x2d, 0x0f, 0xb0, 0x54, 0xbb, 0x16,
]

_AES_INV_SBOX = [0] * 256
for _i, _v in enumerate(_AES_SBOX):
    _AES_INV_SBOX[_v] = _i

# AES Rcon (第一列)
_AES_RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1b, 0x36]


def _aes_sub_word(w: int) -> int:
    return (_AES_SBOX[(w >> 24) & 0xFF] << 24 |
            _AES_SBOX[(w >> 16) & 0xFF] << 16 |
            _AES_SBOX[(w >> 8) & 0xFF] << 8 |
            _AES_SBOX[w & 0xFF])


def _aes_rot_word(w: int) -> int:
    return ((w << 8) | (w >> 24)) & 0xFFFFFFFF


def _aes_key_expansion(key: bytes) -> list:
    """AES-128 密钥扩展，返回 11 轮密钥 (每轮 16 字节)"""
    nk = 4  # 128-bit
    nr = 10
    w = [0] * (4 * (nr + 1))
    for i in range(nk):
        w[i] = (key[4 * i] << 24) | (key[4 * i + 1] << 16) | (key[4 * i + 2] << 8) | key[4 * i + 3]
    for i in range(nk, 4 * (nr + 1)):
        temp = w[i - 1]
        if i % nk == 0:
            temp = _aes_sub_word(_aes_rot_word(temp)) ^ (_AES_RCON[i // nk - 1] << 24)
        w[i] = w[i - nk] ^ temp
    # 转为 4x4 字节数组格式 (state)
    round_keys = []
    for r in range(nr + 1):
        rk = []
        for col in range(4):
            rk.append(w[r * 4 + col])
        round_keys.append(rk)
    return round_keys


def _aes_add_round_key(state: list, round_key: list):
    for i in range(4):
        for j in range(4):
            state[i][j] ^= (round_key[j] >> (24 - i * 8)) & 0xFF


def _aes_sub_bytes(state: list, inv: bool = False):
    sbox = _AES_INV_SBOX if inv else _AES_SBOX
    for i in range(4):
        for j in range(4):
            state[i][j] = sbox[state[i][j]]


def _aes_shift_rows(state: list, inv: bool = False):
    if not inv:
        state[1][0], state[1][1], state[1][2], state[1][3] = state[1][1], state[1][2], state[1][3], state[1][0]
        state[2][0], state[2][1], state[2][2], state[2][3] = state[2][2], state[2][3], state[2][0], state[2][1]
        state[3][0], state[3][1], state[3][2], state[3][3] = state[3][3], state[3][0], state[3][1], state[3][2]
    else:
        state[1][0], state[1][1], state[1][2], state[1][3] = state[1][3], state[1][0], state[1][1], state[1][2]
        state[2][0], state[2][1], state[2][2], state[2][3] = state[2][2], state[2][3], state[2][0], state[2][1]
        state[3][0], state[3][1], state[3][2], state[3][3] = state[3][1], state[3][2], state[3][3], state[3][0]


def _aes_gf_mul(a: int, b: int) -> int:
    """GF(2^8) 乘法"""
    result = 0
    for _ in range(8):
        if b & 1:
            result ^= a
        hi = a & 0x80
        a = (a << 1) & 0xFF
        if hi:
            a ^= 0x1b
        b >>= 1
    return result


def _aes_mix_columns(state: list, inv: bool = False):
    for col in range(4):
        a = [state[i][col] for i in range(4)]
        if not inv:
            state[0][col] = _aes_gf_mul(2, a[0]) ^ _aes_gf_mul(3, a[1]) ^ a[2] ^ a[3]
            state[1][col] = a[0] ^ _aes_gf_mul(2, a[1]) ^ _aes_gf_mul(3, a[2]) ^ a[3]
            state[2][col] = a[0] ^ a[1] ^ _aes_gf_mul(2, a[2]) ^ _aes_gf_mul(3, a[3])
            state[3][col] = _aes_gf_mul(3, a[0]) ^ a[1] ^ a[2] ^ _aes_gf_mul(2, a[3])
        else:
            state[0][col] = _aes_gf_mul(14, a[0]) ^ _aes_gf_mul(11, a[1]) ^ _aes_gf_mul(13, a[2]) ^ _aes_gf_mul(9, a[3])
            state[1][col] = _aes_gf_mul(9, a[0]) ^ _aes_gf_mul(14, a[1]) ^ _aes_gf_mul(11, a[2]) ^ _aes_gf_mul(13, a[3])
            state[2][col] = _aes_gf_mul(13, a[0]) ^ _aes_gf_mul(9, a[1]) ^ _aes_gf_mul(14, a[2]) ^ _aes_gf_mul(11, a[3])
            state[3][col] = _aes_gf_mul(11, a[0]) ^ _aes_gf_mul(13, a[1]) ^ _aes_gf_mul(9, a[2]) ^ _aes_gf_mul(14, a[3])


def _aes_block_encrypt(block: bytes, round_keys: list) -> bytes:
    """加密一个 16 字节块"""
    state = [[block[i + 4 * j] for j in range(4)] for i in range(4)]
    _aes_add_round_key(state, round_keys[0])
    for r in range(1, 10):
        _aes_sub_bytes(state, inv=False)
        _aes_shift_rows(state, inv=False)
        _aes_mix_columns(state, inv=False)
        _aes_add_round_key(state, round_keys[r])
    _aes_sub_bytes(state, inv=False)
    _aes_shift_rows(state, inv=False)
    _aes_add_round_key(state, round_keys[10])
    result = bytearray(16)
    for i in range(4):
        for j in range(4):
            result[i + 4 * j] = state[i][j]
    return bytes(result)


def _aes_block_decrypt(block: bytes, round_keys: list) -> bytes:
    """解密一个 16 字节块"""
    state = [[block[i + 4 * j] for j in range(4)] for i in range(4)]
    _aes_add_round_key(state, round_keys[10])
    for r in range(9, 0, -1):
        _aes_shift_rows(state, inv=True)
        _aes_sub_bytes(state, inv=True)
        _aes_add_round_key(state, round_keys[r])
        _aes_mix_columns(state, inv=True)
    _aes_shift_rows(state, inv=True)
    _aes_sub_bytes(state, inv=True)
    _aes_add_round_key(state, round_keys[0])
    result = bytearray(16)
    for i in range(4):
        for j in range(4):
            result[i + 4 * j] = state[i][j]
    return bytes(result)


def _aes_ecb_encrypt(data: bytes, key: bytes) -> bytes:
    """AES-128-ECB 加密 (纯 Python, 无外部依赖)"""
    round_keys = _aes_key_expansion(key)
    padded = _pkcs7_pad(data)
    result = bytearray()
    for i in range(0, len(padded), 16):
        result.extend(_aes_block_encrypt(padded[i:i + 16], round_keys))
    return bytes(result)


def _aes_ecb_decrypt(data: bytes, key: bytes) -> bytes:
    """AES-128-ECB 解密 (纯 Python, 无外部依赖)"""
    round_keys = _aes_key_expansion(key)
    result = bytearray()
    for i in range(0, len(data), 16):
        result.extend(_aes_block_decrypt(data[i:i + 16], round_keys))
    return _pkcs7_unpad(bytes(result))


def eapi_params_encrypt(path: str, params: dict) -> str:
    """
    EAPI 请求参数加密

    构造: nobody{path}use{json_params}md5forencrypt → MD5
    最终: {path}-36cd479b6b5-{params}-36cd479b6b5-{sign} → AES 加密 → hex

    Args:
        path: API 路径 (如 /api/song/lyric/v1)
        params: 请求参数字典

    Returns:
        可用于 POST body 的字符串 (params=HEX)
    """
    path_bytes = path.encode()
    params_bytes = json.dumps(params, separators=(',', ':'), ensure_ascii=False).encode()

    sign_src = b"nobody" + path_bytes + b"use" + params_bytes + b"md5forencrypt"
    sign = hashlib.md5(sign_src).hexdigest()

    aes_src = path_bytes + b"-36cd479b6b5-" + params_bytes + b"-36cd479b6b5-" + sign.encode()
    encrypted = _aes_ecb_encrypt(aes_src, EAPI_KEY)

    return f"params={encrypted.hex().upper()}"


def eapi_response_decrypt(response_body: bytes) -> dict:
    """
    EAPI 响应解密

    Args:
        response_body: 服务器返回的原始字节

    Returns:
        解密后的 JSON 字典
    """
    decrypted = _aes_ecb_decrypt(response_body, EAPI_KEY)
    return json.loads(decrypted)


def eapi_get_anonimous_username(device_id: str) -> str:
    """
    生成网易云匿名用户名

    Args:
        device_id: 设备ID

    Returns:
        Base64 编码的用户名
    """
    xored = []
    key_len = len(EAPI_DEVICEID_XOR_KEY)
    for i, ch in enumerate(device_id):
        xored.append(chr(ord(ch) ^ ord(EAPI_DEVICEID_XOR_KEY[i % key_len])))
    xored_str = ''.join(xored)
    md5_digest = hashlib.md5(xored_str.encode('utf-8')).digest()
    combined = f"{device_id} {b64encode(md5_digest).decode('utf-8')}"
    return b64encode(combined.encode('utf-8')).decode('utf-8')


def eapi_get_cache_key(data: str) -> str:
    """生成 EAPI 缓存 key"""
    return b64encode(_aes_ecb_encrypt(data.encode(), b")(13daqP@ssw0rd~")).decode()


# ═══════════════════════════════════════════════════════════════
# QRC 文本解析 — 将解密后的 QRC XML 转为结构化数据
# ═══════════════════════════════════════════════════════════════

import re

_QRC_PATTERN = re.compile(r'<Lyric_1 LyricType="1" LyricContent="(?P<content>.*?)"/>', re.DOTALL)
_QRC_LINE_PATTERN = re.compile(r"^\[(\d+),(\d+)\](.*)$")
_QRC_WORD_PATTERN = re.compile(r"(?:\[\d+,\d+\])?(?P<content>(?:(?!\(\d+,\d+\)).)*)\((?P<start>\d+),(?P<duration>\d+)\)")


def parse_qrc_text(decrypted_qrc: str) -> tuple[dict, list]:
    """
    解析解密后的 QRC 文本，返回 (标签, 行级歌词列表, 逐词列表)

    每行: {"time": 秒, "text": 行文本, "words": [{start, end, text}, ...]}
    逐词: 平铺的 [{start, end, text}, ...]
    """
    match = _QRC_PATTERN.search(decrypted_qrc)
    if not match:
        return {}, [], []

    tags = {}
    line_lyrics = []
    word_timeline = []

    for raw_line in match.group("content").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        line_match = _QRC_LINE_PATTERN.match(line)
        if line_match:
            line_start = int(line_match.group(1))
            line_content = line_match.group(3)

            words = []
            line_text = ""
            for wm in _QRC_WORD_PATTERN.finditer(line_content):
                wtext = wm.group("content")
                wstart = int(wm.group("start"))
                wdur = int(wm.group("duration"))
                wend = wstart + wdur
                if wtext.strip():
                    words.append({
                        "start": wstart / 1000,
                        "end": wend / 1000,
                        "text": wtext.strip(),
                    })
                    line_text += wtext.strip()
                    word_timeline.append({
                        "start": wstart / 1000,
                        "end": wend / 1000,
                        "text": wtext.strip(),
                    })

            if line_text:
                line_lyrics.append({
                    "time": line_start / 1000,
                    "text": line_text,
                    "words": words,
                })
        else:
            tag_m = re.match(r"^\[(\w+):([^\]]*)\]$", line)
            if tag_m:
                tags[tag_m.group(1)] = tag_m.group(2)

    return tags, line_lyrics, word_timeline


# ═══════════════════════════════════════════════════════════════
# KRC 文本解析 — 将解密后的 KRC 文本转为结构化数据
# ═══════════════════════════════════════════════════════════════

_KRC_LINE_PATTERN = re.compile(r"^\[(\d+),(\d+)\](.*)$")
_KRC_WORD_PATTERN = re.compile(r"(?:\[\d+,\d+\])?<(?P<start>\d+),(?P<duration>\d+),\d+>(?P<content>(?:.(?!\d+,\d+,\d+>))*)")
_KRC_TAG_PATTERN = re.compile(r"^\[(\w+):([^\]]*)\]$")


def parse_krc_text(decrypted_krc: str) -> tuple[dict, list, list, list]:
    """
    解析解密后的 KRC 文本

    KRC 行格式: [开始毫秒,持续毫秒]<字偏移,字持续,0>字内容...
    标签: [key:base64_value]
    其中 language 标签是 base64 JSON，含罗马音(type=0)和翻译(type=1)

    Args:
        decrypted_krc: 解密后的 KRC 文本

    Returns:
        (tags_dict, orig_word_timeline, roma_word_timeline, ts_line_timeline)
        - orig_word_timeline: [{"start":秒, "end":秒, "text":str}, ...]
        - roma_word_timeline: 同上（罗马音逐字），无数据时为空
        - ts_line_timeline: [{"time":秒, "text":str}, ...]（译文逐行），无数据时为空
    """
    import base64

    tags = {}
    orig_lines = []  # [(line_start, line_end, [(word_start, word_end, text), ...])]

    for raw_line in decrypted_krc.splitlines():
        line = raw_line.strip()
        if not line or not line.startswith("["):
            continue

        tag_m = _KRC_TAG_PATTERN.match(line)
        if tag_m:
            tags[tag_m.group(1)] = tag_m.group(2)
            continue

        line_match = _KRC_LINE_PATTERN.match(line)
        if not line_match:
            continue

        line_start = int(line_match.group(1))
        line_duration = int(line_match.group(2))
        line_end = line_start + line_duration
        line_content = line_match.group(3)

        words = []
        for wm in _KRC_WORD_PATTERN.finditer(line_content):
            text = wm.group("content")
            word_start = line_start + int(wm.group("start"))
            word_end = word_start + int(wm.group("duration"))
            words.append((word_start, word_end, text.strip()))

        if not words:
            words = [(line_start, line_end, line_content.strip())]

        orig_lines.append((line_start, line_end, words))

    # 构建原文逐字时间轴
    orig_timeline = []
    for line_start, line_end, words in orig_lines:
        for w_start, w_end, w_text in words:
            if w_text:
                orig_timeline.append({"start": w_start / 1000, "end": w_end / 1000, "text": w_text})

    # 解析 language 标签中的罗马音(type=0)和翻译(type=1)
    roma_timeline = []
    ts_timeline = []

    if "language" in tags and tags["language"].strip():
        try:
            lang_json = json.loads(base64.b64decode(tags["language"].strip()))
            for lang in lang_json.get("content", []):
                if not isinstance(lang, dict):
                    continue
                lyric_content = lang.get("lyricContent", [])
                if not isinstance(lyric_content, list):
                    continue
                if lang.get("type") == 0:  # 罗马音（逐字）
                    offset = 0
                    for i, (line_start, line_end, words) in enumerate(orig_lines):
                        if all(not w_text for _, _, w_text in words):
                            offset += 1
                            continue
                        ri = i - offset
                        if ri < 0 or ri >= len(lyric_content):
                            continue
                        content_row = lyric_content[ri]
                        if not isinstance(content_row, list):
                            continue
                        for j, (w_start, w_end, w_text) in enumerate(words):
                            if w_text and j < len(content_row):
                                roma_timeline.append({
                                    "start": w_start / 1000,
                                    "end": w_end / 1000,
                                    "text": content_row[j],
                                })
                elif lang.get("type") == 1:  # 翻译（逐行）
                    for i, (line_start, line_end, words) in enumerate(orig_lines):
                        if i < len(lyric_content) and lyric_content[i]:
                            line_data = lyric_content[i]
                            if isinstance(line_data, list) and len(line_data) > 0:
                                ts_timeline.append({
                                    "time": line_start / 1000,
                                    "text": line_data[0],
                                })
        except Exception:
            pass

    return tags, orig_timeline, roma_timeline, ts_timeline


# ═══════════════════════════════════════════════════════════════
# YRC 文本解析 — 网易云逐字歌词
# ═══════════════════════════════════════════════════════════════

_YRC_LINE_PATTERN = re.compile(r"^\[(\d+),(\d+)\](.*)$")
_YRC_WORD_PATTERN = re.compile(r"(?:\[\d+,\d+\])?\((?P<start>\d+),(?P<duration>\d+),\d+\)(?P<content>(?:.(?!\d+,\d+,\d+\)))*)")  # noqa: E501


def parse_yrc_text(yrc_text: str) -> list:
    """
    解析 YRC 格式逐字歌词 (网易云音乐)

    YRC 行格式: [开始毫秒,持续毫秒](字开始,字持续,0)字内容...

    Args:
        yrc_text: YRC 歌词文本

    Returns:
        word_timeline: [{"start": 秒, "end": 秒, "text": str}, ...]
    """
    word_timeline = []

    for raw_line in yrc_text.splitlines():
        line = raw_line.strip()
        if not line or not line.startswith("["):
            continue

        line_match = _YRC_LINE_PATTERN.match(line)
        if not line_match:
            continue

        line_start = int(line_match.group(1))
        line_content = line_match.group(3)

        for wm in _YRC_WORD_PATTERN.finditer(line_content):
            text = wm.group("content")
            word_start = int(wm.group("start"))
            word_end = word_start + int(wm.group("duration"))
            if text.strip():
                word_timeline.append({
                    "start": word_start / 1000,
                    "end": word_end / 1000,
                    "text": text.strip(),
                })

    return word_timeline
