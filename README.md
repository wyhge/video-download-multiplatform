# 多平台视频下载 / video-download-multiplatform

---

## 简介

贴上任意主流平台的视频链接，用 `yt-dlp` + `ffmpeg` 把视频保存到本地，并自动把分轨的视频流和音频流合并成一个完整的 MP4。不依赖任何第三方 API Key，不会因为别人的 Key 失效而罢工。

B站另外配了专用脚本：自动绕开常被公司/校园网拦截的 `mcdn.bilivideo.cn:8082` P2P 节点，直连 upos/443 节点下载，告别 `[SSL: WRONG_VERSION_NUMBER]` 反复重试失败。

**合规前提**：只下载自己上传、已获授权或可合法离线保存的内容，并遵守目标平台服务条款。禁止批量抓取、转售、公开分发他人作品、规避付费墙。详见文末「合规声明」。

---

## 核心价值

- **1700+ 站点通吃**：B站、抖音、小红书、微博、优酷、爱奇艺、西瓜、AcFun、斗鱼、虎牙、YouTube、Twitter/X、Instagram、Facebook、Vimeo、Twitch 等，中外平台一套流程。
- **不用 Key 不会挂**：不依赖任何第三方解析 API，不受公共 Key 被封影响。
- **音视频自动合一**：DASH 分轨平台（B站/YouTube）下载后自动用 ffmpeg 合并，不留分轨垃圾文件。
- **B站专治网络拦截**：专用脚本自动挑选未被拦截的 CDN 节点，且比通用路径拿到更高码率。
- **环境自检开箱即用**：`check_env.py` 一条命令查全依赖，缺什么直接给出可复制的安装命令。

---

## 适用对象

- 内容收藏者 — 把自己关注的视频备份到本地，不怕原帖被删
- 创作者 — 保存自己发布或已获授权的素材，便于离线剪辑
- 研究者 / 学习者 — 留存公开课程、演讲等资料用于个人学习

---

## 使用前准备

需要三件套，缺哪个补哪个：

| 依赖 | 必需性 | 安装方式 |
|------|--------|----------|
| Python 3.8+ | 必需 | 已装即可 |
| yt-dlp | 必需 | `pip install -U yt-dlp` |
| ffmpeg | 必需 | PyPI 通道：`pip install -U imageio-ffmpeg`（快，不带 ffprobe）<br>winget 通道：`winget install --id Gyan.FFmpeg`（带 ffprobe，下载较慢） |
| curl | 可选 | 系统通常自带，没有时脚本自动回退标准库 |

装完跑一次自检，它会打印你本机可直接复制的路径变量：

```bash
python3 scripts/check_env.py
```

---

## 使用方法

**B站链接** — 走专用脚本：

```bash
python scripts/bili_dl.py "<B站URL 或 BV号>" "<输出目录>"
```

支持多分 P、中文标题、带追踪参数的原始链接；会员内容设 `BILI_SESSDATA` 环境变量（用你自己账号的 Cookie）。

**其它平台** — 走 yt-dlp：

```bash
yt-dlp --no-playlist --ffmpeg-location "<ffmpeg路径>" \
  -o "<输出目录>/%(title)s.%(ext)s" "<视频URL>"
```

需要登录才能看的内容加 `--cookies-from-browser chrome`。

下载完成后用 `ffmpeg -i <文件>` 确认同时存在 Video 和 Audio 两条流。

---

## 支持平台

| 平台 | 支持情况 |
|------|----------|
| B站 bilibili | ✅ 专用脚本，含番剧/合集/收藏夹/课程 |
| 抖音 / TikTok | ✅ 原生支持 |
| 小红书 | ✅ 原生支持（URL 需保留 `xsec_token`） |
| 微博 / 优酷 / 爱奇艺 / 西瓜 / AcFun | ✅ 原生支持 |
| 斗鱼 / 虎牙 | ✅ 直播 + 录播 |
| YouTube / X / Instagram / Facebook / Vimeo / Twitch | ✅ 原生支持 |
| 快手 / 腾讯视频 | ⚠️ 无原生提取器，成功率不稳定 |

不确定某平台是否支持时，用 `yt-dlp --list-extractors | grep <关键词>` 查证，不要凭猜测回答。

---

## 合规声明

**可以做**

- 下载自己上传的内容、已获授权的内容、公有领域内容
- 个人学习、研究、离线观看
- yt-dlp 官方提取器支持范围内的站点

**不要做**

- 批量抓取、整站镜像、爬取他人主页或合集
- 转售、公开分发、二次传播他人作品
- 去除水印后传播，或用它规避付费墙获取付费内容
- 采集视频中的人脸、声音、联系方式等个人信息

**关于 B站脚本的技术边界**

`scripts/bili_dl.py` 会模拟 B站客户端的常规请求参数（wbi 签名、客户端指纹），目的只有一个：取到该账号本来就有权观看的清晰度和一个未被网络拦截的 CDN 节点。它不做并发、不做批量、不破解付费。若要在公开渠道分发且希望进一步降低风险，删除该文件只保留 yt-dlp 通用路径即可，其余流程不受影响。

**隐私红线**

- 不内置、不上传任何 API Key、Cookie、账号信息
- `BILI_SESSDATA` / `--cookies-from-browser` 读取的是本机登录态，仅在下载会员内容时使用，且不要把 Cookie 值写进任何文件、日志或对话

**免责**：本技能只提供「把公开可访问的内容保存到本地」的能力，内容的版权与使用合规责任在使用者本人。

---

## 常见问题

**下载失败先做什么？** 先升级 yt-dlp：`pip install -U yt-dlp`。平台反爬变化频繁，旧版本失效很常见。

**报 `ffmpeg not found`？** PATH 没刷新，用 `--ffmpeg-location` 显式指定，或重开 shell。

**B站报 `SSL: WRONG_VERSION_NUMBER`？** 直链落到被拦截的 mcdn 节点了，用专用脚本重下。

**小红书 403？** URL 里的 `xsec_token` 被删了，这个鉴权参数必须保留。

**YouTube 提示 "Sign in to confirm you're not a bot"？** 触发了机器人验证，加 `--cookies-from-browser chrome`。
"# video-download-multiplatform" 
