# douyin_cdp.py — 抖音视频下载（CDP 兜底，绕开 yt-dlp 直下失败）
#
# 用法:
#   python douyin_cdp.py "<抖音URL>" "[输出目录]"
#
# 示例:
#   python douyin_cdp.py "https://www.douyin.com/video/7699716102913396011" "D:\out"
#   python douyin_cdp.py "https://v.douyin.com/xxxxx/" "D:\out"
#
# 合规声明:
#   仅用于保存你自己上传、已获授权或可合法离线观看的公开内容，且需遵守抖音服务条款。
#   禁止: 批量抓取 / 整站镜像 / 转售 / 公开分发他人作品 / 去除水印后传播 / 规避付费墙。
#   本脚本不做并发、不做批量，仅做单视频的「让 Chrome 自行签名取地址 + 落盘」。
#
# 为什么需要这个脚本（而不是 yt-dlp 直下）:
#   - Chrome 127+ 对 Cookie 启用了「应用绑定加密(ABE)」，yt-dlp 用 DPAPI 解不开，
#     会报 "Failed to decrypt with DPAPI"。
#   - 抖音 web 详情接口(aweme/detail)需要页面 JS 实时生成的 a_bogus 签名，
#     yt-dlp 的 Douyin 提取器这块还是 TODO，直下会报 "Fresh cookies needed"。
#   本脚本改用 Chrome DevTools Protocol：启动带抖音登录态的 Chrome(headless)，
#   让 Chrome 自己的 JS 完成签名并请求详情，再从网络响应里取出真实 CDN 播放地址下载。
#
# 原理:
#   1. 复制本机真实 Chrome profile 的登录态到一个临时「非默认」目录
#      （Chrome 拒绝在默认 profile 目录上开远程调试，且复制能保留抖音登录态绕过风控）。
#   2. 启动 Chrome --headless=new --remote-debugging-port=PORT --user-data-dir=<临时目录>。
#   3. 用 WebSocket 连 CDP，拦截 aweme/detail 的网络响应，解析出 play_addr 真实地址。
#   4. curl 带 Referer 把最高码率那路下载成 MP4；输出 FINAL:<绝对路径>。
#
# 依赖: 托管 Python + yt-dlp 同款 ffmpeg 目录；websocket-client（缺失自动 pip 安装）。
#   ffmpeg 用于本脚本不直接合并（抖音是单文件），但校验仍可用；curl 用于下载。

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import urllib.parse

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = 9333
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")


def ensure_ws():
    """确保 websocket-client 可用，缺失则自动安装。"""
    try:
        import websocket  # noqa: F401
        return
    except Exception:
        pass
    subprocess.run([sys.executable, "-m", "pip", "install", "-U", "websocket-client"],
                   check=False)
    try:
        import websocket  # noqa: F401
    except Exception:
        print("[douyin_cdp] ERROR: 无法加载 websocket-client，请手动执行 "
              "pip install websocket-client", file=sys.stderr)
        sys.exit(1)


def find_chrome():
    cands = [
        os.path.expandvars(r"%LOCALAPPDATA%/Google/Chrome/Application/chrome.exe"),
        r"C:/Program Files/Google/Chrome/Application/chrome.exe",
        r"C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
        os.path.expanduser(r"~/AppData/Local/Google/Chrome/Application/chrome.exe"),
        os.path.join(os.environ.get("ProgramFiles", r"C:/Program Files"),
                     "Google/Chrome/Application/chrome.exe"),
    ]
    for c in cands:
        if c and os.path.exists(c):
            return c
    p = shutil.which("chrome") or shutil.which("google-chrome") or shutil.which("chrome.exe")
    return p


def find_real_profile():
    cands = [
        os.path.expandvars(r"%LOCALAPPDATA%/Google/Chrome/User Data"),
        os.path.expanduser(r"~/AppData/Local/Google/Chrome/User Data"),
    ]
    for c in cands:
        if c and os.path.isdir(c):
            return c
    return None


def find_tool(name):
    p = shutil.which(name)
    if p:
        return p
    home = os.path.expanduser("~")
    pf = os.environ.get("ProgramFiles", r"C:/Program Files")
    for c in [
        os.path.join(home, ".workbuddy", "binaries", "ffmpeg", "bin", name + ".exe"),
        os.path.join(pf, "Gyan", "FFmpeg", "bin", name + ".exe"),
        os.path.join(pf, "ffmpeg", "bin", name + ".exe"),
    ]:
        if os.path.exists(c):
            return c
    return None


