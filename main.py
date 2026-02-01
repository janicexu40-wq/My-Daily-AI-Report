#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
私人晨间情报官 - GitHub Actions 生产环境专用版
功能：
1. 抓取全网核心商业/科技新闻 (混合源抗反爬策略)
2. "商业猎手"风格深度拆解 (严格基于事实)
3. 生成 .mp3 音频 + .html 移动端网页
4. Bark 推送网页链接
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
from typing import List, Dict, Tuple

# ========== 自动依赖检查与安装 ==========
try:
    import edge_tts
except ImportError:
    print("📦 正在安装 edge-tts...")
    os.system("pip install edge-tts")
    import edge_tts

try:
    import markdown
except ImportError:
    print("📦 正在安装 markdown...")
    os.system("pip install markdown")
    import markdown

# ========== 全局配置区 ==========
DASHSCOPE_API_KEY = os.getenv('DASHSCOPE_API_KEY')
BARK_KEY = os.getenv('BARK_KEY')
GITHUB_REPO = os.getenv('GITHUB_REPOSITORY', 'yourname/yourrepo') 

# 🔥 终极 RSS 源列表 (混合动力版 - 适配 GitHub US 节点)
# 策略：GitHub Actions 位于美国，访问 rsshub.app 通常顺畅，
# 但部分源站反爬严格，故核心源使用抗封锁能力强的镜像。
RSS_SOURCES = [
    # --- 第一梯队：核心财经 (使用高可用镜像) ---
    "https://rsshub.rssforever.com/wallstreetcn/live/global/2",      # 华尔街见闻-快讯
    "https://rsshub.rssforever.com/wallstreetcn/hot/day",            # 华尔街见闻-热榜
    "https://rsshub.rssforever.com/cls/telegraph/red",               # 财联社-电报
    "https://rsshub.rssforever.com/yicai/headline",                  # 第一财经-头条
    
    # --- 第二梯队：权威官媒 (官方源 + 伪装头) ---
    "https://rsshub.app/news/xhsxw",                      # 新华社
    "https://rsshub.app/thepaper/channel/25951",          # 澎湃-财经
    "https://rsshub.app/thepaper/channel/25950",          # 澎湃-时事
    
    # --- 第三梯队：深度与科技 (混合策略) ---
    "https://rsshub.rssforever.com/36kr/newsflashes",     # 36Kr
    "https://rsshub.rssforever.com/sspai/index",          # 少数派
    "https://rsshub.rssforever.com/woshipm/popular/daily",# 产品经理
    "https://rsshub.app/huxiu/channel/103",               # 虎嗅
    
    # --- 第四梯队：研报 ---
    "https://rsshub.rssforever.com/eastmoney/report/strategyreport", # 策略研报
]

# 文件路径配置
OUTPUT_DIR = 'output'
DATE_STR = datetime.now().strftime('%Y%m%d')
AUDIO_FILENAME = f'briefing_{DATE_STR}.mp3'
AUDIO_FILE = f'{OUTPUT_DIR}/{AUDIO_FILENAME}'
MD_FILE = f'{OUTPUT_DIR}/briefing_{DATE_STR}.md'
HTML_FILE = f'{OUTPUT_DIR}/briefing_{DATE_STR}.html'
RSS_FILE = 'feed.xml'

VOICE_NAME = 'zh-CN-YunxiNeural'

# ========== 核心功能函数 ==========

def clean_text_for_tts(text: str) -> str:
    """TTS 文本清洗：移除 Markdown 符号，保留可读内容"""
    text = re.sub(r'#+\s?', '', text)              # 去标题
    text = re.sub(r'\*\*|__|\*', '', text)         # 去加粗
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text) # 去链接保留文本
    text = re.sub(r'>\s?', '', text)               # 去引用
    text = re.sub(r'[-*]{3,}', '', text)           # 去分割线
    text = re.sub(r'📊.*', '', text, flags=re.S)   # 去掉末尾的统计模块
    return text.strip()

def cleanup_old_files(days_to_keep: int = 3):
    """清理历史文件，防止仓库膨胀"""
    print(f"🧹 清理 {days_to_keep} 天前的旧文件...")
    now = time.time()
    cutoff = now - (days_to_keep * 86400)
    if not os.path.exists(OUTPUT_DIR): return
    files = glob.glob(os.path.join(OUTPUT_DIR, '*'))
    for f in files:
        if os.path.basename(f).startswith('.'): continue
        if os.path.getmtime(f) < cutoff:
            try: os.remove(f)
            except: pass

def send_bark_notification(title: str, content: str, click_url: str = None):
    """发送 Bark 手机推送"""
    if not BARK_KEY: return
    try:
        # 摘要截取，去掉换行
        summary = content.replace('\n', ' ')[:100] + "..."
        url = f"https://api.day.app/{BARK_KEY}/{title}/{summary}"
        params = {
            'group': 'MorningBrief',
            'icon': 'https://cdn-icons-png.flaticon.com/512/2965/2965363.png'
        }
        if click_url: params['url'] = click_url
        requests.get(url, params=params, timeout=10)
        print(f"✅ Bark 推送成功")
    except Exception as e:
        print(f"⚠️ Bark 推送失败: {e}")

