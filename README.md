# 🤖 私人晨间情报官

每天早上 7 点自动生成 40 分钟深度商业播客

## 📻 功能特点

- 📰 **全景扫描**：全球商业科技 + 中国民生动态（中国内容占50%）
- 🔍 **深度分析**：5-6 个话题的投研级分析（现象→本质→搞钱路径→风险预警）
- 🎙️ **AI 语音**：Edge-TTS 自然播报，适合通勤收听
- 📱 **推送通知**：生成完毕自动推送到 iPhone（Bark App）
- 🎧 **播客订阅**：支持小宇宙 App 自动更新

## 🎧 如何订阅

在**小宇宙 App**中添加以下 RSS 地址：
```
https://raw.githubusercontent.com/janicexu40-wq/My-Daily-AI-Report/main/feed.xml
```

**订阅步骤**：
1. 打开小宇宙 App
2. 点击右下角 **+** 号
3. 选择 **通过 RSS 订阅**
4. 粘贴上面的地址

## 🚀 部署状态

查看最新运行状态：点击仓库顶部的 **Actions** 标签

每天北京时间早上 7:00 自动运行

## 🔧 自定义配置

### 修改新闻源

编辑 `main.py` 第 30-36 行的 `RSS_SOURCES` 列表：
```python
RSS_SOURCES = [
    'https://www.36kr.com/feed',          # 36氪
    'https://www.huxiu.com/rss/0.xml',    # 虎嗅
    'https://www.thepaper.cn/rss_channel.jsp',  # 澎湃新闻
    # 添加你想要的其他 RSS 源
]
```

### 更换语音音色

编辑 `main.py` 第 45 行：

- **当前**：`zh-CN-YunxiNeural`（成熟男声）
- **女声**：`zh-CN-XiaoxiaoNeural`（温柔女声）
- **更多音色**：[查看完整列表](https://speech.microsoft.com/portal/voicegallery)

### 调整运行时间

编辑 `.github/workflows/daily.yml` 第 6 行：
```yaml
- cron: '0 23 * * *'  # 北京时间早上 7 点（UTC 23:00）
```

修改示例：
- 早上 6 点：`'0 22 * * *'`
- 晚上 9 点：`'0 13 * * *'`
- 中午 12 点：`'0 4 * * *'`

## 🔑 必需配置

在 **Settings** → **Secrets and variables** → **Actions** 中添加：

| 密钥名称 | 说明 | 获取方式 |
|---------|------|---------|
| `DASHSCOPE_API_KEY` | 阿里云通义千问 API | [阿里云百炼平台](https://dashscope.console.aliyun.com/) |
| `BARK_KEY` | iPhone 推送通知密钥 | Bark App 中查看（格式如 `xxxxxx`） |

## 📊 输出文件

每次运行会生成以下文件：
```
output/
├── briefing.mp3    # 音频文件（约 30-40 分钟）
└── briefing.txt    # 文字稿（约 8000 字）

feed.xml            # RSS 订阅源
```

## ⚙️ 技术架构

- **AI 模型**：阿里云 Qwen3-Max-Thinking
- **语音合成**：Microsoft Edge-TTS
- **自动化**：GitHub Actions（每日定时运行）
- **新闻源**：36氪、虎嗅、澎湃、财新、界面新闻等

## 🐛 故障排查

### Actions 运行失败

1. 检查 **Settings** → **Secrets** 中的密钥是否正确
2. 查看 **Actions** 标签页的错误日志
3. 确认阿里云 API 额度是否充足

### 小宇宙无法订阅

1. 确保仓库是 **Public**（公开状态）
2. 确认至少运行过一次，生成了 `feed.xml` 文件
3. 等待 5-10 分钟后重试

### 音频无法播放

1. 检查 `output/briefing.mp3` 是否成功生成
2. 确认 GitHub Actions 运行完成（绿色✅）
3. 刷新小宇宙 RSS 订阅

## 📝 更新日志

- **2026-01-27**：初始版本发布

---

**隐私说明**：本项目仅供个人使用，所有数据存储在你的 GitHub 仓库中，不会上传到任何第三方服务器。
