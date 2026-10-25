---
name: video-download-multiplatform
description: 用 yt-dlp + ffmpeg 从 B站/bilibili、抖音/Douyin、小红书/XiaoHongShu 三个平台下载视频到本地，自动合并分轨的视频流与音频流为单个 MP4。不依赖任何第三方 API Key：B站配 bili_dl.py 绕开 mcdn 拦截，抖音配 douyin_cdp.py 绕过签名反爬，小红书用 yt-dlp 原生提取器（保留 xsec_token）。其余平台仍可由 yt-dlp 通用提取器下载。仅用于下载自己上传或已获授权、可合法保存的内容。适用于用户提供视频链接要求「下载抖音/B站/小红书视频」「保存视频到本地」「获取视频文件」的场景。触发词：下载视频、下载B站、下载抖音、下载小红书、保存视频、yt-dlp、视频下载到本地。
description_zh: 下载各平台视频到本地
description_en: Download videos from any platform
disable: false
agent_created: true
---

# video-download-multiplatform

用 `yt-dlp` + `ffmpeg` 把任意平台的视频保存到本地，**不依赖第三方 API Key**。

> **合规前提**：只下载你自己上传的、已获授权的、或公有领域的内容，并遵守目标平台的服务条款。
> 禁止批量抓取、转售、公开分发他人作品，也禁止用它绕过付费墙。详见文末「合规与隐私」。

## 0. 先拿路径（每次开工第一步，别猜路径）

本技能不硬编码任何机器相关路径。先跑自检，它会打印你本机可直接复制的 `PY` / `YTDLP` / `FFMPEG`：

```bash
# 有 python 在 PATH 时
PY="$(python3 -c 'import sys;print(sys.executable)' 2>/dev/null || python -c 'import sys;print(sys.executable)')"
"$PY" "<SKILL_DIR>/scripts/check_env.py"

# 没有 python 在 PATH 时（Windows 托管环境常见）
"%USERPROFILE%\.workbuddy\binaries\python\versions\3.13.12\python.exe" "<SKILL_DIR>/scripts/check_env.py"
```

`<SKILL_DIR>` = 本 SKILL.md 所在目录。

输出末尾有三行，粘回 shell 即可：

```
PY=".../python.exe"
YTDLP=".../yt-dlp.exe"
FFMPEG=".../ffmpeg.exe"
```

自检会检查四件套并给出缺失项的安装命令：

| 依赖 | 必需性 | 说明 |
|------|--------|------|
| yt-dlp | 必需 | 平台解析与下载；缺失时脚本给 `pip install -U yt-dlp` |
| ffmpeg | 必需 | 音视频合并；缺失时脚本给两条安装路线 |
| curl | 可选 | B站脚本用；没有会自动回退 urllib 标准库 |
| ffprobe | 可选 | 只用于校验，可用 `ffmpeg -i` 替代 |

> 平台反爬变化频繁，下载失败时先 `"$PY" -m pip install -U yt-dlp` 再重试。

## When to use

- 用户给出**任何**视频平台链接，要求把视频保存到本地
- 用户说「下载这个视频」「保存视频」「把视频弄下来」
- 其它依赖 API Key 的下载器（如 `video-downloader` skill 的 redfox API）失败时，**改用本 skill 兜底**

## 平台支持情况

本技能聚焦以下三个平台，每个都有开箱即用的专用 / 特化方案：

| 平台 | 方案 | 备注 |
|------|------|------|
| **B站 bilibili** | 专用脚本 `bili_dl.py` | 番剧/合集/收藏夹/UP主空间/课程；绕开 mcdn 拦截拿更高码率 |
| **抖音** | 专用 CDP 脚本 `douyin_cdp.py`（见 §1.5） | ⚠️ yt-dlp 直下必失败，必须走专用脚本 |
| **小红书** | yt-dlp 原生支持 | URL 须保留 `xsec_token`，去掉会 403 |

> 其它平台仍可由 yt-dlp 通用提取器下载（先跑 §0 自检拿到 `$YTDLP` 路径），但本说明文档只展开上述三个。

## Steps

### 1. B站专用脚本（B站链接走这条，别走 yt-dlp）

B站 DASH 直链常分配到 `mcdn.bilivideo.cn:8082` P2P 节点，在公司/校园网下该端口被拦，yt-dlp 会报 `[SSL: WRONG_VERSION_NUMBER]` 且重试全失败。脚本内置绕行：从 playurl 返回的候选里挑非 mcdn 的 upos/443 节点逐个重试，curl 下载后 ffmpeg 合并。

```bash
"$PY" "<SKILL_DIR>/scripts/bili_dl.py" "<B站URL 或 BV号>" "<输出目录>"
```

- 支持带追踪参数的原始链接、多分 P 视频（`?p=N` 自动选对应分 P）、中文标题。
- 输出解析：脚本最后一行打印 `FINAL:<绝对路径>`，取其作最终文件。
- 比 yt-dlp 通用路径码率更高（实测同一视频：脚本 585 kbps vs yt-dlp 430 kbps）。
- 会员内容：先用**自己的账号**设 `BILI_SESSDATA` 环境变量再跑；仍不行就退回 yt-dlp + `--cookies-from-browser chrome`。不要使用他人的 Cookie。