def generate_html_file(markdown_text: str, output_path: str, audio_filename: str):
    """生成移动端友好的 HTML 页面"""
    print("🎨 正在生成 HTML 网页...")
    html_body = markdown.markdown(markdown_text)
    
    template = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <title>晨间猎手内参</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Helvetica Neue", Arial, sans-serif; background: #f7f7f7; color: #333; line-height: 1.75; margin: 0; padding: 0; }}
            .container {{ max-width: 650px; margin: 0 auto; background: #fff; padding: 20px 18px; min-height: 100vh; }}
            h1 {{ font-size: 22px; font-weight: bold; margin-bottom: 10px; line-height: 1.4; }}
            h2 {{ font-size: 18px; margin-top: 35px; border-left: 4px solid #d32f2f; padding-left: 10px; font-weight: 700; margin-bottom: 15px; }}
            h3 {{ font-size: 16px; font-weight: bold; margin-top: 20px; color: #444; }}
            p {{ margin-bottom: 16px; font-size: 16px; text-align: justify; }}
            strong {{ color: #d32f2f; font-weight: 700; }}
            ul {{ padding-left: 20px; }}
            li {{ margin-bottom: 8px; font-size: 16px; }}
            .audio-box {{ margin: 20px 0; padding: 15px; background: #f1f3f4; border-radius: 8px; text-align: center; }}
            audio {{ width: 100%; margin-top: 10px; outline: none; }}
            .meta {{ font-size: 14px; color: #888; margin-bottom: 20px; }}
            .footer {{ text-align: center; font-size: 12px; color: #ccc; margin-top: 50px; padding-bottom: 30px; }}
            hr {{ border: 0; border-top: 1px solid #eee; margin: 30px 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>☕️ 晨间猎手内参 · 深度咖啡版</h1>
            <div class="meta">{datetime.now().strftime('%Y年%m月%d日')} | AI 商业情报</div>
            
            <div class="audio-box">
                <div style="font-weight:bold; color:#555; margin-bottom:5px;">🎧 点击收听今日简报</div>
                <audio controls src="./{audio_filename}">您的浏览器不支持音频播放。</audio>
            </div>
            
            {html_body}
            
            <div class="footer">Powered by AI Hunter & GitHub Actions</div>
        </div>
    </body>
    </html>
    """
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(template)

# ========== 核心逻辑区 ==========

def fetch_rss_articles() -> Tuple[List[Dict], str]:
    """抓取 RSS 并返回 (文章列表, 统计信息字符串)"""
    articles = []
    stats = {}
    
    now = datetime.now()
    cutoff_time = now - timedelta(hours=25) 
    
    # 伪装成 Chrome 浏览器，解决官方源的反爬限制
    FAKE_HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8'
    }
    
    print(f"📰 正在从 {len(RSS_SOURCES)} 个源抓取新闻...")
    
    for source_url in RSS_SOURCES:
        try:
            # 使用 requests 获取内容，再传给 feedparser，这样可以完全控制 Headers
            resp = requests.get(source_url, headers=FAKE_HEADERS, timeout=15)
            if resp.status_code != 200:
                print(f"  ❌ {source_url}: HTTP {resp.status_code}")
                continue
                
            feed = feedparser.parse(resp.content)
            source_name = feed.feed.get('title', '未知来源').replace('RSSHub', '').replace(' - ', '').strip()
            
            count = 0
            for entry in feed.entries[:15]:
                # 解析时间
                pub_time = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    pub_time = datetime(*entry.published_parsed[:6])
                
                # 筛选最近25小时
                if not pub_time or pub_time > cutoff_time:
                    articles.append({
                        'title': entry.title,
                        'summary': entry.get('summary', '')[:300], # 截取摘要
                        'source': source_name
                    })
                    count += 1
            
            if count > 0:
                stats[source_name] = count
                print(f"  ✅ {source_name}: 获取 {count} 条")
            else:
                if feed.bozo:
                    print(f"  ⚠️ {source_name}: 解析异常 (可能被拦截)")
                else:
                    print(f"  ⚠️ {source_name}: 0 条更新")
                
        except Exception as e:
            print(f"  ❌ {source_url}: {e}")
    
    # 生成统计报告
    if not stats:
        stats_str = "⚠️ 本次未从任何源提取到新闻，可能是网络波动或源站反爬。"
    else:
        stats_str = "\n".join([f"- {name}: {cnt}条" for name, cnt in stats.items()])
    
    print(f"📊 总计获取 {len(articles)} 条有效新闻")
    return articles[:60], stats_str

def _call_ai(prompt: str, max_tokens: int) -> str:
    """调用 DashScope API 生成内容"""
    if not DASHSCOPE_API_KEY:
        return "❌ 错误：未配置 DASHSCOPE_API_KEY，请在 GitHub Secrets 中设置。"
    
    system_prompt = """
    你是一位【严谨的商业情报分析师】。
    
    **核心原则**：
    1. **基于事实**：所有分析必须严格基于用户提供的【新闻素材】。如果不清楚，请忽略，严禁编造。
    2. **禁止穿越**：素材中未提及日期的，默认是“过去24小时”。不要编造未来的日期。
    3. **格式规范**：输出标准的 Markdown 格式。
    """
    
    url = 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions'
    headers = {'Authorization': f'Bearer {DASHSCOPE_API_KEY}', 'Content-Type': 'application/json'}
    payload = {
        'model': 'qwen3-max',
        'messages': [{'role': 'system', 'content': system_prompt}, {'role': 'user', 'content': prompt}],
        'max_tokens': max_tokens + 2000,
        'temperature': 0.2, # 低温度，保证 factual correctness
        'enable_thinking': True,
        'thinking_budget': 1024
    }
    
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=300)
        resp_json = resp.json()
        if 'choices' in resp_json:
            return resp_json['choices'][0]['message']['content']
        else:
            print(f"AI Response Error: {resp_json}")
            return "AI 生成返回格式异常"
    except Exception as e:
        print(f"AI Connection Error: {e}")
        return "AI 生成服务暂时不可用"

def generate_content(articles: List[Dict], stats_str: str) -> str:
    print("✍️  正在生成文稿...")
    
    # === 熔断机制 ===
    if not articles:
        return f"""
# 晨间猎手内参
**{datetime.now().strftime('%Y年%m月%d日')}**

---

## ⚠️ 今日暂停更新

系统在过去 24 小时内未检测到有效新闻信号。
可能原因：
1. 节假日新闻源停更
2. 网络连接异常
3. 数据源反爬虫策略更新

### 📊 系统诊断
{stats_str}
        """

    week_days = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    now = datetime.now()
    date_str = now.strftime('%Y年%m月%d日')
    weekday_str = week_days[now.weekday()]
    
    news_pool = ""
    for i, a in enumerate(articles):
        news_pool += f"{i+1}. [{a['source']}] {a['title']}\n摘要：{a['summary']}\n\n"
    
    prompt = f"""
    今天是{date_str}，{weekday_str}。
    请仅基于以下【新闻素材】，撰写一份晨间内参。
    
    **素材池：**
    {news_pool}
    
    **写作要求：**
    
    ## 第一部分：全景扫描
    （从素材中精选 8-10 条有价值的新闻。格式："- **来源**：具体内容"。）
    
    ## 第二部分：深度分析
    （仅当素材中有足够信息支撑时，选出 1-3 个话题进行拆解。）
    格式：
    ### 话题一：[标题]
    1. **现状**：(基于素材)
    2. **猎手拆解**：
       - **利益链条**：[谁在赚钱/亏钱？]
       - **底层逻辑**：[政策或商业本质]
    3. **搞钱路径**：
       - **短线/中线**：[机会点]
    
    ---
    
    (文末附上)
    ### 📊 本期数据源统计
    {stats_str}
    """
    
    return _call_ai(prompt, max_tokens=5000)

async def generate_audio(text: str, output_path: str):
    print(f"🎙️  正在生成音频...")
    clean_text = clean_text_for_tts(text)
    # 使用 Edge TTS，加 5% 语速
    communicate = edge_tts.Communicate(clean_text, voice=VOICE_NAME, rate='+5%')
    await communicate.save(output_path)

def generate_rss(audio_url: str):
    today = datetime.now().strftime('%Y-%m-%d')
    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>晨间猎手</title><item><title>{today}</title>
<enclosure url="{audio_url}" type="audio/mpeg" length="100000"/><guid>{today}</guid>
</item></channel></rss>"""
    with open(RSS_FILE, 'w') as f: f.write(content)

# ========== 主程序入口 ==========

def main():
    print("🚀 启动任务 (GitHub Actions Mode)...")
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        
        # 1. 抓取 (带统计)
        articles, stats_str = fetch_rss_articles()
        
        # 2. AI 写作
        full_markdown = generate_content(articles, stats_str)
        
        # 3. 保存 Markdown
        with open(MD_FILE, 'w', encoding='utf-8') as f:
            f.write(full_markdown)
            
        # 4. 生成网页
        generate_html_file(full_markdown, HTML_FILE, AUDIO_FILENAME)
        
        # 5. 生成音频
        asyncio.run(generate_audio(full_markdown, AUDIO_FILE))
        
        # 6. 生成链接
        if '/' in GITHUB_REPO:
            username, repo_name = GITHUB_REPO.split('/')
            page_url = f"https://{username}.github.io/{repo_name}/{OUTPUT_DIR}/briefing_{DATE_STR}.html"
            rss_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{OUTPUT_DIR}/{AUDIO_FILENAME}"
        else:
            page_url = "https://github.com"
            rss_url = ""

        generate_rss(rss_url)
        
        # 7. Bark 推送
        summary = clean_text_for_tts(full_markdown)[:60]
        if "暂停更新" in full_markdown: summary = "今日无有效新闻提取"
        
        send_bark_notification(
            f"{datetime.now().strftime('%m月%d日')}晨间猎手", 
            summary, 
            click_url=page_url
        )
        
        # 8. 清理
        cleanup_old_files()
        print("✅ 任务全部完成")
        
    except Exception as e:
        print(f"❌ 严重错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
