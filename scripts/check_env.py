# check_env.py — 下载环境自检（yt-dlp / ffmpeg / ffprobe / curl）
#
# 用法:
#   python check_env.py
#
# 输出每项依赖的「状态 + 实际路径 + 版本」，缺失项直接给出可复制的安装命令。
# 全部就绪时退出码 0，缺任意一项退出码 1。

import os
import shutil
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

HOME = os.path.expanduser("~")
PY = sys.executable
SCRIPTS = os.path.join(os.path.dirname(PY), "Scripts")
FFMPEG_DIR = os.path.join(HOME, ".workbuddy", "binaries", "ffmpeg", "bin")


def find(name, extra=()):
    """PATH 优先，其次常见非 PATH 安装位置。"""
    p = shutil.which(name)
    if p:
        return p
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    cands = list(extra) + [
        os.path.join(FFMPEG_DIR, name + ".exe"),
        os.path.join(HOME, "scoop", "apps", "ffmpeg", "current", "bin", name + ".exe"),
        os.path.join(pf, "Gyan", "FFmpeg", "bin", name + ".exe"),
        os.path.join(pf, "ffmpeg", "bin", name + ".exe"),
    ]
    for c in cands:
        if os.path.exists(c):
            return c
    return None


def version(cmd, marker):
    """取版本串：ffmpeg --version 首行 / yt-dlp --version。"""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        out = (r.stdout or "") + (r.stderr or "")
        for line in out.splitlines():
            if marker in line.lower():
                return line.strip()[:70]
        return (out.strip().splitlines() or [""])[0][:70]
    except Exception as e:
        return "调用失败: %s" % e


def probe(name, ver_cmd, marker, extra=()):
    path = find(name, extra)
    return (name, bool(path), path or "-", version(ver_cmd(path), marker) if path else "-")


ITEMS = [
    probe("yt-dlp", lambda p: [p, "--version"], "",
          extra=[os.path.join(SCRIPTS, "yt-dlp.exe"),
                 os.path.join(SCRIPTS, "yt-dlp")]),
    probe("ffmpeg", lambda p: [p, "-version"], "ffmpeg version"),
    probe("ffprobe", lambda p: [p, "-version"], "ffprobe version"),
    probe("curl", lambda p: [p, "--version"], "curl"),
]

ok = all(i[1] for i in ITEMS[:2])  # yt-dlp 与 ffmpeg 是硬依赖

print("=" * 64)
print("video-download-multiplatform · 环境自检")
print("=" * 64)
print("%-10s %-6s %s" % ("依赖", "状态", "路径"))
print("-" * 64)
for name, found, path, ver in ITEMS:
    print("%-10s %-6s %s" % (name, "OK" if found else "MISS", path))
    if found:
        print("%-10s %-6s %s" % ("", "", ver))
print("-" * 64)

if not ok:
    print("\n缺依赖，按下面修复（复制即可执行）：\n")
    if not ITEMS[0][1]:
        print("  # yt-dlp")
        print('  %s -m pip install -U yt-dlp' % PY)
        print()
    if not ITEMS[1][1]:
        print("  # ffmpeg（二选一：PyPI 通道最快，winget 通道带 ffprobe）")
        print('  %s -m pip install -U imageio-ffmpeg' % PY)
        print('  %s -c "import imageio_ffmpeg, shutil, os; '
              'os.makedirs(r\'%s\', exist_ok=True); '
              'shutil.copy2(imageio_ffmpeg.get_ffmpeg_exe(), '
              'r\'%s\')"' % (PY, FFMPEG_DIR, os.path.join(FFMPEG_DIR, "ffmpeg.exe")))
        print()
        print("  winget install --id Gyan.FFmpeg --accept-package-agreements "
              "--accept-source-agreements")
        print()
    print("ffmpeg 就位后需重开 shell（或让本脚本用绝对路径调用）才生效 PATH。")

print("\n把下面三行粘进 bash，后续命令里的 $PY / $YTDLP / $FFMPEG 即可直接使用：")
print('PY="%s"' % PY.replace("\\", "/"))
print('YTDLP="%s"' % (ITEMS[0][2].replace("\\", "/") if ITEMS[0][1] else "<未安装>"))
print('FFMPEG="%s"' % (ITEMS[1][2].replace("\\", "/") if ITEMS[1][1] else "<未安装>"))
print()
print("结论: %s" % ("全部就绪，可以直接下载" if ok else "缺少必需依赖"))
sys.exit(0 if ok else 1)
