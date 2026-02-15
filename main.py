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
import dashscope # 阿里云百炼 SDK
from aligo import Aligo

# ================= 0. 全局配置 =================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("J-Intel")

# 🟢 核心：强制锁定北京时间 (UTC+8)
utc_now = datetime.utcnow()
BEIJING_NOW = utc_now + timedelta(hours=8)

DATE_STR = BEIJING_NOW.strftime('%Y%m%d')
DISPLAY_DATE = BEIJING_NOW.strftime('%Y年%m月%d日')
WEEK_DAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
DISPLAY_WEEKDAY = WEEK_DAYS[BEIJING_NOW.weekday()]

# 环境变量
DASHSCOPE_API_KEY = os.getenv('DASHSCOPE_API_KEY') # 阿里云 Key (通用)
BARK_KEY = os.getenv('BARK_KEY')
ALIYUN_TOKEN = os.getenv('ALIYUN_REFRESH_TOKEN')
GITHUB_REPO = os.getenv('GITHUB_REPOSITORY', 'My-Daily-AI-Report')

# 输出路径
OUTPUT_DIR = 'output'
AUDIO_FILE = f'{OUTPUT_DIR}/briefing_{DATE_STR}.mp3'
MD_FILE = f'{OUTPUT_DIR}/briefing_{DATE_STR}.md'
HTML_FILE = f'{OUTPUT_DIR}/briefing_{DATE_STR}.html'
RSS_FILE = 'feed.xml'

# ================= 1. 信源分层策略 =================

def load_opml_sources(file_path='hn_popular_blogs_2025.opml'):
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
    selected_blogs = random.sample(opml_blogs, min(3, len(opml_blogs))) if opml_blogs else []

    return {
        "L1_Signal": {
            "weight": 1, 
            "urls": [
                "https://rsshub.rssforever.com/wallstreetcn/live/global/2",
                "https://rsshub.rssforever.com/cls/telegraph/red",
                "https://rsshub.app/news/xhsxw"
            ]
        },
        "L2_Industry": {
            "weight": 3, 
            "urls": [
                "https://36kr.com/feed",
                "https://rsshub.app/huxiu/channel/103",
                "https://rsshub.rssforever.com/yicai/headline"
            ]
        },
        "L3_Tech": {
            "weight": 2,
            "urls": [
                "https://news.ycombinator.com/rss",
                "https://rsshub.app/github/trending/daily/python",
                "https://rsshub.app/arxiv/user/karpathy" 
            ]
        },
        "L4_Deep": {
            "weight": 2,
            "urls": selected_blogs + [
                "https://rsshub.rssforever.com/eastmoney/report/strategyreport"
            ]
        }
    }

# ================= 2. 智能评分与清洗 =================

KW_HIGH_VALUE = ["融资", "财报", "暴涨", "暴跌", "政策", "首发", "独家", "SaaS", "变现", "套利", "红利", "风口", "底层逻辑", "架构", "开源"]
KW_LOW_VALUE = ["促销", "抽奖", "八卦", "预告", "开箱", "体验", "游戏", "电影", "综艺"]

def calculate_score(title, summary, base_weight):
    score = base_weight
    content = (title + summary).lower()
    for kw in KW_HIGH_VALUE:
        if kw in content: score += 1
    for kw in KW_LOW_VALUE:
        if kw in content: score -= 2
    return max(1, min(5, score))

def clean_text_for_tts(text: str) -> str:
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    text = re.sub(r'\*\*([^\*]+)\*\*', r'\1', text)
    text = re.sub(r'#+\s', '', text)
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'^\s*[-*]\s', '', text, flags=re.MULTILINE)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'[-=]{3,}', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

# ================= 3. 并行采集引擎 =================

def fetch_single_feed(url, layer_name, base_weight):
    headers = {'User-Agent': 'Mozilla/5.0 (J-Intel/3.0)'}
    items = []
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        feed = feedparser.parse(resp.content)
        cutoff_time = BEIJING_NOW - timedelta(hours=24)
        
        for entry in feed.entries[:8]: 
            pub_time = BEIJING_NOW
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                try:
                    pub_time = datetime(*entry.published_parsed[:6]) + timedelta(hours=8)
                except: pass
            
            if pub_time > cutoff_time:
                title = entry.get('title', '')
                summary = entry.get('summary', '')[:300]
                score = calculate_score(title, summary, base_weight)
                
                if score >= 3:
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
            
    all_news.sort(key=lambda x: x['score'], reverse=True)
    logger.info(f"✅ 采集完成，筛选出 {len(all_news)} 条高价值情报")
    return all_news