抖音走 §1.5 专用脚本；小红书走下面第 2 步。

### 1.5 抖音专用脚本（CDP 兜底，yt-dlp 直下会失败）

抖音的 web 提取器在 yt-dlp 当前版本上**不可用**，原因是两道反爬：

- **Chrome 127+ 应用绑定加密（ABE）**：抖音要求带浏览器 Cookie，而 Cookie 用 ABE 加密，yt-dlp 的 DPAPI 解密直接报 `Failed to decrypt with DPAPI`。
- **`a_bogus` 签名挑战**：抖音详情接口（`aweme/detail`）需要页面 JS 实时生成的 `a_bogus` 签名，yt-dlp 的 Douyin 提取器这块还是 `TODO`，直下会报 `Fresh cookies needed`。

所以抖音**不要走 yt-dlp**，改用本技能配套的 CDP 脚本——它启动一个带抖音登录态的 Chrome（headless），让 Chrome 自己的 JS 完成签名并请求详情，再从网络响应里取出真实 CDN 播放地址下载：

```bash
"$PY" "<SKILL_DIR>/scripts/douyin_cdp.py" "<抖音URL>" "<输出目录>"
```

要点：

- **链接形态自动归一化**：`jingxuan/vlog?modal_id=ID`、短链 `v.douyin.com/xxx/` 都会被处理；`modal_id` 类精选页链接会归一到规范的 `douyin.com/video/ID`（精选页更易触发风控，规范页更稳）。
- **需要本机 Chrome 已登录抖音**：脚本会复制你真实 Chrome profile 的登录态到一个临时「非默认」目录（Chrome 拒绝在默认 profile 目录上开远程调试，且复制能保留登录态以绕过人机验证）。若没登录，页面可能弹验证导致取不到地址。
- **依赖**：`websocket-client`（缺失时脚本自动 `pip install`）；ffmpeg / curl 走既有探测逻辑。
- **输出解析**：最后一行打印 `FINAL:<绝对路径>`，取名用视频标题（已做非法字符清洗）。
- 抖音是单文件，无需音视频合并。

### 2. 小红书下载（yt-dlp 通用路径）

小红书用 yt-dlp 原生提取器即可，但分享链接必须**完整保留** `xsec_token` 鉴权参数——被任何清理工具删掉都会 403：

```
xiaohongshu.com/explore/xxx?xsec_token=...   ← 整个链接原样保留
```

然后：

```bash
"$YTDLP" --no-playlist \
  --ffmpeg-location "$FFMPEG" \
  -o "<输出目录>/%(title)s.%(ext)s" \
  "<视频URL>"
```

关键参数：
- `--no-playlist`：只下当前视频，不下整个合集/主页（批量下载他人内容属高风险用法，见合规章节）
- `--ffmpeg-location`：显式指定 ffmpeg，避免 PATH 未刷新导致合并失败
- `-o "%(title)s.%(ext)s"`：用视频标题作为文件名

按需增加：
- `--cookies-from-browser chrome`：仅限下载**自己账号**有权观看的内容（会读取本机浏览器登录态）
- `-f "bv*+ba/b"`：显式要求最佳视频+最佳音频
- `--write-thumbnail`：额外保存封面图
- `--write-subs --sub-langs "zh-CN,en"`：下载字幕（若平台提供）

### 3. 检查是否需要合并音视频

高画质视频（DASH 格式，B站常见）会**分轨下载** —— 视频流和音频流是两个文件：

```
标题.f100026.mp4   ← 纯视频，无声音
标题.f30280.m4a    ← 纯音频
```

yt-dlp 找到 ffmpeg 会**自动合并并删除分轨**（实测确认），通常不需要手工干预。若报 `ffmpeg not found`，说明 PATH 未生效，加 `--ffmpeg-location "$FFMPEG"` 重跑。

抖音/小红书等短视频平台通常是**单文件**，不需要这步。

列出下载结果确认（中文/特殊字符文件名必须用 Python 遍历，别用 shell 通配符）：

```bash
"$PY" -c "
import os
outdir = r'<输出目录>'
for f in os.listdir(outdir):
    print(f'{os.path.getsize(os.path.join(outdir, f)):>12}  {f}')
"
```

### 4. 手动合并（仅当第 3 步发现分轨残留）

```bash
"$FFMPEG" -y -i "<视频文件>.f100026.mp4" -i "<音频文件>.f30280.m4a" \
  -map 0:v:0 -map 1:a:0 -c copy "<最终输出>.mp4"
```

`-c copy` 直接复制流，不重新编码，秒级完成。

### 5. 清理分轨文件

```bash
"$PY" -c "
import os
outdir = r'<输出目录>'
for f in os.listdir(outdir):
    if '.f1' in f or '.f3' in f:  # yt-dlp 分轨命名特征
        os.remove(os.path.join(outdir, f))
        print(f'deleted: {f}')
"
```

