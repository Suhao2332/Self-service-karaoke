"""PyInstaller 构建脚本 — 绕过 Python 3.10.0 的 dis 模块 bug"""
import dis
import os
import sys
import shutil

# Monkey-patch: Python 3.10.0 的 _get_const_info 在遇到畸形字节码时
# 会 IndexError，这里补一个安全兜底
_orig_get_const_info = dis._get_const_info

def _safe_get_const_info(const_index, const_list):
    try:
        return _orig_get_const_info(const_index, const_list)
    except IndexError:
        return (None, f"<bad_const_{const_index}>")

dis._get_const_info = _safe_get_const_info

# 清理旧构建产物
for d in ["build", "dist"]:
    if os.path.exists(d):
        shutil.rmtree(d)
for f in os.listdir("."):
    if f.endswith(".spec"):
        os.remove(f)

# 运行 PyInstaller
from PyInstaller.__main__ import run as pyi_run
sys.argv = [
    "pyinstaller",
    "--onedir",
    "--name", "MV-Karaoke-Maker",
    "--distpath", "./dist",
    "--workpath", "./build",
    "--add-data", "backend/app;app",
    "--hidden-import", "pygame",
    "--hidden-import", "requests",
    "--hidden-import", "soundfile",
    "--hidden-import", "librosa",
    "--exclude-module", "sklearn",
    "--noconsole",
    "backend/app/main.py",
]
pyi_run()
