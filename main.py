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
2. **真实性**：严格基于事实，禁止编造。若是预测，必须显式标注“*基于当前数据的推测*”。
3. **去重合并**：对相似新闻进行合并，提取核心增量信息。
4. **风格**：冷峻、客观、实用、直接、行动导向。拒绝正确的废话，拒绝煽情。
5. **输出限制**：严格遵守字数限制。

## Workflow
你需要处理输入的信息（或自行检索今日热点），并按以下两个部分输出：

### Part 1: 全球热点速递 (Top 10)
* **筛选标准**：高商业价值、技术突破、政策剧变、巨头动向。
* **数量**：精选10条。
* **格式**：每条控制在150字以内。
* **内容**：一句话讲清发生了什么 + 对行业/搞钱的直接影响。

### Part 2: 深度搞钱逻辑 (Deep Dive)
* **筛选**：从上述热点中，嗅出“钱味”最浓的 1-3 个话题。
* **思维模型 (作为内核)**：
    1. 焦虑信号 (Signal)：忽略情绪，看流量流向哪里？谁在焦虑（新手/老手/企业主）？哪里有海量新人涌入但基建简陋？
    2. 掘金铲子 (Shovel)：定位生态位（上/中/下游）。哪里是红海（避坑）？哪里是蓝海（机会）？
* **输出结构 (必须按此格式输出)**：
    * 每条分析控制在 1000 字以内，采用议论文格式。
    
    #### 标题：[核心机会/痛点] - [具体的搞钱方向]
    
    **1. 表象与真相 (Phenomenon)**
    * 简述新闻表象。
    * 揭示背后的流量流向和焦虑人群（谁在买单？）。
    
    **2. 机遇与风险辩证 (Analysis)**
    * **生态位分析**：当前处于产业链的哪个环节？
    * **红海警示**：明确指出哪些方向已经过热，不可触碰。
    * **蓝海判断**：基于“供需不平衡”原理，指出真正的缺口在哪里。
    
    **3. 搞钱路径 (Actionable Path)**
    * 基于今日情报，给出极度具体的行动建议。
    * 格式参考：*开发某类插件 / 制作某类SOP教程 / 提供某类数据清洗服务 / 搬运某类信息差*。
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
        # 增加超时时间，防止 AI 思考太久导致连接中断
        response = dashscope.Generation.call(
            model='qwen3-max', 
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

# ================= 5. 生成交付物 =================

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
            h4 {{ background: #f2f2f7; padding: 12px; border-radius: 8px; margin-top: 25px; border-left: 5px solid #34c759; }}
            strong {{ color: #3a3a3c; font-weight: 700; }}
            audio {{ width: 100%; margin: 20px 0; border-radius: 30px; }}
            li {{ margin-bottom: 10px; line-height: 1.6; }}
            .footer {{ text-align: center; margin-top: 40px; color: #c7c7cc; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🦁 J记财讯 · 商业内参</h1>
            <div class="date">📅 {DISPLAY_DATE} {DISPLAY_WEEKDAY} | 📍 Beijing Time</div>
            
            <div style="background:#e5f1ff; padding:15px; border-radius:10px; margin-bottom:20px;">
                <strong>🎧 语音播报：</strong>
                <audio controls src="briefing_{DATE_STR}.mp3"></audio>
            </div>
            
            {html_body}
            
            <div class="footer">Powered by J-Intel System | Data: Global RSS</div>
        </div>
    </body>
    </html>
    """
    with open(HTML_FILE, 'w', encoding='utf-8') as f: f.write(html_template)
    logger.info(f"🌐 HTML 保存: {HTML_FILE}")
    
    # 3. 生成 MP3 (使用清洗后的纯文本)
    # ✅ 关键修正：这里统一使用了 clean_text_for_tts 这个函数名
    tts_text = clean_text_for_tts(content)
    
    intro = f"今天是{DISPLAY_DATE}，{DISPLAY_WEEKDAY}。欢迎收听J记财讯。\n\n"
    final_tts_text = intro + tts_text[:2500] 
    
    communicate = edge_tts.Communicate(final_tts_text, "zh-CN-YunxiNeural", rate="+10%")
    await communicate.save(AUDIO_FILE)
    logger.info(f"🎙️ MP3 保存: {AUDIO_FILE}")
    
    return [MD_FILE, HTML_FILE, AUDIO_FILE]

# ================= 6. 云端归档与本地清理 =================

def upload_and_cleanup(files):
    # 1. 阿里云盘上传
    if ALIYUN_TOKEN:
        try:
            logger.info("☁️ 连接阿里云盘...")
            ali = Aligo(level=logging.ERROR, refresh_token=ALIYUN_TOKEN)
            remote_folder = ali.get_folder_by_path('/晨间情报')
            if not remote_folder:
                ali.create_folder('/晨间情报')
                remote_folder = ali.get_folder_by_path('/晨间情报')
            
            for f in files:
                ali.upload_file(f, remote_folder.file_id)
                logger.info(f"   ⬆️ 上传成功: {os.path.basename(f)}")
            logger.info("✅ 云盘备份完成")
        except Exception as e:
            logger.error(f"❌ 云盘上传失败: {e}")
    else:
        logger.warning("⚠️ 未配置 ALIYUN_REFRESH_TOKEN，跳过上传")

    # 2. 本地清理 (保留最近3天 - 基于文件名日期)
    logger.info("🧹 执行本地清理 (保留3天)...")
    
    cutoff_date = BEIJING_NOW - timedelta(days=3)
    cutoff_str = cutoff_date.strftime('%Y%m%d')
    
    for f in glob.glob(os.path.join(OUTPUT_DIR, '*')):
        filename = os.path.basename(f)
        match = re.search(r'(\d{8})', filename)
        if match:
            file_date_str = match.group(1)
            if file_date_str < cutoff_str:
                try:
                    os.remove(f)
                    logger.info(f"   🗑️ 删除旧文件: {filename}")
                except: pass

# ================= 主程序入口 =================

if __name__ == "__main__":
    # 1. 采集
    news_data = fetch_all_data()
    
    # 2. 分析
    report_content = analyze_with_ai(news_data)
    
    # 3. 生成文件
    generated_files = asyncio.run(generate_assets(report_content))
    
    # 4. 备份与清理
    upload_and_cleanup(generated_files)
    
    logger.info("🎉 J记财讯任务圆满完成")