### 6. 展示结果

用 `present_files` 展示最终 MP4。

## Verification

```bash
"$FFMPEG" -hide_banner -i "<最终输出>.mp4" 2>&1 | grep -E "Duration|Stream"
```

应该看到 **两个流**：`Video: h264...` 和 `Audio: aac...`。只有 Video 说明音频没合并成功。

> 装了 ffprobe 的话也可 `ffprobe -v error -show_entries stream=codec_type -of csv=p=0 "<文件>"`。

## Pitfalls

- **不要用 `video-downloader` skill 的 redfox API**：内置公共 API Key 已被禁用（错误码 3105）。本 skill 是可靠替代方案。
- **Windows 中文文件名**：不要用 bash 的 `rm`/`ls` 通配符处理含中文和全角括号（`（）`）的文件名 —— 转义会失败。改用 Python 的 `os.listdir` + `os.remove`。
- **yt-dlp 会把 `/` 替换成 `⧸`**（U+29F8）：文件名中的斜杠会变成视觉相似的 Unicode 字符，用 `os.listdir` 遍历而不是猜文件名。
- **ffmpeg 不在 PATH 时**：装完当前 shell 的 PATH 还是旧的。要么重开 shell，要么用 `--ffmpeg-location "$FFMPEG"`。本 skill 的 `bili_dl.py` 会自动探测常见安装位置，无需干预。
- **装 ffmpeg 的两条路**：
  - PyPI 通道（快）：`pip install -U imageio-ffmpeg`，再把 `imageio_ffmpeg.get_ffmpeg_exe()` 拷到 `~/.workbuddy/binaries/ffmpeg/bin/ffmpeg.exe`。缺点是不带 ffprobe。
  - winget 通道（带 ffprobe）：`winget install --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements`。下载源较慢。
- **B站 mcdn 节点被墙**：直链常分配到 `mcdn.bilivideo.cn:8082`（P2P 节点），公司/校园网下该端口被拦截。**解法已固化**：直接用 `scripts/bili_dl.py`。
- **小红书别删 `xsec_token`**：清理 URL 时保留鉴权参数，否则 403。
- **抖音别走 yt-dlp**：抖音 web 提取器在当前 yt-dlp 上不可用——Chrome 127+ 的**应用绑定加密(ABE)** 让 cookie 解不开（报 `Failed to decrypt with DPAPI`），且详情接口要 **`a_bogus` 客户端签名**（yt-dlp 还是 TODO，报 `Fresh cookies needed`）。直接用 `scripts/douyin_cdp.py`（CDP 方案），别在抖音上耗 yt-dlp。
- **抖音 CDP 脚本前提**：脚本会复制本机 Chrome 登录态到临时目录，**需你已在 Chrome 登录抖音**；未登录时页面可能弹人机验证导致取不到地址。另外 Chrome 拒绝在默认 profile 目录开远程调试，所以必须用临时目录；脚本已自动处理，并加了 `--remote-allow-origins=*` 放行 CDP 连接。
- **AV1 编码**：B站新视频常用 AV1，`-c copy` 合并没问题，但若后续要重编码需注意解码器支持。

## 合规与隐私（发布 / 使用前必读）

**可以做**
- 下载自己上传的内容、已获授权的内容、公有领域内容
- 个人学习、研究、离线观看
- yt-dlp 官方提取器支持范围内的站点

**不要做**
- 批量抓取、整站镜像、爬取他人主页/合集
- 转售、公开分发、二次传播他人作品
- 去除水印后传播，或用它规避付费墙获取付费内容
- 采集视频中的人脸、声音、联系方式等个人信息

**关于 B站脚本的技术边界**
`scripts/bili_dl.py` 会模拟 B站客户端的常规请求参数（wbi 签名、客户端指纹），目的只有一个：**取到该账号本来就有权观看的清晰度和一个未被网络拦截的 CDN 节点**。它不做并发、不做批量、不破解付费。若你要在公开渠道分发本技能且希望进一步降低风险，删掉 `scripts/bili_dl.py` 只保留 yt-dlp 通用路径即可，其余流程不受影响。

**隐私红线**
- 本技能不内置、不上传任何 API Key、Cookie、账号信息
- `BILI_SESSDATA` / `--cookies-from-browser` 读取的是本机登录态，**仅在用户明确要求下载会员内容时使用**
- 不要把 Cookie 值写进任何文件、日志、代码注释或对话回复
- 下载的产物可能包含创作者信息，二次分发前自行确认授权

**免责**：本技能只提供「把公开可访问的内容保存到本地」的能力，内容的版权与使用合规责任在使用者本人。

## 配套 Skill

下载完成后常见的后续需求：
- **转文字** → `video-to-text-transcribe`（faster-whisper 本地转录）
- **做成教学视频** → `text-to-slides-video`（HTML 幻灯片 → 1080p MP4）

三个 skill 可串联成完整链路。
