import os
import sys
import re
import time
import glob
import logging
import asyncio
import random
import requests
import feedparser
import markdown
import concurrent.futures
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from http import HTTPStatus
import edge_tts
import dashscope
from aligo import Aligo

# ================= 0. 全局配置 =================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("J-Intel")

# 🟢 核心：强制锁定北京时间 (UTC+8)
# 无论 GitHub Actions 服务器在哪，都以北京时间为准
utc_now = datetime.utcnow()
BEIJING_NOW = utc_now + timedelta(hours=8)

# 日期格式化
DATE_STR = BEIJING_NOW.strftime('%Y%m%d') # 文件名用
DISPLAY_DATE = BEIJING_NOW.strftime('%Y年%m月%d日') # 报告显示用
WEEK_DAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
DISPLAY_WEEKDAY = WEEK_DAYS[BEIJING_NOW.weekday()]

# 环境变量
DASHSCOPE_API_KEY = os.getenv('DASHSCOPE_API_KEY')
BARK_KEY = os.getenv('BARK_KEY')
ALIYUN_TOKEN = os.getenv('ALIYUN_REFRESH_TOKEN')
GITHUB_REPO = os.getenv('GITHUB_REPOSITORY', 'My-Daily-AI-Report')

# 输出路径
OUTPUT_DIR = 'output'
AUDIO_FILE = f'{OUTPUT_DIR}/briefing_{DATE_STR}.mp3'
MD_FILE = f'{OUTPUT_DIR}/briefing_{DATE_STR}.md'
HTML_FILE = f'{OUTPUT_DIR}/briefing_{DATE_STR}.html'

# ================= 1. 信源分层策略 (Stratified Source Strategy) =================

def load_opml_sources(file_path='hn_popular_blogs_2025.opml'):
    """解析 OPML 文件，提取深度博客 RSS"""
    sources = []
    if os.path.exists(file_path):
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            for outline in root.findall(".//outline[@type='rss']"):
                url = outline.get('xmlUrl')
                if url: sources.append(url)
            logger.info(f"📂 已加载 OPML 深度源: {len(sources)} 个")
        except Exception as e:
            logger.error(f"❌ OPML 解析失败: {e}")
    return sources

def get_rss_layers():
    opml_blogs = load_opml_sources()
    # 随机抽取 3 个博客防止 token 爆炸，保持每日新鲜感
    selected_blogs = random.sample(opml_blogs, min(3, len(opml_blogs))) if opml_blogs else []

    return {
        # 第一层：实时信号 (高频，快讯)
        "L1_Signal": {
            "weight": 1, 
            "urls": [
                "https://rsshub.rssforever.com/wallstreetcn/live/global/2", # 华尔街见闻 Live
                "https://rsshub.rssforever.com/cls/telegraph/red",          # 财联社电报
                "https://rsshub.app/news/xhsxw"                               # 新华社
            ]
        },
        # 第二层：行业解读 (商业价值分析主力)
        "L2_Industry": {
            "weight": 3, 
            "urls": [
                "https://36kr.com/feed",
                "https://rsshub.app/huxiu/channel/103", # 虎嗅
                "https://rsshub.rssforever.com/yicai/headline" # 第一财经
            ]
        },
        # 第三层：技术情报 (低密度)
        "L3_Tech": {
            "weight": 2,
            "urls": [
                "https://news.ycombinator.com/rss",
                "https://rsshub.app/github/trending/daily/python",
                "https://rsshub.app/arxiv/user/karpathy" 
            ]
        },
        # 第四层：深度洞察 (周报级/低频)
        "L4_Deep": {
            "weight": 2,
            "urls": selected_blogs + [
                "https://rsshub.rssforever.com/eastmoney/report/strategyreport" # 研报
            ]
        }
    }

# ================= 2. 智能评分与清洗 =================

