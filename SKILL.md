---
name: video-download-multiplatform
description: 用 yt-dlp + ffmpeg 从任意主流视频平台下载视频到本地，自动合并分轨的视频流与音频流为单个 MP4。支持 B站/bilibili、抖音/Douyin、TikTok、小红书/XiaoHongShu、微博/Weibo、优酷/Youku、爱奇艺/iQiyi、西瓜视频/Ixigua、AcFun、斗鱼、虎牙、YouTube、Twitter/X、Instagram、Facebook、Vimeo、Twitch 等 1700+ 站点。不依赖任何第三方 API Key，比 redfox 类需要密钥的下载器更可靠。内置 check_env.py 自检 + bili_dl.py 绕开 B站 mcdn 拦截。仅用于下载自己上传或已获授权、可合法保存的内容。适用于用户提供视频链接要求「下载视频」「保存视频到本地」「下载抖音/B站/小红书视频」「获取视频文件」的场景。触发词：下载视频、下载B站、下载抖音、下载小红书、下载快手、下载YouTube、保存视频、yt-dlp、视频下载到本地。
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

yt-dlp 内置 **1700+ 提取器**。国内外主流平台：

| 平台 | Extractor | 备注 |
|------|-----------|------|
| **B站 bilibili** | `BiliBili` 等 20+ | 支持番剧、合集、收藏夹、UP主空间、课程 |
| **抖音** | `Douyin` | ✅ 原生支持 |
| **TikTok** | `TikTok` | ✅ 原生支持（部分子提取器已失效） |
| **小红书** | `XiaoHongShu` | ✅ 原生支持 |
| **微博** | `Weibo` / `WeiboVideo` / `WeiboUser` | ✅ |
| **优酷** | `youku` / `youku:show` | ✅ |
| **爱奇艺** | `iqiyi` | ✅ |
| **西瓜视频** | `Ixigua` | ✅ |
| **AcFun** | `AcFunVideo` / `AcFunBangumi` | ✅ |
| **斗鱼 / 虎牙** | `DouyuTV` / `huya:video` | 直播+录播 |
| **YouTube / Twitter / Instagram / Facebook / Vimeo / Twitch** | 各自原生 | ✅ |
| **快手** | ❌ 无原生 extractor | 靠通用提取器兜底，成功率不稳定 |
| **腾讯视频** | ❌ 无原生 extractor | 同上 |

**查证某平台是否支持**（不要凭猜测回答用户）：

```bash
"$YTDLP" --list-extractors 2>/dev/null | grep -iE "<平台关键词>"
```

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

其余平台（抖音/小红书/YouTube/微博等）走下面第 2 步。

### 2. 通用 yt-dlp 下载

先清理 URL 追踪参数，只保留核心链接：

| 平台 | 原始链接 | 清理后 |
|------|---------|--------|
| B站 | `bilibili.com/video/BV1xx/?spm_id_from=...&vd_source=...` | `bilibili.com/video/BV1xx/` |
| 抖音 | `v.douyin.com/xxxxx/` 短链 | 直接用，yt-dlp 会自动跟随跳转 |
| 小红书 | `xiaohongshu.com/explore/xxx?xsec_token=...` | **保留 `xsec_token`**，去掉它会 403 |

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

高画质视频（DASH 格式，B站/YouTube 常见）会**分轨下载** —— 视频流和音频流是两个文件：

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
- **快手 / 腾讯视频无原生支持**：只能靠通用提取器，可能失败。失败时如实告知用户，不要反复重试同一命令（频繁重试易触发风控）。
- **登录墙 / 机器人验证**：报 "Private video"、"Sign in to confirm you're not a bot"（YouTube 常见）时，加 `--cookies-from-browser chrome`，需本机 Chrome 已登录**该用户自己的**账号。
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