# ================= 4. 双模型流水线 (阿里云 All-in-One) =================

# --- Stage 1: Qwen3-Max (结构师 + 猎手) ---
QWEN_PROMPT = f"""
# Role: "J记财讯" 首席情报架构师

## Task
你是流水线的第一环。请根据今日素材，完成两项任务：

### 任务一：撰写 Part 1 (Top 15)
* **筛选标准**：高商业价值、技术突破、政策剧变、巨头动向。
* **数量**：精选15条。
* **格式**：每条控制在200字以内。
* **内容结构**：
    - **【领域标签】** 总结原新闻内容（客观陈述，1-2句话）+ AI模型分析（搞钱指向，1-2句话）
    - **（消息来源：XX+日期）**
* **风格要求**：
    - 电头：**J记财讯 | 北京{datetime.now().strftime('%m月%d日')}电**
    - 前半部分：客观总结原新闻，不掺杂分析
    - 后半部分：AI模型基于事实的冷峻分析，必须带**搞钱指向**——谁受影响 + 该做什么
    - 时效词：内测/刚刚/紧急/48小时内/窗口期/首当其冲

### 任务二：构建 Part 2 (Deep Dive Draft)
* **筛选**：从素材中选出 1-3 个“钱味”最浓的搞钱话题。
* **输出**：提供原始分析素材草稿（包含现象、逻辑、红海蓝海判断、具体动作），不要写成最终文章，把素材留给下一环的主笔进行润色。

## Output Format (严格遵守)
请用 "===SPLIT===" 将两部分隔开。

### Part 1: 全球热点速递 (Top 15)
(请按以下范例格式输出 15 条)
> 【AI】OpenAI官方博客2月14日发布，GPT-5已进入灰度测试阶段，新增视频生成功能。该技术将降低影视内容制作门槛，传统外包报价模式承压。短视频剪辑师、影视外包公司首当其冲，需48小时内评估技能升级路径或转向创意策划层，避免被工具替代。（消息来源：OpenAI官方博客2月14日）

===SPLIT===

### Part 2 草稿
(请列出 1-3 个话题的原始分析素材，供下一环节使用)
"""

# --- Stage 2: Kimi (Moonshot via Aliyun) (主笔 + 深度锐化) ---
KIMI_PROMPT = """
# Role: "J记财讯" 资深主笔

## Task
你收到了架构师提供的【Deep Dive 草稿】。你的任务是将其重写为最终的 **Part 2: 深度搞钱逻辑**。

## 核心写作要求 (Term + Layman 结构)
必须严格遵守以下段落结构：**每个模块先给【商业术语框架】，紧跟一句【人话总结】，两段合并为一段，去掉"说人话："标签。**

## Output Structure & Example (Must Follow)
请严格模仿以下范文的【节奏】和【术语+人话】的混合方式：

#### 标题：[核心机会/痛点] - [具体的搞钱方向]

**1. 表象与真相 (Phenomenon)**
**场景迁移与情绪价值消费**：剧本杀带火的"恋陪"服务，正在向滑雪、徒步、Citywalk等领域**场景迁移**。本质是**情绪价值消费**崛起——Z世代不再只为实物买单，更愿为"感觉"付费。疫情后**社交补偿心理**强烈，"陪伴"成了**非标品**（没有统一标准的商品），这正是**流量洼地**。年轻人寂寞愿意花钱找人陪，这行还不饱和，早进早占坑。

**2. 机遇与风险辩证 (Analysis)**
**生态位分析**：当前处于产业链**下游**（直接服务C端），上游是平台抽成，中游是培训缺位，下游是服务混乱。现在切入中游标准化或下游专业化，都是机会。
**红海警示**：纯颜值陪聊、低价陪玩已经**红海化**，价格战惨烈，平台抽成30%-50%，新进入者必死，**避坑**。
**蓝海判断**：基于**供需错配**，"技能+陪伴"的**复合型人才**（会滑雪+懂急救+会拍照）极度稀缺，客单价能翻三倍，这就是**差异化壁垒**。有真本事就是降维打击。

**3. 搞钱路径 (Actionable Path)**
**第一步，垂直切入（单点突破）**：选一个**高净值场景**（滑雪、潜水），锁定**付费意愿强的人群**（一线城市白领）。**单点突破**比**泛化运营**更容易建立**品牌心智**。先做好一件事，别啥都想接。
**第二步，SOP化（建立信任资产）**：制定**服务标准作业程序**：接单流程、安全协议、应急预案。把**非标服务**尽量**标准化**，降低客户决策成本。写个说明书，让客户觉得找你放心。
**第三步，数据飞轮（增长闭环）**：收集**用户行为数据**，优化**匹配效率**和**服务颗粒度**。好口碑带来**复购**和**转介绍**。每单完事问问感受，不断改进，生意自己滚起来。
**Next Step**：24小时内可启动的具体动作，[极度具体，如"注册XX平台账号""整理你的技能清单""联系3个潜在客户"]。
"""

