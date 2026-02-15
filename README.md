<div align="center">

# 🦁 J-Intel: 晨间商业猎手 (Morning Hunter)

**"这不是简单的新闻播报，这是你的私人商业情报猎手。"**

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://python.org)
[![Powered by Qwen](https://img.shields.io/badge/AI-Qwen%20Max-00A65A)](https://tongyi.aliyun.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![GitHub Actions](https://github.com/janicexu40-wq/My-Daily-AI-Report/actions/workflows/daily.yml/badge.svg)](https://github.com/janicexu40-wq/My-Daily-AI-Report/actions)

</div>

---

## 📖 项目简介

**J-Intel (J记财讯)** 是一个全自动化的商业情报挖掘系统。

它每天早上 7 点自动运行，通过**四层情报漏斗**过滤全网海量信息，利用 AI 扮演“首席分析师”进行深度拆解，最终生成一份包含**“快讯+深度+音频”**的多模态内参，并自动同步到你的云盘。

> **核心理念**：拒绝噪音，只看信号；拒绝焦虑，只找铲子。

---

## ⚡️ 核心特性

### 1. 🦁 四层情报漏斗 (The 4-Layer Funnel)
系统采用分层采集策略，确保信息既有广度又有深度：
- **Layer 1: 实时信号 (Signals)** - *华尔街见闻 Live、财联社电报*
  - ⚡️ 毫秒级快讯，只抓取标题，捕捉市场异动。
- **Layer 2: 行业解读 (Industry)** - *36Kr、虎嗅、第一财经*
  - 🔭 深度报道，用于 AI 分析商业逻辑和产业链位置。
- **Layer 3: 技术情报 (Tech)** - *Hacker News、GitHub Trending*
  - 🛠 挖掘新工具、新框架，寻找“卖铲子”的机会。
- **Layer 4: 深度洞察 (Deep Dive)** - *OPML 博客群、研报*
  - 🧠 随机抽取顶级技术博客与券商研报，提供跨越周期的洞察。

### 2. 🧠 智能价值评分
不是所有新闻都值得看。系统内置**关键词评分引擎**：
- **加分项** (+1~2)：`融资` `财报` `SaaS` `变现` `套利` `底层逻辑`
- **减分项** (-2)：`促销` `八卦` `开箱` `综艺`
- **机制**：低于 3 分的信息直接丢弃，高分信息送入 LLM 深度拆解。

### 3. 🎙️ 广播级语音合成
- 使用 **Edge-TTS** (zh-CN-YunxiNeural) 生成媲美真人的语音。
- 内置 **正则清洗管道**，自动移除 Markdown 符号、代码块和无意义字符，确保听感如电台般流畅。

### 4. ☁️ 云端永存，本地极简
- **阿里云盘**：全量备份历史所有 MP3、Markdown 和 HTML 文件，支持在线播放和倍速听书。
- **GitHub**：利用 `git add .` 机制，自动清理 3 天前的旧文件，保持仓库轻量化。
## 📂 输出示例

每天运行后，你将在阿里云盘 `/晨间情报` 文件夹看到：

- 📄 `briefing_20260216.md` (深度文字版)
- 🌐 `briefing_20260216.html` (手机适配版网页)
- 🎧 `briefing_20260216.mp3` (10分钟语音版)

---

## 🤝 致谢与协议

- **核心灵感**：[Intel Briefing](https://github.com/77AutumN/Intel_Briefing)
- **语音支持**：[edge-tts](https://github.com/rany2/edge-tts)
- **网盘工具**：[aligo](https://github.com/wxy247/aligo)

本项目遵循 MIT 协议开源。

---

## 🛠️ 技术架构

```mermaid
graph TD
    A[🕒 GitHub Actions 定时触发] --> B(🚀 启动 J-Intel 引擎);
    
    subgraph Data_Collection [1. 情报采集]
        B --> C{RSS 分层抓取};
        C -->|L1 信号| D[快讯源];
        C -->|L2 行业| E[深度源];
        C -->|L3 技术| F[HN/Github];
        C -->|L4 洞察| G[OPML/研报];
    end
    
    subgraph Processing [2. 数据处理]
        D & E & F & G --> H[智能评分过滤器];
        H -->|Score < 3| I[🗑️ 丢弃];
        H -->|Score >= 3| J[素材池];
    end
    
    subgraph AI_Analysis [3. AI 分析]
        J --> K[🧠 Qwen-Max 大模型];
        K -->|System Prompt| L[生成 J记财讯];
    end
    
    subgraph Delivery [4. 交付与归档]
        L --> M[生成 Markdown/HTML];
        L --> N[正则清洗 -> TTS 生成 MP3];
        M & N --> O[☁️ 上传阿里云盘];
        O --> P[🧹 清理 GitHub 旧文件];
    end


## 🚀 快速部署

### 1. Fork 本仓库
点击右上角的 **Fork** 按钮，将项目复制到你的 GitHub 账号下。

### 2. 配置 Secrets
进入仓库 `Settings` -> `Secrets and variables` -> `Actions`，添加以下密钥：

| 密钥名称 | 说明 | 获取方式 |
| :--- | :--- | :--- |
| `DASHSCOPE_API_KEY` | 阿里云百炼大模型 API | [阿里云百炼平台](https://dashscope.console.aliyun.com/) |
| `ALIYUN_REFRESH_TOKEN` | 阿里云盘上传凭证 | 使用 [aligo](https://github.com/wxy247/aligo) 获取 |
| `BARK_KEY` | (可选) iPhone 推送密钥 | App Store 下载 [Bark](https://apps.apple.com/us/app/bark-customed-notifications/id1403753865) |

### 3. 上传 OPML (可选)
如果你有自己的 RSS 订阅列表，将其导出为 `hn_popular_blogs_2025.opml` 并上传到仓库根目录，系统会自动读取其中的博客源。

### 4. 手动运行测试
进入 `Actions` 页面，选择 `Daily AI Morning Briefing`，点击 **Run workflow**。

---


