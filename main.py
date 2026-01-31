#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
私人深度晨间情报官 - 主程序
每日自动生成40分钟深度商业情报播客
"""

import os
import sys
import feedparser
import requests
from datetime import datetime, timedelta
import json
import asyncio
import time
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

# RSS 新闻源 (已替换为更稳定的镜像源)
RSS_SOURCES = [
    "https://rsshub.rssforever.com/infzm/2",              # 南方周末
    "https://rsshub.rssforever.com/woshipm/popular/daily", # 人人都是产品经理
    "https://www.huxiu.com/rss/0.xml",                    # 虎嗅 (官方源)
    "https://rsshub.rssforever.com/wallstreetcn/live/global/2", # 华尔街见闻
    "https://rsshub.rssforever.com/cls/telegraph/red",          # 财联社
    "https://rsshub.rssforever.com/wallstreetcn/hot/day",       # 华尔街热文
    "https://rsshub.rssforever.com/thepaper/channel/25950",     # 澎湃时事
    "https://36kr.com/feed",                                    # 36Kr (官方源)
    "https://rsshub.rssforever.com/thepaper/channel/25951",     # 澎湃财经
    "https://rsshub.rssforever.com/xueqiu/hots",                # 雪球热帖
]

# 输出目录配置
OUTPUT_DIR = 'output'
AUDIO_FILE = f'{OUTPUT_DIR}/briefing.mp3'
TEXT_FILE = f'{OUTPUT_DIR}/briefing.txt'
RSS_FILE = 'feed.xml'

# Edge-TTS 语音配置
# 建议保持使用 Edge-TTS，因为它免费且支持长文本（8000字），适合播客场景
VOICE_NAME = 'zh-CN-YunxiNeural'

# ========== 工具函数 ==========

def send_bark_notification(title: str, content: str):
    """通过 Bark 发送推送通知到 iPhone"""
    if not BARK_KEY:
        print("⚠️  未配置 BARK_KEY，跳过推送通知")
        return
    
    try:
        url = f"https://api.day.app/{BARK_KEY}/{title}/{content}"
        requests.get(url, timeout=5)
        print(f"✅ 已发送 Bark 通知: {title}")
    except Exception as e:
        print(f"⚠️  Bark 推送失败: {e}")


def fetch_rss_articles() -> List[Dict]:
    """
    从多个 RSS 源抓取最新24小时的新闻
    """
    articles = []
    now = datetime.now()
    cutoff_time = now - timedelta(hours=24)
    
    print(f"📰 开始从 {len(RSS_SOURCES)} 个源抓取新闻...")
    
    for source_url in RSS_SOURCES:
        try:
            # 伪装成浏览器 User-Agent，防止被 RSSHub 拦截
            feed = feedparser.parse(
                source_url,
                agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            )
            source_name = feed.feed.get('title', source_url)
            
            for entry in feed.entries[:15]:
                pub_time = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    pub_time = datetime(*entry.published_parsed[:6])
                
                if pub_time and pub_time < cutoff_time:
                    continue
                
                articles.append({
                    'title': entry.title,
                    'summary': entry.get('summary', entry.get('description', ''))[:300],
                    'link': entry.link,
                    'source': source_name
                })
            
            print(f"  ✓ {source_name}: 获取 {len([a for a in articles if a['source'] == source_name])} 条")
            time.sleep(1)
            
        except Exception as e:
            print(f"  ✗ 抓取失败 {source_url}: {e}")
    
    print(f"📊 共获取 {len(articles)} 条新闻\n")
    return articles[:40]


def _call_dashscope(model: str, prompt: str, max_tokens: int, temperature: float, extra_params: dict = None) -> str:
    """底层 DashScope API 调用封装"""
    if not DASHSCOPE_API_KEY:
        raise ValueError("未配置 DASHSCOPE_API_KEY")
    
    url = 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions'
    headers = {
        'Authorization': f'Bearer {DASHSCOPE_API_KEY}',
        'Content-Type': 'application/json'
    }
    
    payload = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': '你是一位资深财经编辑，擅长将商业新闻转化为深度投研分析。'},
            {'role': 'user', 'content': prompt}
        ],
        'max_tokens': max_tokens,
        'temperature': temperature
    }
    
    if extra_params:
        payload.update(extra_params)
    
    timeout = 300 if extra_params and extra_params.get('enable_thinking') else 60
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        result = response.json()
        choice = result['choices'][0]['message']
        return choice['content']
    except Exception as e:
        print(f"❌ API 调用失败（模型: {model}）: {e}")
        raise


def call_qwen_flash(prompt: str, max_tokens: int = 1000) -> str:
    # 使用 qwen-flash (极速版) 进行海量新闻的快速筛选
    print(f"  ⚡ 调用 qwen-flash (高性价比筛选)...")
    return _call_dashscope(
        model='qwen-flash',  # <--- 已修改：使用最便宜的 Flash 模型
        prompt=prompt,
        max_tokens=max_tokens,
        temperature=0.7
    )


def call_qwen_max_thinking(prompt: str, max_tokens: int = 4000) -> str:
    # 使用指定的 qwen3-max-2026-01-23 版本进行深度思考
    thinking_budget = min(max_tokens * 2, 16000)
    print(f"  🧠 调用 qwen3-max-2026-01-23 (深度思考)...")
    return _call_dashscope(
        model='qwen3-max-2026-01-23',  # <--- 已修改：指定快照版本
        prompt=prompt,
        max_tokens=max_tokens + thinking_budget,
        temperature=0.6,
        extra_params={'enable_thinking': True, 'thinking_budget': thinking_budget}
    )


def generate_section_a_overview(articles: List[Dict]) -> str:
    print("✍️  正在生成【板块A：全景扫描】...")
    news_text = ""
    for i, article in enumerate(articles[:25], 1):
        news_text += f"{i}. {article['title']}\n   {article['summary'][:150]}\n\n"
    
    prompt = f"""
    请基于以下新闻素材，撰写一份**2000字**的"全球商业科技 + 中国民生动态"概览。
    要求：中国内容占50%，重点关注社保、房地产、消费、科技大厂。
    新闻素材：
    {news_text}
    """
    return call_qwen_max_thinking(prompt, max_tokens=3000)


def generate_section_b_deep_dive(articles: List[Dict]) -> str:
    print("✍️  正在生成【板块B：猎手深度分析】...")
    titles = chr(10).join([f"{i+1}. {a['title']}" for i, a in enumerate(articles[:30])])
    
    selection_prompt = f"从以下新闻中选出5-6个最具商业价值的话题：\n{titles}"
    selected_topics = call_qwen_flash(selection_prompt, max_tokens=500)
    
    analysis_prompt = f"""
    针对以下话题进行深度分析（共5000字）：
    {selected_topics}
    分析框架：现象速写 -> 本质拆解 -> 搞钱路径 -> 风险预警
    """
    return call_qwen_max_thinking(analysis_prompt, max_tokens=6000)


def assemble_full_script(section_a: str, section_b: str) -> str:
    date_str = datetime.now().strftime('%Y年%m月%d日')
    return f"""
    欢迎收听私人晨间情报，今天是{date_str}。
    {section_a}
    接下来进入深度分析板块。
    {section_b}
    感谢收听。
    """


async def generate_audio(text: str, output_path: str):
    print(f"🎙️  正在生成音频...")
    communicate = edge_tts.Communicate(text, voice=VOICE_NAME, rate='+5%')
    await communicate.save(output_path)


def generate_rss_feed(script: str, audio_url: str):
    print("📡 正在生成 RSS Feed...")
    rss_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>私人晨间情报</title>
    <item>
      <title>{datetime.now().strftime('%Y-%m-%d')} 晨间情报</title>
      <enclosure url="{audio_url}" type="audio/mpeg" length="100000"/>
      <guid>{datetime.now().strftime('%Y-%m-%d')}</guid>
    </item>
  </channel>
</rss>"""
    with open(RSS_FILE, 'w', encoding='utf-8') as f:
        f.write(rss_content)


def main():
    print("🚀 启动...")
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        articles = fetch_rss_articles()
        
        if not articles:
             print("⚠️ 警告：未抓取到新闻。使用测试数据继续流程...")
             articles = [{'title': '测试新闻', 'summary': '这是一个测试', 'link': 'http://test', 'source': 'Test'}]

        if articles:
            section_a = generate_section_a_overview(articles)
            section_b = generate_section_b_deep_dive(articles)
            full_script = assemble_full_script(section_a, section_b)
            
            with open(TEXT_FILE, 'w', encoding='utf-8') as f:
                f.write(full_script)
                
            asyncio.run(generate_audio(full_script, AUDIO_FILE))
            
            repo = os.getenv('GITHUB_REPOSITORY', 'your-repo')
            generate_rss_feed(full_script, f"https://raw.githubusercontent.com/{repo}/main/{AUDIO_FILE}")
            
            print("✅ 全部完成")
        else:
            print("❌ 任务终止")
            sys.exit(1)
        
    except Exception as e:
        print(f"❌ 运行失败: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
