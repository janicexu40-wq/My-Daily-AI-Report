# 🕵️‍♂️ 晨间猎手内参 (Morning Hunter Briefing)

> **"这不是简单的新闻播报，这是你的私人商业情报猎手。"**

本项目每天早上 7 点自动运行，抓取全网核心财经/科技信息，通过 AI 扮演“商业情报猎手”进行深度拆解，生成 **"快讯+深度"** 的双模态情报，并推送到你的设备。

## ✨ 核心功能

- 📰 **全景扫描**：聚合新华社、华尔街见闻、财联社等核心信源，按时间轴过滤噪音。
- 🦁 **深度拆解**：AI 独家分析框架：**现状层 → 猎手拆解 (底层逻辑) → 搞钱路径**。
- ☁️ **阿里云盘同步**：自动上传 MP3 到网盘，支持倍速/后台播放。
- 📱 **移动端网页**：仿公众号风格的精美 HTML，支持边听边看。
- 🎙️ **自然语音**：Edge-TTS 生成媲美真人的语音播报。

## 🚀 部署指南

### 1. 配置密钥 (Secrets)
在仓库的 **Settings** → **Secrets and variables** → **Actions** 中添加：

| 密钥名称 | 说明 | 获取方式 |
|---------|------|---------|
| `DASHSCOPE_API_KEY` | 阿里云通义千问 API | [阿里云百炼平台](https://dashscope.console.aliyun.com/) |
| `BARK_KEY` | iPhone 推送通知密钥 | App Store 下载 [Bark](https://apps.apple.com/us/app/bark-customed-notifications/id1403753865) |
| `ALIYUN_REFRESH_TOKEN`| 阿里云盘上传凭证 | 用于网盘自动上传 |

### 2. 开启 GitHub Pages
为了使用手机网页版，请务必开启：
1. 进入仓库 **Settings** -> **Pages**。
2. **Branch** 选择 `main`，文件夹选择 `/ (root)`。
3. 点击 **Save**。

---

## 📻 如何收听 (三种方式)

### 方式一：阿里云盘 (网盘党推荐) ☁️
*适合习惯使用网盘听书、需要倍速播放的用户。*
1. 每天早上任务完成后，MP3 音频会自动上传到你的阿里云盘 **`/晨间情报`** 文件夹（需在 `.yml` 中配置）。
2. 直接打开 **阿里云盘 App** 点击播放即可。

### 方式二：手机网页 (Bark 推送) 📱
*适合需要边听边看文稿、查看深度分析图文的用户。*
1. 手机收到 **Bark** 通知的推送。
2. **点击通知**，跳转到当天的 HTML 情报页。
3. **网页示例**：
   `https://janicexu40-wq.github.io/My-Daily-AI-Report/output/briefing_20260201.html`

### 方式三：播客订阅 (RSS) 🎙️
*适合使用小宇宙、Apple Podcast 的泛用型播客用户。*
**复制以下 RSS 地址添加订阅**：
https://raw.githubusercontent.com/janicexu40-wq/My-Daily-AI-Report/main/feed.xml
---

## 🗞️ 核心情报源

本项目采用混合信源策略：

- **第一梯队 (金融核心)**：华尔街见闻 (Live)、财联社 (电报)
- **第二梯队 (权威定调)**：新华社、第一财经、澎湃新闻
- **第三梯队 (深度/科技)**：虎嗅、36氪、少数派 (sspai)、人人都是产品经理
- **第四梯队 (研报)**：东方财富策略研报、南方周末

---

## 🔧 高级配置

### 调整运行时间
编辑 `.github/workflows/daily.yml`：
```yaml
- cron: '0 23 * * *'  # 对应北京时间早上 7:00
更换声音
编辑 main.py 中的 VOICE_NAME：

zh-CN-YunxiNeural (默认，稳重男声)

zh-CN-XiaoxiaoNeural (活力女声)

📂 输出文件结构
Plaintext
output/
├── briefing_20260201.mp3   # 🎙️ 音频 (上传至阿里云盘)
├── briefing_20260201.html  # 📱 网页 (Bark 跳转)
├── briefing_20260201.md    # 📝 原稿
feed.xml                    # 📡 RSS
免责声明：本项目生成的投资分析仅供参考，AI 可能会产生幻觉，不构成任何投资建议。
