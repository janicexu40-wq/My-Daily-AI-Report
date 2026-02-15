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
from dashscope import Generation, MultiModalConversation
from aligo import Aligo

# ── 模型重试配置 ──────────────────────────────────────────
MAX_RETRIES = 3          # 最大重试次数
RETRY_BASE_DELAY = 2     # 指数退避基数（秒）：第1次等2s，第2次等4s
# ─────────────────────────────────────────────────────────

# ================= 0. 全局配置 =================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("J-Intel")

# 🟢 1. 打印 SDK 版本 (用于调试环境确保支持 Kimi 思考模式)
try:
    logger.info(f"🔍 当前 DashScope SDK 版本: {dashscope.__version__}")
except:
    pass

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

# ================= 1. 信源分层策略 (升级版) =================

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
    # 从 80+ 个博客中随机抽取 5 个作为今日深度补充
    opml_blogs = load_opml_sources()
    selected_blogs = random.sample(opml_blogs, min(5, len(opml_blogs))) if opml_blogs else []

    return {
        # 🟢 L1: 市场信号 (快讯/电报) - 权重最高，捕捉异动
        "L1_Signal": {
            "weight": 2, 
            "urls": [
                "https://rsshub.rssforever.com/wallstreetcn/live/global/2", # 华尔街见闻-快讯
                "https://rsshub.rssforever.com/cls/telegraph/red",         # 财联社-电报
                "https://rsshub.app/news/xhsxw"                            # 新华社
            ]
        },
        # 🟢 L2: 行业热点 (头条/热榜) - 关注主流叙事
        "L2_Hot": {
            "weight": 2, 
            "urls": [
                "https://rsshub.rssforever.com/wallstreetcn/hot/day",      # 华尔街见闻-日榜
                "https://rsshub.rssforever.com/yicai/headline",            # 第一财经-头条
                "https://36kr.com/feed"                                    # 36Kr
            ]
        },
        # 🟢 L3: 深度思考 (博客/深度媒) - 寻找长逻辑
        "L3_Deep": {
            "weight": 2,
            "urls": selected_blogs + [                                     # OPML 随机源
                "https://rsshub.app/huxiu/channel/103",                    # 虎嗅-深案例
                "https://rsshub.rssforever.com/eastmoney/report/strategyreport" # 券商策略
            ]
        },
        # 🟢 L4: 硬核技术 (Tech/Dev) - 寻找工具铲子
        "L4_Tech": {
            "weight": 2,
            "urls": [
                "https://news.ycombinator.com/rss",                        # Hacker News
                "https://rsshub.app/github/trending/daily/python",         # GitHub Trending
                "https://rsshub.app/arxiv/user/karpathy"                   # Arxiv (AI前沿)
            ]
        }
    }

# ================= 2. 智能评分与清洗 =================

KW_HIGH_VALUE = ["融资", "财报", "暴涨", "暴跌", "政策", "首发", "独家", "SaaS", "变现", "套利", "红利", "风口", "底层逻辑", "架构", "开源", "复盘"]
KW_LOW_VALUE = ["促销", "抽奖", "八卦", "预告", "开箱", "体验", "游戏", "电影", "综艺", "明星"]

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
* **来源要求**：**请尽可能选择不同的媒体来源，不要让单一媒体（如36氪、华尔街见闻）占据超过50%的内容。**
* **格式**：每条控制在200字以内。
* **内容结构**：
    - **【领域标签】** 总结原新闻内容（客观陈述，1-2句话）+ AI模型分析（搞钱指向，1-2句话）
    - **（消息来源：XX+日期）**
* **风格要求**：
    - **开头固定格式**：**今天是{DISPLAY_DATE}，{DISPLAY_WEEKDAY}，一起了解过去24小时新闻。**
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
**今天是{DISPLAY_DATE}，{DISPLAY_WEEKDAY}，一起了解过去24小时新闻。**