def copy_profile(real, tmp):
    """复制真实 profile 的登录态到临时目录（排除缓存与密码库，尽力而为）。

    跳过密码库(Login Data)、各种 journal/lock 文件；单个文件若因权限/锁定
    无法读取则跳过并告警，不阻断整体复制。核心的 Network/Cookies 会照常复制。
    """
    os.makedirs(tmp, exist_ok=True)
    src_default = os.path.join(real, "Default")
    dst_default = os.path.join(tmp, "Default")
    ignore_dirs = {"Cache", "Code Cache", "Service Worker", "GPUCache", "Media Cache",
                   "optimization_guide_prediction_model_store", "SiteCharacteristicsDatabase",
                   "GrShaderCache", "DawnGraphiteCache", "DawnWebGPUCache"}
    ignore_files = {"Login Data", "Login Data-journal", "lock", "LOCK",
                    "SingletonLock", "Cookies-journal", "Web Data-journal"}
    skipped = []
    if os.path.isdir(src_default):
        for root, dirs, files in os.walk(src_default):
            rel = os.path.relpath(root, src_default)
            if rel != "." and rel.split(os.sep)[0] in ignore_dirs:
                dirs[:] = []
                continue
            dst_root = os.path.join(dst_default, rel)
            os.makedirs(dst_root, exist_ok=True)
            for f in files:
                if f in ignore_files:
                    continue
                try:
                    shutil.copy2(os.path.join(root, f), os.path.join(dst_root, f))
                except OSError as e:
                    skipped.append((os.path.join(root, f), str(e)))
    src_ls = os.path.join(real, "Local State")
    if os.path.exists(src_ls):
        try:
            shutil.copy2(src_ls, os.path.join(tmp, "Local State"))
        except OSError as e:
            skipped.append((src_ls, str(e)))
    if skipped:
        print("[douyin_cdp] 提示: 以下文件跳过(多为锁定/密码库，一般不影响下载):",
              file=sys.stderr)
        for s, e in skipped[:6]:
            print("  " + s, file=sys.stderr)
    return tmp


def launch_chrome(chrome, tmp_profile, url):
    args = [
        chrome, f"--remote-debugging-port={PORT}",
        "--headless=new", f"--user-data-dir={tmp_profile}",
        "--no-first-run", "--no-default-browser-check",
        "--remote-allow-origins=*",
        "--window-size=1280,800", "--disable-gpu",
        "--autoplay-policy=no-user-gesture-required",
        f"--user-agent={UA}",
        "about:blank",
    ]
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(40):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=2) as r:
                if r.status == 200:
                    return proc
        except Exception:
            time.sleep(0.5)
    try:
        proc.kill()
    except Exception:
        pass
    raise SystemExit("[douyin_cdp] ERROR: Chrome 远程调试未能启动")


def cdp_get_video(url):
    import websocket  # 已在 ensure_ws 保证可用

    # 找已经在抖音视频页的 page target（页面可能重定向，多等几轮）
    target = None
    for _ in range(30):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=5) as r:
                pages = json.loads(r.read())
        except Exception:
            time.sleep(1)
            continue
        for p in pages:
            if p.get("type") == "page" and "douyin.com" in p.get("url", ""):
                target = p
                break
        if target:
            break
        time.sleep(1)
    if not target:
        # 退而求其次：任意 page target
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=5) as r:
            pages = json.loads(r.read())
        target = next((p for p in pages if p.get("type") == "page"), None)
    if not target:
        raise SystemExit("[douyin_cdp] ERROR: 没有可用的 page target")

    ws = websocket.create_connection(target["webSocketDebuggerUrl"], timeout=60)
    lock = threading.Lock()
    mid = [0]
    found = {}
    loaded = threading.Event()
    detail_req_id = [None]
    detail_body_id = [None]
    saw_detail = [False]
    seen_urls = []

    def send(method, params=None):
        with lock:
            mid[0] += 1
            ws.send(json.dumps({"id": mid[0], "method": method, "params": params or {}}))
            return mid[0]

    send("Page.enable")
    send("Runtime.enable")
    send("Network.enable")
    send("Network.setCacheDisabled", {"cacheDisabled": True})

    def reader():
        while True:
            try:
                ws.settimeout(60)
                msg = json.loads(ws.recv())
            except Exception:
                return
            method = msg.get("method", "")
            # 命令响应（带 id，无 method）：getResponseBody 的返回
            if method == "" and "id" in msg and "result" in msg:
                if msg.get("id") == detail_body_id[0]:
                    body = msg.get("result", {}).get("body", "")
                    try:
                        data = json.loads(body)
                    except Exception:
                        pass
                    else:
                        ad = data.get("aweme_detail") or data.get("awemeInfo")
                        if ad:
                            v = ad.get("video", {}) or {}
                            cands = (v.get("play_addr") or {}).get("url_list") or []
                            br = v.get("bit_rate") or []
                            best, best_rate = None, -1
                            for b in br:
                                r0 = b.get("bit_rate", 0) or 0
                                if r0 > best_rate:
                                    best_rate, best = r0, b
                            if best:
                                cands = best.get("play_addr", {}).get("url_list") or cands or []
                            title = (ad.get("desc") or "").strip() or ad.get("aweme_id", "douyin_video")
                            if cands:
                                found["url"] = cands[0]
                                found["title"] = title
                                found["rate"] = best_rate
                continue
            if method == "Page.loadEventFired":
                loaded.set()
            elif method == "Network.responseReceived":
                p = msg.get("params", {})
                u = p.get("response", {}).get("url", "")
                if u and len(seen_urls) < 120:
                    seen_urls.append(u)
                # 详情接口（排除评论列表）
                if "/aweme/detail" in u and "comment" not in u:
                    saw_detail[0] = True
                    detail_req_id[0] = p.get("requestId")
                    bid = send("Network.getResponseBody", {"requestId": p.get("requestId")})
                    detail_body_id[0] = bid

    th = threading.Thread(target=reader, daemon=True)
    th.start()

    # 网络监听已就绪，再发起导航，确保从第一个请求起就能拦截
    time.sleep(1)
    send("Page.navigate", {"url": url})
    loaded.wait(timeout=40)
    for _ in range(35):
        time.sleep(1)
        if "url" in found:
            break

    try:
        ws.close()
    except Exception:
        pass
    if "url" not in found:
        # 诊断信息
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list", timeout=5) as r:
                for pg in json.loads(r.read()):
                    if pg.get("type") == "page":
                        print("[douyin_cdp] 当前URL: " + pg.get("url", ""), file=sys.stderr)
        except Exception:
            pass
        cap = any("captcha" in u or "verifycenter" in u or "rc-client-security" in u for u in seen_urls)
        print("[douyin_cdp] 诊断: saw_detail=%s 含验证码资源=%s 已捕获请求数=%d"
              % (saw_detail[0], cap, len(seen_urls)), file=sys.stderr)
        if not saw_detail[0]:
            for u in seen_urls[:25]:
                print("  " + u, file=sys.stderr)
        raise SystemExit("[douyin_cdp] ERROR: 未能从页面取到播放地址"
                          + ("（页面可能触发了人机验证，请确认本机 Chrome 已登录抖音，或稍后重试）"
                             if not saw_detail[0] else "（详情响应未含视频地址）"))
    return found["url"], found.get("title", "douyin_video"), found.get("rate", -1)


