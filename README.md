🕵️‍♂️ 晨间猎手内参 (Morning Hunter Briefing)
"这不是简单的新闻播报，这是你的私人商业情报猎手。"
本项目每天早上 7 点自动运行，抓取全网核心财经/科技信息，通过 AI 扮演“商业情报猎手”进行深度拆解，生成 "快讯+深度" 的双模态情报，并自动同步到你的云盘和手机。
✨ 核心功能
📰 全景扫描 (Flash News)：聚合新华社、华尔街见闻、财联社等核心信源，按时间轴过滤噪音，只看干货。
🦁 猎手深度拆解：AI 独家分析框架：现状层 (The Facts) → 猎手拆解 (底层逻辑) → 搞钱路径 (行动指南)。
☁️ 阿里云盘自动同步：生成的 MP3 音频会自动上传到网盘，支持倍速播放、断点续传、后台听书。
📱 移动端网页体验：自动生成仿"微信公众号"风格的 HTML 网页（内置播放器），Bark 推送点击即达。
🎙️ 自然语音播报：使用 Edge-TTS 生成媲美真人的语音（支持 4000+ 字长文）。
📻 如何收听 (三种方式)
方式一：阿里云盘 (网盘党推荐) ☁️
适合习惯使用网盘听书、需要倍速播放的用户。
每天早上任务完成后，MP3 音频会自动上传到你的阿里云盘 /晨间情报 文件夹。
打开 阿里云盘 App，找到当天日期的文件直接播放。
方式二：手机网页 (图文+音频) 📱
适合需要边听边看文稿、查看深度分析文字的用户。
手机收到 Bark 通知的推送。
点击通知，直接跳转到当天的精美 HTML 情报页（内置播放器）。
网页示例地址：  
https://janicexu40-wq.github.io/My-Daily-AI-Report/output/briefing_20260201.html  
(注：日期部分 20260201 会随每天生成自动变化)
方式三：播客订阅 (RSS) 🎙️
适合使用小宇宙、Apple Podcast 的泛用型播客用户。
复制以下 RSS 地址添加订阅：
[https://raw.githubusercontent.com/janicexu40-wq/My-Daily-AI-Report/main/feed.xml](https://raw.githubusercontent.com/janicexu40-wq/My-Daily-AI-Report/main/feed.xml)
🚀 部署指南
1. 配置密钥 (Secrets)
在仓库的 Settings → Secrets and variables → Actions 中添加以下 3 个密钥：
密钥名称	说明	获取方式
DASHSCOPE_API_KEY	阿里云通义千问 API	阿里云百炼平台
BARK_KEY	iPhone 推送通知密钥	App Store 下载 Bark
ALIYUN_REFRESH_TOKEN	阿里云盘上传凭证	获取 Refresh Token 用于网盘自动上传
2. 开启 GitHub Pages (🔴 关键步骤)
为了让手机能访问生成的 HTML 网页，必须开启此功能：
进入仓库 Settings。
左侧栏点击 Pages。
Build and deployment -> Source 选择 Deploy from a branch。
Branch 选择 main，文件夹选择 / (root)。
点击 Save。
3. 检查权限
进入 Settings → Actions → General，滚动到底部 Workflow permissions，确保勾选：
✅ Read and write permissions
🗞️ 核心情报源
本项目采用混合信源策略，确保信息全面且权威（可在 main.py 中修改）：
第一梯队 (金融核心)：华尔街见闻 (Live)、财联社 (电报)
第二梯队 (权威定调)：新华社、第一财经、澎湃新闻
第三梯队 (深度/科技)：虎嗅、36氪、少数派 (sspai)、人人都是产品经理
第四梯队 (研报)：东方财富策略研报、南方周末
🔧 高级配置
调整运行时间
编辑 .github/workflows/daily.yml：
- cron: '0 23 * * *'  # 对应北京时间早上 7:00
提示：GitHub Actions 使用 UTC 时间，北京时间 = UTC + 8。
更换声音
编辑 main.py 中的 VOICE_NAME：
zh-CN-YunxiNeural (默认，稳重男声)
zh-CN-XiaoxiaoNeural (活力女声)
📂 输出文件结构
每次运行会自动在 output/ 目录生成以下文件（只保留最近 3 天）：
output/  
├── briefing_20260201.mp3   # 🎙️ 音频 (上传至阿里云盘)  
├── briefing_20260201.html  # 📱 网页 (Bark 跳转)  
├── briefing_20260201.md    # 📝 Markdown 原稿  
└── briefing_20260201.txt   # (纯文本备份)  
feed.xml                    # 📡 RSS 订阅源
