# bili_dl.py — B站视频一键下载（自动绕开 mcdn:8082 拦截）
#
# 用法:
#   python bili_dl.py "<B站URL 或 BV号>" "<输出目录>"
#
# 示例:
#   python bili_dl.py "https://www.bilibili.com/video/BV1xx411c7mD/?spm_id_from=333" "D:\out"
#
# 合规声明:
#   仅用于保存你自己上传、已获授权或可合法离线观看的内容，且需遵守 B站服务条款。
#   禁止: 批量抓取 / 整站镜像 / 转售 / 公开分发他人作品 / 规避付费墙。
#   本脚本不做并发、不做批量、不破解付费，仅做单视频的「取可用节点 + 合并落盘」。
#
# 说明:
#   - B站 DASH 直链经常分配到 mcdn.bilivideo.cn:8082（P2P 节点），在公司/校园网等
#     环境下被拦截，yt-dlp 会报 [SSL: WRONG_VERSION_NUMBER] 且重试全失败。
#   - 本脚本调 x/player/wbi/playurl（fnval=4048 + try_look=1 + wbi 签名 + 客户端常规
#     参数，缺一不可，否则只返回低分辨率），从 baseUrl+backupUrl 候选里挑
#     非 mcdn 的 upos/443 直链；对每个候选逐个重试，直到拿到数据。
#   - 视频流: avc1 > hvc1 > av01 优先，取最高分辨率；音频: 取最高码率。
#   - 用 curl 带 Referer 下载，ffmpeg -c copy 合并，临时分轨文件用完即删。
#   - 仅支持公开视频；会员内容请用你自己账号的 SESSDATA（见下），不要用他人 Cookie。
#
# 依赖: 托管 Python（urllib 标准库）、curl（缺失时自动回退 urllib）、ffmpeg。
#   - ffmpeg 自动探测顺序: PATH -> ~/.workbuddy/binaries/ffmpeg/bin -> scoop -> Program Files
#   - 无 ffmpeg 时不会静默失败: 输出无声视频流并打印安装命令
#   - 环境自检: 同目录 check_env.py
# 会员/高码率: 设环境变量 BILI_SESSDATA=<你自己账号 Cookie 中的 SESSDATA>
#   注意不要把 SESSDATA 写进任何文件、日志或对话。

import base64
import hashlib
import json
import math
import os
import random
import re
import shutil
import string
import subprocess
import sys
import time
import urllib.parse
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
REFERER = "https://www.bilibili.com"

# 会员/高码率可选：先设环境变量 BILI_SESSDATA=<浏览器 Cookie 里的 SESSDATA>
SESSDATA = os.environ.get("BILI_SESSDATA", "").strip()
BASE_HEADERS = {"User-Agent": UA, "Referer": REFERER}
if SESSDATA:
    BASE_HEADERS["Cookie"] = "SESSDATA=" + SESSDATA

# wbi 签名所需的固定置换表（与 B站客户端一致）
_MIXIN_TAB = [46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43,
              5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16,
              24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59,
              6, 63, 57, 62, 11, 36, 20, 34, 44, 52]


def fail(msg):
    print("[bili_dl] ERROR: " + msg)
    sys.exit(1)


def http_json(url, params=None, timeout=20):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=dict(BASE_HEADERS))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def find_tool(name):
    """先在 PATH 里找，再找几个常见的非 PATH 安装位置。找不到返回 None。"""
    p = shutil.which(name)
    if p:
        return p
    home = os.path.expanduser("~")
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    cands = [
        os.path.join(home, ".workbuddy", "binaries", "ffmpeg", "bin", name + ".exe"),
        os.path.join(home, "scoop", "apps", "ffmpeg", "current", "bin", name + ".exe"),
        os.path.join(pf, "Gyan", "FFmpeg", "bin", name + ".exe"),
        os.path.join(pf, "ffmpeg", "bin", name + ".exe"),
    ]
    for c in cands:
        if os.path.exists(c):
            return c
    return None


def parse_bvid(s):
    m = re.search(r"(BV\w{10})", s)
    return m.group(1) if m else None


def parse_page(s):
    m = re.search(r"[?&]p=(\d+)", s)
    return int(m.group(1)) if m else 1


