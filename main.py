import os
import asyncio
import feedparser
import edge_tts
import glob
import logging
from datetime import datetime, timedelta # 引入 timedelta 用于时区修正
from http import HTTPStatus
import dashscope
from aligo import Aligo

# ================= 1. 猎手雷达设置 =================
RSS_SOURCES = {
    "signals": [ # 【焦虑信号】寻找痛点
        "https://www.v2ex.com/index.xml", 
        "https://www.reddit.com/r/SaaS/new/.rss",
    ],
    "shovels": [ # 【掘金铲子】寻找工具
        "https://news.ycombinator.com/rss",
        "https://stratechery.com/feed/",
    ],
    "macro": [ # 【宏观风向】钱往哪里流
        "https://feed.36kr.com/feed",
    ]
}

# ================= 2. 猎手思维模型 =================
HUNTER_SYSTEM_PROMPT = """
你不再是新闻播报员，你是“晨间商业猎手”。你的任务是从信息中嗅出“钱味”。
请阅读以下聚合的全球情报，严格按照框架输出一份【商业情报内参】：

## 🎯 第一步：焦虑信号 (Signal)
* **逆向判断**：忽略热点情绪，指出流量正流向哪个具体细分领域？
* **痛点锁定**：谁在焦虑？(新手/老手/企业主) 他们的具体痛苦是什么？(太贵/太慢/太难)
* **机会判断**：哪里有“海量新人涌入”但“基础设施只有简陋的中游产品”，哪里就是机会。

## 🛠 第二步：掘金铲子 (Shovel)
* **生态位分析**：当前处于产业链的上游(工具)、中游(生产)还是下游(分发)？
* **避坑指南**：明确指出哪里是红海，不要去碰。
* **搞钱路径**：基于今日情报，给出一个具体的行动建议。(例如：开发某类插件、制作某类教程、提供某类数据服务)

## 📢 猎手广播 (Podcast Script)
(请生成一段300字以内的口语化播报文稿。
要求：语气犀利、自信，像个老朋友一样告诉听众今天的最大机会在哪里。
不要念新闻标题，直接说结论和机会点。)
"""

# ================= 3. 核心功能函数 =================

def fetch_rss_intel(category):
    """抓取 RSS 并进行简单清洗"""
    print(f"🕵️‍♂️ [猎手雷达] 正在扫描 {category} 频道...")
    combined_content = ""
    for url in RSS_SOURCES.get(category, []):
        try:
            feed = feedparser.parse(url)
            # 只取前 3 条，避免 Token 溢出
            for entry in feed.entries[:3]:
                title = getattr(entry, 'title', '无标题')
                link = getattr(entry, 'link', '无链接')
                summary = getattr(entry, 'summary', '')[:200] 
                combined_content += f"【标题】{title}\n【链接】{link}\n【摘要】{summary}\n\n"
        except Exception as e:
            print(f"⚠️ 抓取失败 {url}: {e}")
    return combined_content

def analyze_with_hunter_ai(content):
    """调用通义千问进行深度分析"""
    if not content: return "今日雷达未捕捉到有效信号。"
    
    print("🧠 [猎手大脑] 正在拆解商业逻辑...")
    try:
        dashscope.api_key = os.getenv("DASHSCOPE_API_KEY")
        response = dashscope.Generation.call(
            model=dashscope.Generation.Models.qwen_turbo, 
            messages=[{'role': 'system', 'content': HUNTER_SYSTEM_PROMPT},
                      {'role': 'user', 'content': f"今日情报汇总数据：\n{content}"}]
        )
        if response.status_code == HTTPStatus.OK:
            return response.output.text
        else:
            print(f"❌ AI分析失败: {response.code} - {response.message}")
            return "AI 暂时掉线。"
    except Exception as e:
        print(f"❌ 系统错误: {e}")
        return f"系统运行出错: {e}"

def upload_to_aliyun_drive(file_paths):
    """上传文件到阿里云盘 /晨间情报 文件夹"""
    print("☁️ [云端归档] 正在连接阿里云盘...")
    try:
        refresh_token = os.getenv("ALIYUN_REFRESH_TOKEN")
        if not refresh_token:
            print("❌ 未找到 ALIYUN_REFRESH_TOKEN，跳过上传。")
            return

        # 初始化 Aligo
        ali = Aligo(level=logging.INFO, refresh_token=refresh_token)
        
        # 获取或创建目标文件夹
        remote_