KW_HIGH_VALUE = ["融资", "财报", "暴涨", "暴跌", "政策", "首发", "独家", "SaaS", "变现", "套利", "红利", "风口", "底层逻辑", "架构", "开源"]
KW_LOW_VALUE = ["促销", "抽奖", "八卦", "预告", "开箱", "体验", "游戏", "电影", "综艺"]

def calculate_score(title, summary, base_weight):
    """
    商业价值评分 (1-5分)
    < 3分：丢弃 (过滤噪音)
    >= 3分：进入快讯
    >= 4分：进入深度拆解候选池
    """
    score = base_weight
    content = (title + summary).lower()
    
    for kw in KW_HIGH_VALUE:
        if kw in content: score += 1
    for kw in KW_LOW_VALUE:
        if kw in content: score -= 2
        
    return max(1, min(5, score))

def clean_text_for_tts(text: str) -> str:
    """
    🎤 TTS 专用清洗：移除 Markdown 符号，防止读出乱码
    """
    # 1. 移除 Markdown 链接 [text](url) -> text
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    # 2. 移除加粗 **text** -> text
    text = re.sub(r'\*\*([^\*]+)\*\*', r'\1', text)
    # 3. 移除标题符号 #
    text = re.sub(r'#+\s', '', text)
    # 4. 移除代码块
    text = re.sub(r'```[\s\S]*?```', '', text)
    # 5. 移除列表符号
    text = re.sub(r'^\s*[-*]\s', '', text, flags=re.MULTILINE)
    # 6. 移除 HTML 标签
    text = re.sub(r'<[^>]+>', '', text)
    # 7. 移除分隔线
    text = re.sub(r'[-=]{3,}', '', text)
    # 8. 移除多余空行
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()

# ================= 3. 并行采集引擎 =================

def fetch_single_feed(url, layer_name, base_weight):
    headers = {'User-Agent': 'Mozilla/5.0 (J-Intel/3.0)'}
    items = []
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        feed = feedparser.parse(resp.content)
        
        # ⏰ 时间过滤：只取北京时间过去 24 小时内的
        cutoff_time = BEIJING_NOW - timedelta(hours=24)
        
        for entry in feed.entries[:8]: 
            pub_time = BEIJING_NOW # 默认最新
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                try:
                    # feedparser 解析的是 UTC，需 +8 转北京时间
                    pub_time = datetime(*entry.published_parsed[:6]) + timedelta(hours=8)
                except: pass
            
            if pub_time > cutoff_time:
                title = entry.get('title', '')
                summary = entry.get('summary', '')[:300]
                link = entry.get('link', '')
                
                score = calculate_score(title, summary, base_weight)
                
                if score >= 3: # 🔴 过滤机制：低于3分直接丢弃
                    items.append({
                        "layer": layer_name,
                        "title": title,
                        "summary": summary,
                        "score": score,
                        "source": feed.feed.get('title', 'Unknown')
                    })
    except Exception as e:
        pass 
    return items

def fetch_all_data():
    logger.info("🚀 启动全层级情报扫描...")
    layers = get_rss_layers()
    all_news = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = []
        for layer_name, config in layers.items():
            for url in config['urls']:
                futures.append(executor.submit(fetch_single_feed, url, layer_name, config['weight']))
        
        for future in concurrent.futures.as_completed(futures):
            all_news.extend(future.result())
            
    # 按分数降序排列
    all_news.sort(key=lambda x: x['score'], reverse=True)
    logger.info(f"✅ 采集完成，筛选出 {len(all_news)} 条高价值情报")
    return all_news

# ================= 4. J记财讯 AI 分析 =================