def get_mixin_key():
    nav = http_json("https://api.bilibili.com/x/web-interface/nav")
    img = nav["data"]["wbi_img"]["img_url"]
    sub = nav["data"]["wbi_img"]["sub_url"]
    lp = lambda x: x.rpartition("/")[2].partition(".")[0]
    lookup = lp(img) + lp(sub)
    return "".join(lookup[i] for i in _MIXIN_TAB)[:32]


def dm_params():
    w, h = 1920, 1080
    rnd = math.floor(114 * random.random())
    wh = [2 * w + 2 * h + 3 * rnd, 4 * w - h + rnd, rnd]
    r2 = math.floor(514 * random.random())
    of = [3 * 10 + 2 * 10 + r2, 4 * 10 - 4 * 10 + 2 * r2, r2]
    return {
        "dm_img_list": "[]",
        "dm_img_str": base64.b64encode(
            "".join(random.choices(string.printable, k=random.randint(16, 64))).encode()
        ).decode()[:-2],
        "dm_cover_img_str": base64.b64encode(
            "".join(random.choices(string.printable, k=random.randint(32, 128))).encode()
        ).decode()[:-2],
        "dm_img_inter": json.dumps({"ds": [], "wh": wh, "of": of}, separators=(",", ":")),
    }


def sign_wbi(params, mixin_key):
    params["wts"] = int(time.time())
    params = {k: "".join(c for c in str(v) if c not in "!'()*")
              for k, v in sorted(params.items())}
    query = urllib.parse.urlencode(params)
    params["w_rid"] = hashlib.md5((query + mixin_key).encode()).hexdigest()
    return params


def get_playurl(bvid, cid):
    mixin = get_mixin_key()
    params = {
        "bvid": bvid,
        "cid": cid,
        "fnval": 4048,      # DASH + 高画质特性
        "try_look": 1,      # 不带它只返回低分辨率
        **dm_params(),      # 客户端常规参数，缺一不可
    }
    raw = http_json("https://api.bilibili.com/x/player/wbi/playurl",
                    sign_wbi(params, mixin))
    if raw.get("code") != 0:
        fail("playurl 返回 code=%s msg=%s（会员/受限内容请改用 yt-dlp + cookies）"
             % (raw.get("code"), raw.get("message")))
    return raw["data"]


def candidates(entry):
    urls = []
    if entry.get("baseUrl"):
        urls.append(entry["baseUrl"])
    urls.extend(entry.get("backupUrl") or [])
    return urls


def is_mcdn(url):
    return "mcdn.bilivideo.cn" in url


