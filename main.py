#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
私人晨间情报官 - 深度猎手版
功能：
1. 每日抓取全球核心商业/科技/政策新闻
2. 扮演"商业情报猎手"进行深度拆解和搞钱路径分析
3. 生成播客音频 (Edge-TTS)
4. Bark 推送核心摘要 + 全文跳转
5. 自动维护 RSS Feed 和清理旧文件
"""

import os
import sys
import feedparser
import requests
from datetime import datetime, timedelta
import json
import asyncio
import time
import re
import glob
from typing import List, Dict

try:
    import edge_tts
except ImportError:
    print("正在安装 edge-tts...")
    os.system("pip install edge-tts")
    import edge_tts

# ========== 配置区 ==========
DASHSCOPE_API_KEY = os.getenv('DASHSCOPE_API_KEY')
BARK_KEY = os.getenv('BARK_KEY')
# 获取 GitHub 仓库名，用于生成跳转链接
GITHUB_REPO = os.getenv('GITHUB_REPOSITORY', 'your-name/your-repo') 

# 🔥 核心 RSS 新闻源 (根据你的需求深度整理)
RSS_SOURCES = [
    # --- 第一梯队：全球与金融核心 (华尔街见闻 + 财联社) ---
    "https://rsshub.app/wallstreetcn/live/global/2",      # 华尔街见闻-重要快讯
    "https://rsshub.app/wallstreetcn/hot/day",            # 华尔街见闻-每日最热
    "https://rsshub.app/cls/telegraph/red",               # 财联社-加红电报
    
    # --- 第二梯队：时事与深度财经 (澎湃 + 新华社 + 第一财经) ---
    "https://rsshub.app/news/xhsxw",                      # 新华社新闻 (权威定调)
    "https://rsshub.app/thepaper/channel/25951",          # 澎湃-财经
    "https://rsshub.app/thepaper/channel/25950",          # 澎湃-时事
    "https://rsshub.app/yicai/latest",                    # 第一财经-最新
    "https://rsshub.app/yicai/headline",                  # 第一财经-头条
    
    # --- 第三梯队：深度商业与科技 (虎嗅 + 36Kr + 少数派 + PM) ---
    "https://rsshub.app/huxiu/channel/103",               # 虎嗅-商业消费 (深度评论)
    "https://rsshub.app/36kr/newsflashes",                # 36Kr快讯
    "https://rsshub.app/sspai/index",                     # 少数派 (科技/效率/生活)
    "https://rsshub.app/woshipm/popular/daily",           # 人人都是产品经理-日榜
    
    # --- 第四梯队：研报与深度 (南方周末 + 研报) ---
    "https://rsshub.app/infzm/2",                         # 南方周末
    "https://rsshub.app/eastmoney/report/strategyreport", # 东方财富-行业研报
]

# 输出目录配置
OUTPUT_DIR = 'output'
DATE_STR = datetime.now().strftime('%Y%m%d')
AUDIO_FILE = f'{OUTPUT_DIR}/briefing_{DATE_STR}.mp3' 
TEXT_FILE = f'{OUTPUT_DIR}/briefing_{DATE_STR}.txt'
RSS_FILE = 'feed.xml'

# Edge-TTS 语音配置
VOICE_NAME = 'zh-CN-YunxiNeural'

# ========== 工具函数 ==========

def clean_text_for_tts(text: str) -> str:
    """清理 Markdown 格式符号，确保 TTS 朗读流畅"""
    text = re.sub(r'#+\s?', '', text)         # 去掉标题 #
    text = re.sub(r'\*\*|__|\*', '', text)    # 去掉加粗 **
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text) # 去掉链接保留文字
    text = re.sub(r'>\s?', '', text)          # 去掉引用 >
    text = re.sub(r'[-*]{3,}', '', text)      # 去掉分割线 ---
    text = re.sub(r'`{3}', '', text)          # 去掉代码块
    return text.strip()

def cleanup_old_files(days_to_keep: int = 3):
    """删除 output 目录下超过指定天数的文件"""
    print(f"🧹 正在清理 {days_to_keep} 天前的旧文件...")
    now = time.time()
    cutoff = now - (days_to_keep * 86400)
    if not os.path.exists(OUTPUT_DIR): return
    
    files = glob.glob(os.path.join(OUTPUT_DIR, '*'))
    for f in files:
        if os.path.basename(f).startswith('.'): continue
        if os.path.getmtime(f) < cutoff:
            try:
                os.remove(f)
                print(f"  Deleted: {f}")
            except Exception: pass

def send_bark_notification(title: str, content: str, click_url: str = None):
    """通过 Bark 发送推送通知，支持点击跳转"""
    if not BARK_KEY:
        print("⚠️  未配置 BARK_KEY，跳过推送通知")
        return
    
    try:
        # 截取摘要 (保留前 100 字)
        summary = content.replace('\n', ' ')[:100] + "..."
        url = f"https://api.day.app/{BARK_KEY}/{title}/{summary}"
        params = {
            'group': 'MorningBrief',
            'icon': 'https://cdn-icons-png.flaticon.com/512/2965/2965363.png'
        }
        if click_url:
            params['url'] = click_url
            
        requests.get(url, params=params, timeout=10)
        print(f"✅ 已发送 Bark 通知: {title}")
    except Exception as e:
        print(f"⚠️  Bark 推送失败: {e}")

def fetch_rss_articles() -> List[Dict]:
    """从 RSS 源抓取新闻"""
    articles = []
    now = datetime.now()
    cutoff_time = now - timedelta(hours=24) # 只取24小时内
    
    print(f"📰 开始从 {len(RSS_SOURCES)} 个源抓取新闻...")
    
    for source_url in RSS_SOURCES:
        try:
            # 设置 User-Agent 防止反爬
            feed = feedparser.parse(
                source_url,
                agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            )
            source_name = feed.feed.get('title', '未知来源')
            
            # 每个源最多取 10 条，避免单一源刷屏
            for entry in feed.entries[:10]:
                pub_time = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    pub_time = datetime(*entry.published_parsed[:6])
                
                # 如果有时间戳且太旧，跳过
                if pub_time and pub_time < cutoff_time:
                    continue
                
                articles.append({
                    'title': entry.title,
                    'summary': entry.get('summary', entry.get('description', ''))[:300],
                    'link': entry.link,
                    'source': source_name
                })
        except Exception as e:
            print(f"  ✗ 抓取失败 {source_url}: {e}")
            
    print(f"📊 共获取 {len(articles)} 条新闻\n")
    return articles[:50] # 总共保留50条供 AI 筛选

# ========== AI 生成逻辑 (核心修改区) ==========

def _call_dashscope(model: str, prompt: str, max_tokens: int, temperature: float, extra_params: dict = None) -> str:
    """底层 API 调用封装"""
    if not DASHSCOPE_API_KEY: raise ValueError("未配置 DASHSCOPE_API_KEY")
    
    url = 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions'
    headers = {'Authorization': f'Bearer {DASHSCOPE_API_KEY}', 'Content-Type': 'application/json'}
    
    # 🔥 重塑人设：商业情报猎手
    system_prompt = """
    你是一位【商业情报猎手】，你的受众是渴望财富增长和认知升级的年轻人。
    你的风格要求：
    1. 语言风格：犀利、透彻、不说官话，像老朋友聊天一样自然，但逻辑极强。
    2. 分析深度：不只看新闻表面，要挖掘背后的利益链条和底层逻辑。
    3. 实用主义：必须提供具体的“搞钱路径”或“避坑指南”，让读者有获得感。
    4. 格式要求：虽然你需要输出结构化内容，但为了语音朗读通顺，请不要使用复杂的Markdown表格，使用清晰的段落。
    """
    
    payload = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': prompt}
        ],
        'max_tokens': max_tokens,
        'temperature': temperature
    }
    if extra_params: payload.update(extra_params)
    
    timeout = 300 if extra_params and extra_params.get('enable_thinking') else 60
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        return response.json()['choices'][0]['message']['content']
    except Exception as e:
        print(f"❌ API 调用失败（模型: {model}）: {e}")
        raise

def call_qwen_flash(prompt: str, max_tokens: int = 1000) -> str:
    print(f"  ⚡ 调用 qwen-flash (快速筛选)...")
    return _call_dashscope(model='qwen-flash', prompt=prompt, max_tokens=max_tokens, temperature=0.7)

def call_qwen_max_thinking(prompt: str, max_tokens: int = 4000) -> str:
    thinking_budget = min(max_tokens * 2, 16000)
    print(f"  🧠 调用qwen-max (深度思考)...")
    return _call_dashscope(
        model='qwen3-max-2026-01-23', # 使用最新模型
        prompt=prompt,
        max_tokens=max_tokens + thinking_budget,
        temperature=0.6,
        extra_params={'enable_thinking': True, 'thinking_budget': thinking_budget}
    )

def generate_section_a_overview(articles: List[Dict]) -> str:
    print("✍️  正在生成【板块A：全景扫描】...")
    news_text = "".join([f"{i+1}. {a['title']} (来源: {a['source']})\n   {a['summary'][:100]}\n\n" for i, a in enumerate(articles[:35])])
    
    date_str = datetime.now().strftime('%Y年%m月%d日')
    
    prompt = f"""
    你是晨间猎手。今天是{date_str}。
    请根据以下新闻素材，撰写【第一部分：全景扫描】。
    
    **写作要求：**
    1. 开场白：复刻这个风格——"哈喽，早上好！欢迎收听晨间猎手内参...先给自己倒杯咖啡...准备好了吗？我们开始今天的猎杀时间。"
    2. 内容选取：精选 **12-15条** 最具影响力的全球商业、科技、民生新闻（DeepSeek、特斯拉、苹果、政策变动等）。
    3. 每条新闻格式：
       - 小标题（简练有力）
       - 正文：先说发生了什么（Fact），一句话点评对行业或普通人的直接影响（Impact）。
       - 每条字数控制在100-150字之间。
    4. 结尾：用一句话过渡到深度分析环节。

    新闻素材：
    {news_text}
    """
    return call_qwen_max_thinking(prompt, max_tokens=3500)

def generate_section_b_deep_dive(articles: List[Dict]) -> str:
    print("✍️  正在生成【板块B：猎手深度分析】...")
    titles = chr(10).join([f"{i+1}. {a['title']}" for i, a in enumerate(articles[:35])])
    
    # 1. 筛选话题
    selection_prompt = f"""
    作为商业猎手，请从以下新闻中选出 **4个** 最具争议性、最能影响普通人钱包的“深水区”话题。
    话题标准：要有冲突感（如AI冲击就业、巨头博弈、政策转向、楼市股市变动）。
    仅输出4个话题标题。
    新闻列表：
    {titles}
    """
    selected_topics = call_qwen_flash(selection_prompt, max_tokens=500)
    
    # 2. 深度写作
    analysis_prompt = f"""
    请对以下4个话题进行【猎手级深度拆解】，每个话题写800-1000字，总字数3000字以上。
    
    话题列表：
    {selected_topics}
    
    **核心写作结构（每个话题必须包含这三个部分）：**
    
    ### 专题X：[具有冲击力的标题]
    
    **1. 现状层 (The Facts)**
    - 快速交代新闻背景，发生了什么？数据是什么？市场反应如何？（客观、冷静）
    
    **2. 猎手拆解 (Hunter's Logic)**
    - **这是核心！** 不要人云亦云。
    - 拆解背后的利益博弈：谁受益？谁受损？
    - 揭示底层逻辑：比如“这表面是降息，实则是资产价格重估”。
    - 使用犀利的语言，如“这背后的逻辑很简单”、“华尔街在恐慌什么”。
    
    **3. 搞钱路径 & 避坑指南 (Actionable Advice)**
    - **必须针对普通人/投资者/从业者。**
    - 给出具体的建议：
      - "如果你持有..."
      - "对于...行业的从业者，这意味着..."
      - "未来的机会在于..."
      - "千万不要..."
    
    **整体语气要求：**
    - 像一个在该行业摸爬滚打多年的老猎手在给徒弟传授经验。
    - 结尾要有一个宏观的升华或警示。
    """
    return call_qwen_max_thinking(analysis_prompt, max_tokens=6000)

def assemble_full_script(section_a: str, section_b: str) -> str:
    return f"""
# 晨间猎手内参 · 深度咖啡版
    
{section_a}

---

## 【第二部分：猎手深度分析】

{section_b}
    """

async def generate_audio(text: str, output_path: str):
    print(f"🎙️  正在生成音频...")
    # 清洗 Markdown 符号，防止 TTS 读出 "星号星号"
    clean_text = clean_text_for_tts(text)
    communicate = edge_tts.Communicate(clean_text, voice=VOICE_NAME, rate='+5%')
    await communicate.save(output_path)

def generate_rss_feed(audio_url: str):
    print("📡 正在生成 RSS Feed...")
    today = datetime.now().strftime('%Y-%m-%d')
    rss_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>私人晨间情报</title>
    <item>
      <title>{today} 晨间情报</title>
      <enclosure url="{audio_url}" type="audio/mpeg" length="100000"/>
      <guid>{today}</guid>
    </item>
  </channel>
</rss>"""
    with open(RSS_FILE, 'w', encoding='utf-8') as f:
        f.write(rss_content)

def main():
    print("🚀 启动任务...")
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        
        # 1. 抓取
        articles = fetch_rss_articles()
        if not articles:
             print("⚠️ 警告：未抓取到新闻。使用测试数据继续...")
             articles = [{'title': '测试新闻', 'summary': '无新闻数据', 'link': 'http://test', 'source': 'Test'}]

        if articles:
            # 2. 生成
            section_a = generate_section_a_overview(articles)
            section_b = generate_section_b_deep_dive(articles)
            full_script = assemble_full_script(section_a, section_b)
            
            # 3. 保存文本
            with open(TEXT_FILE, 'w', encoding='utf-8') as f:
                f.write(full_script)
            
            # 4. 生成音频
            asyncio.run(generate_audio(full_script, AUDIO_FILE))
            
            # 5. 后续处理 (RSS, Bark, 清理)
            audio_filename = os.path.basename(AUDIO_FILE)
            text_filename = os.path.basename(TEXT_FILE)
            
            # 生成链接
            rss_audio_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{OUTPUT_DIR}/{audio_filename}"
            full_text_url = f"https://github.com/{GITHUB_REPO}/blob/main/{OUTPUT_DIR}/{text_filename}"
            
            generate_rss_feed(rss_audio_url)
            
            # Bark 推送 (带跳转)
            # 提取全景扫描前100字做摘要
            summary_candidate = clean_text_for_tts(section_a)[:100]
            send_bark_notification(
                f"{datetime.now().strftime('%m月%d日')}晨间内参", 
                summary_candidate,
                click_url=full_text_url
            )
            
            cleanup_old_files(days_to_keep=3)
            print("✅ 任务全部完成")
        else:
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ 运行失败: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