def call_qwen_structure(context):
    logger.info("🧠 [Stage 1] Qwen3-Max 正在构建骨架...")
    try:
        dashscope.api_key = DASHSCOPE_API_KEY
        # 阿里云最强模型
        response = dashscope.Generation.call(
            model='qwen3-max-2026-01-23', 
            messages=[
                {'role': 'system', 'content': QWEN_PROMPT},
                {'role': 'user', 'content': f"今日情报素材池：\n{context}"}
            ]
        )
        if response.status_code == HTTPStatus.OK:
            return response.output.text
        else:
            logger.error(f"Qwen Error: {response.message}")
            return None
    except Exception as e:
        logger.error(f"Qwen Exception: {e}")
        return None

def call_kimi_refine(draft_content):
    logger.info("💎 [Stage 2] Kimi (via Aliyun) 正在深度锐化...")
    try:
        dashscope.api_key = DASHSCOPE_API_KEY
        # 尝试调用 Kimi (Moonshot)
        model_name = 'moonshot-v1-32k' 
        
        response = dashscope.Generation.call(
            model=model_name, 
            messages=[
                {"role": "system", "content": KIMI_PROMPT},
                {"role": "user", "content": f"请参考范文风格，深度润色以下草稿：\n\n{draft_content}"}
            ]
        )
        
        if response.status_code == HTTPStatus.OK:
            return f"### Part 2: 深度搞钱逻辑 (Deep Dive)\n\n{response.output.text}"
        else:
            # 降级策略
            logger.warning(f"Kimi Call Failed: {response.message} -> 降级使用 Qwen-Plus 润色")
            fallback_resp = dashscope.Generation.call(
                model='qwen-plus',
                messages=[
                    {"role": "system", "content": KIMI_PROMPT},
                    {"role": "user", "content": f"请参考范文风格，深度润色以下草稿：\n\n{draft_content}"}
                ]
            )
            return f"### Part 2: 深度搞钱逻辑 (Deep Dive)\n\n{fallback_resp.output.text}"

    except Exception as e:
        logger.error(f"Kimi/Fallback Exception: {e}")
        return f"### Part 2 (Kimi调用失败)\n\n{draft_content}"

def dual_model_pipeline(news_items):
    if not news_items:
        return f"# J记财讯 · {DISPLAY_DATE}\n\n**⚠️ 今日无有效情报信号**"

    # 1. 准备素材
    context = ""
    for i, item in enumerate(news_items[:80]):
        context += f"{i+1}. [{item['source']}] (分:{item['score']}) {item['title']}\n摘要：{item['summary']}\n\n"

    # 2. Qwen: 结构化 + 初筛
    qwen_output = call_qwen_structure(context)
    if not qwen_output:
        return "❌ 报告生成失败 (Qwen阶段)"

    # 3. 拆分 Qwen 输出
    parts = qwen_output.split("===SPLIT===")
    if len(parts) == 2:
        part1_top15 = parts[0].strip()
        part2_draft = parts[1].strip()
    else:
        part1_top15 = qwen_output
        part2_draft = "（Qwen未正确输出分隔符，请查看原始日志）"

    # 4. Kimi: 深度润色 Part 2
    part2_final = call_kimi_refine(part2_draft)

    # 5. 组合
    return f"# J记财讯 ({DISPLAY_DATE})\n\n{part1_top15}\n\n---\n\n{part2_final}"