J_PROMPT = f"""
# Role: "J记财讯" 首席商业情报分析师

## Profile
你是一位嗅觉敏锐、逻辑严密的商业情报分析师。你的核心能力是从海量、碎片化的信息中剔除噪音，利用逆向思维锁定流量洼地，为用户提供“带钱味”的深度决策参考。

## Current Context
今天是：{DISPLAY_DATE} {DISPLAY_WEEKDAY} (北京时间)
所有分析必须基于“过去24小时”的情报。

## Constraints & Principles
1. **时效性**：仅关注过去24小时内的情报，严禁穿越历史。
2. **真实性**：严格基于事实，禁止编造。
3. **去重合并**：对相似新闻进行合并。
4. **风格**：冷峻、客观、实用、直接。拒绝正确的废话。

## Workflow
请基于提供的【素材池】，输出以下两部分：

### Part 1: 全球热点速递 (Top 10)
* **筛选标准**：高商业价值、技术突破、政策剧变、巨头动向。
* **格式**：每条控制在150字以内。
* **内容**：一句话讲清发生了什么 + 对行业/搞钱的直接影响。

### Part 2: 深度搞钱逻辑 (Deep Dive)
* **筛选**：从热点中嗅出“钱味”最浓的 1-3 个话题。
* **思维模型 (作为内核)**：
  1. 焦虑信号：谁在焦虑？流量去哪了？
  2. 掘金铲子：定位生态位，找蓝海。
* **输出结构 (必须严格按此格式)**：

#### 标题：[核心机会/痛点] - [具体的搞钱方向]

**1. 表象与真相 (Phenomenon)**
* 简述新闻表象。
* 揭示背后的流量流向和焦虑人群（谁在买单？）。

**2. 机遇与风险辩证 (Analysis)**
* **生态位分析**：当前处于产业链的哪个环节？
* **红海警示**：明确指出哪些方向已经过热。
* **蓝海判断**：指出真正的缺口在哪里。

**3. 搞钱路径 (Actionable Path)**
* **行动建议**：(如：开发插件/制作SOP/搬运信息差)
* **Next Step**：给读者的第一步执行指令。
"""

def analyze_with_ai(news_items):
    if not news_items:
        return f"# J记财讯 · {DISPLAY_DATE}\n\n**⚠️ 今日无有效情报信号**"

    # 构建素材池：取前 40 条高分新闻
    context = ""
    for i, item in enumerate(news_items[:40]):
        context += f"{i+1}. [{item['source']}] (分:{item['score']}) {item['title']}\n摘要：{item['summary']}\n\n"

    logger.info("🧠 AI 正在进行深度拆解...")
    try:
        dashscope.api_key = DASHSCOPE_API_KEY
        response = dashscope.Generation.call(
            model='qwen-max', 
            messages=[
                {'role': 'system', 'content': J_PROMPT},
                {'role': 'user', 'content': f"今日情报素材池：\n{context}"}
            ]
        )
        if response.status_code == HTTPStatus.OK:
            return f"# J记财讯 ({DISPLAY_DATE})\n\n" + response.output.text
        else:
            return "❌ AI 服务暂时不可用"
    except Exception as e:
        logger.error(f"AI Error: {e}")
        return "❌ 分析系统发生错误"

# ================= 5. 生成交付物 (Markdown, HTML, Audio) =================

async def generate_assets(content):
    if not os.path.exists(OUTPUT_DIR): os.makedirs(OUTPUT_DIR)
    
    # 1. 保存 Markdown
    with open(MD_FILE, 'w', encoding='utf-8') as f: f.write(content)
    logger.info(f"📄 MD 保存: {MD_FILE}")
    
    # 2. 生成 HTML (移动端适配)
    html_body = markdown.markdown(content)
    html_template = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>J记财讯 {DISPLAY_DATE}</title>
        <style>
            body {{ font-family: -apple-system, system-ui, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; background: #f2f2f7; color: #1c1c1e; }}
            .container {{ background: #fff; padding: 25px; border-radius: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); }}
            h1 {{ font-size: 24px; color: #000; margin-bottom: 5px; }}
            .date {{ color: #8e8e93; font-size: 14px; margin-bottom: 25px; }}
            h2 {{ margin-top: 35px; padding-bottom: 10px; border-bottom: 2px solid #007aff; color: #007aff; }}
            h4 {{ background: #f2f2f