> 【AI】OpenAI官方博客2月14日发布，GPT-5已进入灰度测试阶段，新增视频生成功能。该技术将降低影视内容制作门槛，传统外包报价模式承压。短视频剪辑师、影视外包公司首当其冲，需48小时内评估技能升级路径或转向创意策划层，避免被工具替代。（消息来源：OpenAI官方博客2月14日）

===SPLIT===

### Part 2 草稿
(请列出 1-3 个话题的原始分析素材，供下一环节使用)
"""

# --- Stage 2: Kimi (Moonshot via Aliyun) (主笔 + 深度锐化) ---
# 🟢 升级：人话翻译官 + 三段式结构 + 具体落地
KIMI_PROMPT = """
# Role: "J记财讯" 资深主笔（人话翻译官）

## Task
你收到了架构师提供的【Deep Dive 草稿】。你的任务是将其重写为最终的 **Part 2: 深度搞钱逻辑**。

**核心原则：说人话，让菜市场大妈都能听懂怎么赚钱。**

## 写作要求（三段式结构）

### 格式要求
- **标题**：【搞钱方向】+【具体机会点】，要抓人眼球
- **每部分结构**：先给**专业判断**（1句话），紧跟**人话解释**（2-3句话），合并成一段
- **禁止**：堆砌术语、学术腔、AI腔（"值得注意的是""笔者认为"等）

### 三段式内容

**1. 表象与真相（到底发生了什么？）**
- 专业判断：用1个商业/行业关键词概括本质
- 人话解释：这玩意儿对用户意味着什么？钱从哪来？

**2. 机遇与风险（谁能赚？谁会死？）**
- 专业判断：红海/蓝海判断 + 壁垒分析
- 人话解释：现在进场是送人头还是捡钱？什么样的人能活下来？

**3. 搞钱路径（具体怎么干？）**
- 专业判断：分阶段策略（冷启动→建立壁垒→规模化）
- 人话解释：今晚就能做的第一件事是什么？别整虚的

### 语言风格（必须遵守）

| 不要这样写 | 要这样写 |
|-----------|---------|
| "生态位分析显示" | "现在进场的人分三种" |
| "差异化壁垒构建" | "你得有点别人抄不走的绝活" |
| "流量洼地窗口期" | "现在知道的人还不多，早进早占坑" |
| "非标服务标准化" | "把模糊的服务变成可复制的套餐" |
| "用户心智占领" | "让客户一想到这事就找你" |

### 结尾要求
**Next Step**：列出24小时内能启动的3个具体动作，格式：
- 今晚：XXX（具体动作，如"在闲鱼发第一条服务帖"）
- 明早：XXX（具体动作，如"加3个目标客户的微信"）
- 本周：XXX（具体动作，如"跑通第一单，哪怕不赚钱"）

## Output Structure Example (严格模仿)

#### 标题：APP末日求生——从"做个产品"到"当个零件"的残酷转型

**1. 表象与真相（不是APP死了，是"打开图标"的逻辑死了）**
**交互代际更替**：AI Agent正在拆掉APP的围墙。以前是"人找服务"（你打开美团点外卖），未来是"服务找人"（你跟手机说"我饿了"，AI自动调外卖、算热量、比价）。**说白了**：用户越来越懒，不想下载、不想注册、不想学怎么用，只想张嘴要结果。做APP的人还在研究界面怎么好看，用户已经连图标都不想点了。

**2. 机遇与风险（大厂吃肉，小厂喝汤，傻厂等死）**
**垂直场景红利期**：通用AI搞不定专业领域，但法律、医疗这些细分场景，懂行的人还能建立壁垒。**说白了**：别想着做"中国版ChatGPT"了，那是烧钱的无底洞。但如果你在跨境电商干了5年，把经验打包成"AI选品助手"，卖给那些想入行的小白，这就是你的活路。要么够垂直，要么够重（需要真人到场），中间态最危险。