# ================= 5. 生成交付物 =================

def generate_rss(audio_url):
    logger.info("📡 正在生成 RSS Feed...")
    rss_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
<channel>
    <title>J记财讯</title>
    <description>每日商业情报内参</description>
    <link>https://github.com/{GITHUB_REPO}</link>
    <lastBuildDate>{datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')}</lastBuildDate>
    <item>
        <title>{DISPLAY_DATE} 情报内参</title>
        <description>J记财讯每日更新</description>
        <pubDate>{datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')}</pubDate>
        <enclosure url="{audio_url}" type="audio/mpeg" length="100000"/>
        <guid>{DATE_STR}</guid>
    </item>
</channel>
</rss>"""
    with open(RSS_FILE, 'w', encoding='utf-8') as f:
        f.write(rss_content)
    logger.info(f"✅ RSS 已生成: {RSS_FILE}")

async def generate_assets(content):
    if not os.path.exists(OUTPUT_DIR): os.makedirs(OUTPUT_DIR)
    
    with open(MD_FILE, 'w', encoding='utf-8') as f: f.write(content)
    logger.info(f"📄 MD 保存: {MD_FILE}")
    
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
    
    tts_text = clean_text_for_tts(content)
    intro = f"今天是{DISPLAY_DATE}，{DISPLAY_WEEKDAY}。欢迎收听J记财讯。\n\n"
    final_tts_text = intro + tts_text[:2500] 
    
    communicate = edge_tts.Communicate(final_tts_text, "zh-CN-YunxiNeural", rate="+10%")
    await communicate.save(AUDIO_FILE)
    logger.info(f"🎙️ MP3 保存: {AUDIO_FILE}")
    
    return [MD_FILE, HTML_FILE, AUDIO_FILE]

# ================= 6. 云端归档与清理 =================

def upload_and_cleanup(files):
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

def send_bark_notification(title, body, url=None):
    if not BARK_KEY:
        logger.warning("⚠️ 未配置 BARK_KEY，跳过推送")
        return
    
    try:
        safe_body = body.replace('\n', ' ')[:100] + "..."
        api_url = f"https://api.day.app/{BARK_KEY}/{title}/{safe_body}"
        params = {
            'group': 'J-Intel',
            'icon': 'https://cdn-icons-png.flaticon.com/512/2965/2965363.png'
        }
        if url:
            params['url'] = url
            
        requests.get(api_url, params=params, timeout=5)
        logger.info("✅ Bark 推送成功")
    except Exception as e:
        logger.error(f"❌ Bark 推送失败: {e}")

# ================= 主程序入口 =================

if __name__ == "__main__":
    # 1. 采集
    news_data = fetch_all_data()
    
    # 2. 分析 (双模型)
    report_content = dual_model_pipeline(news_data)
    
    # 3. 生成文件
    generated_files = asyncio.run(generate_assets(report_content))
    
    # 4. 生成 RSS
    if '/' in GITHUB_REPO:
        audio_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{OUTPUT_DIR}/briefing_{DATE_STR}.mp3"
    else:
        audio_url = ""
    generate_rss(audio_url)
    
    # 5. 备份与清理
    upload_and_cleanup(generated_files)
    
    # 6. 发送 Bark 推送
    if '/' in GITHUB_REPO:
        user, repo = GITHUB_REPO.split('/')
        page_url = f"https://{user}.github.io/{repo}/{OUTPUT_DIR}/briefing_{DATE_STR}.html"
    else:
        page_url = ""

    send_bark_notification(
        f"J记财讯 ({DISPLAY_DATE})",
        "今日商业情报已生成(Qwen+Kimi)，点击查看详情。",
        url=page_url
    )
    
    logger.info("🎉 J记财讯任务圆满完成")