def sanitize(name):
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", name).strip()
    return (name[:80] or "douyin_video").strip()


def normalize_url(url):
    """把各种形态的抖音链接归一到规范的视频页 https://www.douyin.com/video/{id}。

    - jingxuan/vlog?modal_id=ID  → /video/ID（精选页易触发风控，规范页更稳）
    - /video/ID                  → 保持
    - v.douyin.com 短链           → 保持，让 Chrome 自行跳转
    """
    m = re.search(r"modal_id=(\d+)", url)
    if not m:
        m = re.search(r"/video/(\d+)", url)
    if m:
        return "https://www.douyin.com/video/" + m.group(1)
    return url


def download(url, out_dir, title, curl):
    os.makedirs(out_dir, exist_ok=True)
    safe = sanitize(title)
    ext = ".mp4"
    out = os.path.join(out_dir, safe + ext)
    i = 1
    while os.path.exists(out):
        out = os.path.join(out_dir, f"{safe}_{i}{ext}")
        i += 1
    referer = "https://www.douyin.com/"
    r = subprocess.run([curl, "-L", "--fail", "--retry", "3", "-o", out,
                        "-H", f"Referer: {referer}", "-H", f"User-Agent: {UA}", url],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("[douyin_cdp] ERROR: curl 下载失败: " + (r.stderr or "")[-400:])
    if os.path.getsize(out) == 0:
        raise SystemExit("[douyin_cdp] ERROR: 下载到空文件，CDN 地址可能已过期，请重试")
    return out


def main():
    ensure_ws()
    if len(sys.argv) < 2:
        print("用法: python douyin_cdp.py \"<抖音URL>\" \"[输出目录]\"", file=sys.stderr)
        sys.exit(2)
    url = sys.argv[1].strip()
    url = normalize_url(url)
    out_dir = sys.argv[2].strip() if len(sys.argv) > 2 else os.getcwd()

    chrome = find_chrome()
    if not chrome:
        raise SystemExit("[douyin_cdp] ERROR: 未找到 chrome.exe，请安装 Chrome 后重试")
    real = find_real_profile()
    if not real:
        raise SystemExit("[douyin_cdp] ERROR: 未找到 Chrome profile，无法复制登录态")

    curl = find_tool("curl")
    if not curl:
        raise SystemExit("[douyin_cdp] ERROR: 未找到 curl，无法下载")

    tmp_profile = os.path.join(tempfile.gettempdir(), "douyin_cdp_profile")
    if os.path.isdir(tmp_profile):
        shutil.rmtree(tmp_profile, ignore_errors=True)

    proc = None
    try:
        copy_profile(real, tmp_profile)
        proc = launch_chrome(chrome, tmp_profile, url)
        play_url, title, rate = cdp_get_video(url)
        out = download(play_url, out_dir, title, curl)
        size = os.path.getsize(out)
        print(f"[douyin_cdp] 码率(kbps): {rate if rate and rate > 0 else 'default'}")
        print(f"[douyin_cdp] 已保存: {out}  ({size} bytes)")
        print("FINAL:" + out)
    finally:
        if proc:
            try:
                proc.kill()
            except Exception:
                pass
        shutil.rmtree(tmp_profile, ignore_errors=True)


if __name__ == "__main__":
    main()
