# 🕵️‍♂️ 晨间猎手内参 (Morning Hunter Briefing)

> **"这不是简单的新闻播报，这是你的私人商业情报猎手。"**

每天早上 7 点，自动抓取全网核心财经/科技信息，通过 AI 商业猎手视角进行深度拆解，生成 **"快讯+深度"** 的双模态情报（精美移动端网页 + 播客音频），并推送到你的手机。

## ✨ 核心功能

- 📰 **全景扫描 (Flash News)**：
    - 聚合 **新华社、华尔街见闻、财联社、第一财经** 等核心信源。
    - 按时间轴排列的快讯流，过滤噪音，只看干货。
- 🦁 **猎手深度拆解 (Deep Dive)**：
    - AI 扮演"商业情报猎手"，不只复述新闻。
    - 独家分析框架：**现状层 (The Facts) → 猎手拆解 (底层逻辑) → 搞钱路径 (行动指南)**。
- 📱 **移动端网页体验**：
    - 自动生成仿"微信公众号"风格的 HTML 网页。
    - 内置音频播放器，支持边听边看。
    - 适配手机屏幕，排版精美（红黑配色，重点加粗）。
- 🎙️ **自然语音播报**：
    - 使用 Edge-TTS 生成媲美真人的语音（支持 4000+ 字长文）。
    - 智能清洗文稿中的 Markdown 符号和表情包，确保听感顺滑。
- 🔔 **无感推送**：
    - 任务完成后通过 **Bark** 推送到 iPhone。
    - **点击通知直接跳转** 到当天的 HTML 情报页。

## 🚀 快速部署

### 1. 配置密钥 (Secrets)
在仓库的 **Settings** → **Secrets and variables** → **Actions** 中添加：

| 密钥名称 | 说明 | 获取方式 |
|---------|------|---------|
| `DASHSCOPE_API_KEY` | 阿里云通义千问 API (推荐 Qwen-Max) | [阿里云百炼平台](https://dashscope.console.aliyun.com/) |
| `BARK_KEY` | iPhone 推送通知密钥 | App Store 下载 [Bark](https://apps.apple.com/us/app/bark-customed-notifications/id1403753865) |

### 2. 开启 GitHub Pages (🔴 关键步骤)
为了让手机能访问生成的 HTML 网页，必须开启此功能：
1. 进入仓库 **Settings**。
2. 左侧栏点击 **Pages**。
3. **Build and deployment** -> **Source** 选择 `Deploy from a branch`。
4. **Branch** 选择 `main`，文件夹选择 `/ (root)`。
5. 点击 **Save**。

### 3. 检查权限
进入 **Settings** → **Actions** → **General**，滚动到底部 **Workflow permissions**，确保勾选：
- ✅ Read and write permissions

---

## 📻 如何使用

### 方式一：手机阅读 (推荐)
1. 每天早上任务完成后，**Bark** 会弹出通知：“02月01日晨间猎手...”。
2. **点击通知**，会自动跳转到当天的精美 HTML 网页。
3. 网页示例地址：
   `https://janicexu40-wq.github.io/My-Daily-AI-Report/output/briefing_20260201.html`
   *(日期会随当天自动变动)*

### 方式二：播客订阅 (RSS)
支持在 **小宇宙**、**Apple Podcast** 等泛用型播客客户端订阅。

**复制以下 RSS 地址添加订阅**：