def pick_stream(dash):
    videos = dash.get("video") or []
    audios = dash.get("audio") or []
    if not videos:
        fail("playurl 未返回 DASH 视频流")
    codec_pref = {"avc1": 0, "hvc1": 1, "av01": 2}
    videos.sort(key=lambda v: (codec_pref.get((v.get("codecs") or "")[:4], 3),
                               -(v.get("width") or 0)))
    v = videos[0]
    a = max(audios, key=lambda x: x.get("bandwidth") or 0) if audios else None
    print("[bili_dl] video: %sx%s codec=%s tbr=%s" %
          (v.get("width"), v.get("height"), v.get("codecs"), v.get("bandwidth")))
    if a:
        print("[bili_dl] audio: id=%s %s kbps" % (a.get("id"), (a.get("bandwidth") or 0) // 1000))
    return v, a


def ordered_urls(entry):
    """非 mcdn 候选优先，mcdn 候选兜底（说不定别的网络能通）。"""
    urls = candidates(entry)
    urls.sort(key=lambda u: 1 if is_mcdn(u) else 0)
    return urls


def curl_download(urls, out):
    for i, u in enumerate(urls):
        host = urllib.parse.urlparse(u).netloc
        print("[bili_dl] try #%d -> %s" % (i + 1, host))
        cmd = ["curl", "-L", "-s", "--max-time", "600",
               "-H", "Referer: " + REFERER, "-H", "User-Agent: " + UA,
               "-H", "Range: bytes=0-", "-o", out, u]
        if SESSDATA:
            cmd[3:3] = ["-H", "Cookie: SESSDATA=" + SESSDATA]
        r = subprocess.run(cmd)
        if r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 0:
            return True
        try:
            os.remove(out)
        except OSError:
            pass
    return False


def urllib_download(urls, out):
    """无 curl 时的回退方案：纯标准库下载。"""
    for i, u in enumerate(urls):
        host = urllib.parse.urlparse(u).netloc
        print("[bili_dl] try #%d (urllib) -> %s" % (i + 1, host))
        try:
            req = urllib.request.Request(
                u, headers=dict(BASE_HEADERS, **{"Range": "bytes=0-"}))
            with urllib.request.urlopen(req, timeout=600) as r, open(out, "wb") as f:
                shutil.copyfileobj(r, f)
            if os.path.getsize(out) > 0:
                return True
        except Exception as e:
            print("[bili_dl]   failed: %s" % e)
        try:
            os.remove(out)
        except OSError:
            pass
    return False


def download(urls, out):
    return curl_download(urls, out) if shutil.which("curl") else urllib_download(urls, out)


def safe_name(s):
    s = re.sub(r'[\\/:*?"<>|]', "_", s).strip()
    return s[:80] or "bilibili_video"


def main():
    if len(sys.argv) < 2:
        fail("用法: python bili_dl.py \"<B站URL 或 BV号>\" [输出目录]")
    src = sys.argv[1]
    outdir = sys.argv[2] if len(sys.argv) > 2 else os.getcwd()
    os.makedirs(outdir, exist_ok=True)

    bvid = parse_bvid(src)
    if not bvid:
        fail("无法从输入解析 BV 号: %s" % src)
    page = parse_page(src)
    print("[bili_dl] bvid=%s page=%s outdir=%s" % (bvid, page, outdir))

    view = http_json("https://api.bilibili.com/x/web-interface/view", {"bvid": bvid})
    if view.get("code") != 0:
        fail("view 接口失败: code=%s" % view.get("code"))
    data = view["data"]
    pages = data.get("pages") or []
    if not (1 <= page <= len(pages)):
        fail("页码超出范围: p=%s（共 %d 页）" % (page, len(pages)))
    cid = pages[page - 1]["cid"]
    title = data["title"]
    if len(pages) > 1:
        title = "%s - %s" % (title, pages[page - 1].get("part") or ("P%d" % page))
    print("[bili_dl] title=%s cid=%s" % (title, cid))

    play = get_playurl(bvid, cid)
    dash = play.get("dash")
    if not dash:
        fail("未获取到 DASH 信息（可能需要登录）")
    v, a = pick_stream(dash)

    vfile = os.path.join(outdir, "_bili_v.m4s")
    afile = os.path.join(outdir, "_bili_a.m4s")
    final = os.path.join(outdir, safe_name(title) + ".mp4")

    if not download(ordered_urls(v), vfile):
        fail("视频流下载失败（所有候选均不可用）")
    print("[bili_dl] video saved: %d bytes" % os.path.getsize(vfile))

    if a:
        if not download(ordered_urls(a), afile):
            fail("音频流下载失败（所有候选均不可用）")
        print("[bili_dl] audio saved: %d bytes" % os.path.getsize(afile))

    ffmpeg = find_tool("ffmpeg")
    if a and ffmpeg:
        print("[bili_dl] ffmpeg: %s" % ffmpeg)
        r = subprocess.run([ffmpeg, "-y", "-i", vfile, "-i", afile,
                            "-map", "0:v:0", "-map", "1:a:0",
                            "-c", "copy", final], capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(final) or os.path.getsize(final) == 0:
            fail("ffmpeg 合并失败: %s" % (r.stderr or "")[-500:])
        for f in (vfile, afile):
            try:
                os.remove(f)
            except OSError:
                print("[bili_dl] warn: 临时文件删除失败（可手动删）: %s" % f)
        print("[bili_dl] merged: %d bytes" % os.path.getsize(final))
    else:
        # 无音频流或无 ffmpeg: 直接把视频流改名输出
        os.replace(vfile, final)
        if a:
            os.replace(afile, final.replace(".mp4", "_audio.m4s"))
        if a and not ffmpeg:
            print("[bili_dl] WARN: 未找到 ffmpeg，输出的是无声视频流。"
                  "安装后重跑即可合并：winget install Gyan.FFmpeg "
                  "或把 ffmpeg.exe 放到 ~/.workbuddy/binaries/ffmpeg/bin/")
        else:
            print("[bili_dl] warn: 未合并（无音频），已输出视频流文件")

    print("FINAL:%s" % os.path.abspath(final))


if __name__ == "__main__":
    main()
