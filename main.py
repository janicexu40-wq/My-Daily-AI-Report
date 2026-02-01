#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
私人深度晨间情报官 - 主程序
功能：
1. 每日自动生成深度商业情报播客
2. 自动清理 Markdown 格式以优化 TTS 朗读
3. Bark 推送核心摘要 + 点击查看全文 (GitHub链接)
4. 自动清理 3 天前的旧文件
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
# 获取 GitHub 仓库名 (格式: username/repo)，如果本地测试没有环境变量，请手动填 'yourname/repo'
GITHUB_REPO = os.getenv('GITHUB_REPOSITORY', 'your-github-username/your-repo-name') 

# RSS 新闻源
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
DATE_STR = datetime.now().strftime('%Y%m%d')
AUDIO_FILE = f'{OUTPUT_DIR}/briefing_{DATE_STR}.mp3' 
TEXT_FILE = f'{OUTPUT_DIR}/briefing_{DATE_STR}.txt'
RSS_FILE = 'feed.xml'

# Edge-TTS 语音配置
VOICE_NAME = 'zh-CN-YunxiNeural'

# ========== 工具函数 ==========

def clean_text_for_tts(text: str) -> str:
    """清理 Markdown 格式符号，确保 TTS 朗读流畅"""
    text = re.sub(r'#+\s?', '', text)
    text = re.sub(r'\*\*|__|\*', '', text)
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    text = re.sub(r'>\s?', '', text)
    text = re.sub(r'[-*]{3,}', '', text)
    text = re.sub(r'^\s*[-+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'`{3}', '', text)
    return text.strip()

def cleanup_old_files(days_to_keep: int = 3):
    """删除 output 目录下超过指定天数的文件"""
    print(f"🧹 正在清理 {days_to_keep} 天前的旧文件...")
    now = time.time()
    cutoff = now - (days_to_keep * 86400)
    if not os.path.exists(OUTPUT_DIR): return
    
    files = glob.glob(os.path.join(OUTPUT_DIR, '*'))
    count = 0
    for f in files:
        if os.path.basename(f).startswith('.'): continue
        if os.path.getmtime(f) < cutoff:
            try:
                os.remove(f)
                count += 1
            except Exception: pass
    print(f"🧹 清理完成，共删除 {count} 个文件。\n")

def send_bark_notification(title: str, content: str, click_url: str = None):
    """通过 Bark 发送推送通知，支持点击跳转"""
    if not BARK_KEY:
        print("⚠️  未配置 BARK_KEY，跳过推送通知")
        return
    
    try:
        # 1. 截取摘要 (保留前 100 字，移除换行以防 URL 截断)
        summary = content.replace('\n', ' ')[:100] + "..."
        
        # 2. 构建基础 URL
        # 注意：Bark 的 URL 结构是 /key/title/body
        url = f"https://api.day.app/{BARK_KEY}/{title}/{summary}"
        
        params = {
            'group': 'MorningBrief',
            'icon': 'https://cdn-icons-png.flaticon.com/512/2965/2965363.png'
        }
        
        # 3. 关键：添加点击跳转链接
        if click_url:
            params['url'] = click_url
            
        requests.get(url, params=params, timeout=10)
        print(f"✅ 已发送 Bark 通知 (带跳转链接): {title}")
    except Exception as e:
        print(f"⚠️  Bark 推送失败: {e}")

def fetch_rss_articles() -> List[Dict]:
    """从多个 RSS 源抓取新闻"""
    articles = []
    now = datetime.now()
    cutoff_time = now - timedelta(hours=24)
    print(f"📰 开始从 {len(RSS_SOURCES)} 个源抓取新闻...")
    
    for source_url in RSS_SOURCES:
        try:
            feed = feedparser.parse(source_url, agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
            source_name = feed.feed.get('title', source_url)
            for entry in feed.entries[:15]:
                pub_time = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    pub_time = datetime(*entry.published_parsed[:6])
                if pub_time and pub_time < cutoff_time: continue
                
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
    """底层 API 调用"""
    if not DASHSCOPE_API_KEY: raise ValueError("未配置 DASHSCOPE_API_KEY")
    
    url = 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions'
    headers = {'Authorization': f'Bearer {DASHSCOPE_API_KEY}', 'Content-Type': 'application/json'}
    system_prompt = '你是一位资深财经编辑。输出纯文本，不使用任何Markdown格式（不用#、**、-、>等符号），语言流畅自然，适合播客朗读。'
    
    payload = {
        'model': model,
        'messages': [{'role': 'system', 'content': system_prompt}, {'role': 'user', 'content': prompt}],
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
    print(f"  ⚡ 调用 qwen-flash...")
    return _call_dashscope(model='qwen-flash', prompt=prompt, max_tokens=max_tokens, temperature=0.7)

def call_qwen_max_thinking(prompt: str, max_tokens: int = 4000) -> str:
    thinking_budget = min(max_tokens * 2, 16000)
    print(f"  🧠 调用qwen-max (深度思考)...")
    return _call_dashscope(
        model='qwen-max',
        prompt=prompt,
        max_tokens=max_tokens + thinking_budget,
        temperature=0.6,
        extra_params={'enable_thinking': True, 'thinking_budget': thinking_budget}
    )

def generate_section_a_overview(articles: List[Dict]) -> str:
    print("✍️  正在生成【板块A】...")
    news_text = "".join([f"{i+1}. {a['title']}\n   {a['summary'][:150]}\n\n" for i, a in enumerate(articles[:25])])
    prompt = f"请基于以下新闻素材，撰写一份**2000字**的'全球商业科技 + 中国民生动态'概览。\n【重要】输出纯文本，不要用Markdown。中国内容占50%。\n新闻素材：\n{news_text}"
    return call_qwen_max_thinking(prompt, max_tokens=3000)

def generate_section_b_deep_dive(articles: List[Dict]) -> str:
    print("✍️  正在生成【板块B】...")
    titles = chr(10).join([f"{i+1}. {a['title']}" for i, a in enumerate(articles[:30])])
    selected_topics = call_qwen_flash(f"选出5-6个最具商业价值的话题：\n{titles}", max_tokens=500)
    prompt = f"针对以下话题进行深度分析（共5000字）：\n{selected_topics}\n【重要】输出纯文本，不要用Markdown。分析逻辑：现象速写 -> 本质拆解 -> 搞钱路径 -> 风险预警"
    return call_qwen_max_thinking(prompt, max_tokens=6000)

def assemble_full_script(section_a: str, section_b: str) -> str:
    date_str = datetime.now().strftime('%Y年%m月%d日')
    return f"欢迎收听私人晨间情报，今天是{date_str}。\n{section_a}\n\n接下来进入深度分析板块。\n{section_b}\n\n感谢收听。"

async def generate_audio(text: str, output_path: str):
    print(f"🎙️  正在生成音频...")
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
    print("🚀 启动...")
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        articles = fetch_rss_articles()
        if not articles:
             print("⚠️ 警告：未抓取到新闻。使用测试数据...")
             articles = [{'title': '测试新闻', 'summary': '这是一个测试', 'link': 'http://test', 'source': 'Test'}]

        if articles:
            section_a = generate_section_a_overview(articles)
            section_b = generate_section_b_deep_dive(articles)
            full_script = assemble_full_script(section_a, section_b)
            
            with open(TEXT_FILE, 'w', encoding='utf-8') as f:
                f.write(full_script)
            
            asyncio.run(generate_audio(full_script, AUDIO_FILE))
            
            # 5. 更新 RSS & Bark
            audio_filename = os.path.basename(AUDIO_FILE)
            text_filename = os.path.basename(TEXT_FILE)
            
            # 生成 RSS 链接 (Raw 链接)
            rss_audio_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{OUTPUT_DIR}/{audio_filename}"
            generate_rss_feed(rss_audio_url)
            
            # 生成 全文阅读链接 (Blob 链接，适合阅读)
            full_text_url = f"https://github.com/{GITHUB_REPO}/blob/main/{OUTPUT_DIR}/{text_filename}"
            
            # 发送 Bark 通知 (点击跳转 GitHub)
            summary_candidate = clean_text_for_tts(section_a)[:100]
            send_bark_notification(
                f"{datetime.now().strftime('%m月%d日')}晨间情报", 
                summary_candidate,
                click_url=full_text_url
            )
            
            cleanup_old_files(days_to_keep=3)
            print("✅ 全部完成")
        else:
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ 运行失败: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