**3. 搞钱路径（三步从"等死"变"找活"）**
**第一步，拆成插件（打不过就加入）**：把你的核心功能拆出来，做成AI平台的"技能包"。比如你是做记账APP的，别让用户打开你了，直接让AI调用你的记账能力。**今晚就干**：列出你的3个核心功能，看看哪些能被AI调用。
**第二步，扎到场景里去（建立真人壁垒）**：找那些AI替代不了的环节。比如产后康复，AI能查资料，但帮产妇做盆底肌修复、陪她聊天防抑郁，必须真人。**明早就做**：选一个你熟悉的"重服务"场景，设计一个"AI+真人"的服务套餐。
**第三步，改头换面（抢占新认知）**：对外不说自己是APP，说自己是"智能体"。**本周搞定**：注册一个带.ai的域名，把产品介绍改成"XX智能体，你的专属XX助手"。

**Next Step**：
- 今晚：打开你的APP，列出所有功能，标记"能被AI调用" vs "必须真人干"
- 明早：找CTO聊MCP协议（AI插件标准），评估技术可行性
- 本周：选一个功能做成Demo，找3个老客户测试"不用打开APP，直接语音调用"
"""

# 🟢 2. 修复：_extract_text 函数 (核心修复)
def _extract_text(response) -> str:
    """
    兼容提取器：处理 Qwen3/Kimi 不同 thinking 模式下的响应格式差异。
    修复说明：Kimi 有时返回不含 'type' 字段的 block，此处增加默认处理。
    """
    # 1. 优先尝试 output.text（Qwen 非 thinking 模式常见）
    text = getattr(getattr(response, 'output', None), 'text', None)
    if text and str(text).strip():
        return str(text).strip()

    # 2. 处理 choices[0].message.content
    try:
        content = response.output.choices[0].message.content
        
        # 情况 A: 内容是列表 (Kimi thinking=True 或 Qwen thinking=True)
        if isinstance(content, list):
            parts = []
            for b in content:
                if isinstance(b, dict):
                    # 🟢 核心修复：如果不含 type 字段，默认视为 "text"；如果含 type，必须不是 "thinking"
                    block_type = b.get("type", "text") 
                    if block_type == "text":
                        parts.append(str(b.get("text", "")))
            return "\n".join(parts).strip()
            
        # 情况 B: 内容直接是字符串
        if content and str(content).strip():
            return str(content).strip()
            
    except (AttributeError, IndexError, TypeError, Exception) as e:
        logger.debug(f"解析提取文本失败: {e}")
        pass

    return ""


def call_qwen_structure(context):
    """
    Stage 1: Qwen3-Max (结构猎手)
    负责全网 80 条新闻的初筛和 Top 15 撰写 + Deep Dive 草稿。
    - enable_thinking 不传（让模型自动决定），避免部分 SDK 版本 output.text 为空的 bug。
    - 指数退避重试：最多 3 次，间隔 2/4/8 秒。
    """
    logger.info("🧠 [Stage 1] Qwen3-Max 正在构建骨架...")
    dashscope.api_key = DASHSCOPE_API_KEY

    for attempt in range(MAX_RETRIES):
        try:
            response = Generation.call(
                model='qwen3-max',
                messages=[
                    {'role': 'system', 'content': QWEN_PROMPT},
                    {'role': 'user', 'content': f"今日情报素材池：\n{context}"}
                ]
                # ⚠️ 不传 enable_thinking：避免 thinking=False 时 output.text 为空的 SDK bug
            )
            if response.status_code == HTTPStatus.OK:
                text = _extract_text(response)
                if text:
                    logger.info(f"✅ [Stage 1] Qwen3-Max 输出完成 ({len(text)} 字)")
                    return text
                else:
                    logger.warning(f"[Stage 1] Qwen 返回空内容 (attempt {attempt+1}/{MAX_RETRIES})，原始响应: {response.output}")
            else:
                logger.warning(f"[Stage 1] Qwen 错误 (attempt {attempt+1}/{MAX_RETRIES}): {response.message}")
        except Exception as e:
            logger.warning(f"[Stage 1] Qwen 异常 (attempt {attempt+1}/{MAX_RETRIES}): {e}")

        if attempt < MAX_RETRIES - 1:
            wait = RETRY_BASE_DELAY ** (attempt + 1)  # 2s → 4s → 8s
            logger.info(f"   ⏳ {wait}s 后重试...")
            time.sleep(wait)

    logger.error("❌ [Stage 1] Qwen3-Max 重试耗尽，返回 None")
    return None

def call_kimi_refine(draft_content):
    """
    Stage 2: Kimi-K2.5 (深度智囊)
    接收 Qwen 的草稿，输出辛辣的"术语+大白话"深度分析。
    - 使用 MultiModalConversation 接口（Kimi-K2.5 的正确调用方式）。
    - enable_thinking=True：强制开启内部推演，先思考再输出，质量更高。
    - 地域限制：kimi-k2.5 仅支持中国大陆（北京）地域的 API Key。
    - 降级策略：kimi-k2.5 失败 → qwen-plus 兜底。
    - 指数退避重试：最多 3 次，间隔 2/4/8 秒。
    """
    logger.info("💎 [Stage 2] Kimi-K2.5 正在深度锐化（思考模式开启）...")
    dashscope.api_key = DASHSCOPE_API_KEY

    messages = [
        {"role": "system", "content": KIMI_PROMPT},
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": f"请参考范文风格，深度润色以下草稿：\n\n{draft_content}"
                }
            ]
        }
    ]

    # ── 主力：kimi-k2.5 ─────────────────────────────────
    for attempt in range(MAX_RETRIES):
        try:
            response = MultiModalConversation.call(
                model='kimi-k2.5',
                messages=messages,
                extra_body={"enable_thinking": True}
            )
            if response.status_code == HTTPStatus.OK:
                result_text = _extract_text(response)
                if result_text:
                    logger.info(f"✅ [Stage 2] Kimi-K2.5 输出完成 ({len(result_text)} 字)")
                    return f"### Part 2: 深度搞钱逻辑 (Deep Dive)\n\n{result_text}"
                else:
                    logger.warning(f"[Stage 2] Kimi-K2.5 返回空内容 (attempt {attempt+1}/{MAX_RETRIES})")
            else:
                logger.warning(f"[Stage 2] Kimi-K2.5 错误 (attempt {attempt+1}/{MAX_RETRIES}): {response.message}")
        except Exception as e:
            logger.warning(f"[Stage 2] Kimi-K2.5 异常 (attempt {attempt+1}/{MAX_RETRIES}): {e}")

        if attempt < MAX_RETRIES - 1:
            wait = RETRY_BASE_DELAY ** (attempt + 1)
            logger.info(f"   ⏳ {wait}s 后重试...")
            time.sleep(wait)

    # ── 降级：qwen-plus ──────────────────────────────────
    logger.warning("⚠️ [Stage 2] Kimi-K2.5 重试耗尽，降级使用 qwen-plus...")
    try:
        fallback_resp = Generation.call(
            model='qwen-plus',
            messages=[
                {"role": "system", "content": KIMI_PROMPT},
                {"role": "user", "content": f"请参考范文风格，深度润色以下草稿：\n\n{draft_content}"}
            ]
        )
        if fallback_resp.status_code == HTTPStatus.OK:
            text = _extract_text(fallback_resp)
            if text:
                logger.info("✅ [Stage 2] qwen-plus 降级成功")
                return f"### Part 2: 深度搞钱逻辑 (Deep Dive · qwen-plus 降级版)\n\n{text}"
        logger.error(f"[Stage 2] qwen-plus 降级失败: {fallback_resp.message}")
    except Exception as e:
        logger.error(f"[Stage 2] qwen-plus 降级异常: {e}")

    logger.error("❌ [Stage 2] 所有模型失败，返回原始草稿")
    return f"### Part 2 (AI润色失败，原始草稿)\n\n{draft_content}"

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
