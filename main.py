#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
私人晨间情报官 - 网页版 (HTML Generator)
功能：
1. 抓取全网核心商业/科技新闻
2. "商业猎手"风格深度拆解
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
from typing import List, Dict

# 自动安装依赖
try:
    import edge_tts
except ImportError:
    os.system("pip install edge-tts")
    import edge_tts

try:
    import markdown
except ImportError:
    print("正在安装 markdown 库...")
    os.system("pip install markdown")
    import markdown

# ========== 配置区 ==========
DASHSCOPE_API_KEY = os.getenv('DASHSCOPE_API_KEY')
BARK_KEY = os.getenv('BARK_KEY')
# 获取 GitHub 仓库信息 (格式: username/repo)
GITHUB_REPO = os.getenv('GITHUB_REPOSITORY', 'yourname/yourrepo') 

# 🔥 终极 RSS 源列表 (已按你的需求整理)
RSS_SOURCES = [
    # --- 第一梯队：金融核心 (华尔街见闻 + 财联社) ---
    "https://rsshub.app/wallstreetcn/live/global/2",      # 华尔街见闻-重要快讯
    "https://rsshub.app/wallstreetcn/hot/day",            # 华尔街见闻-每日最热
    "https://rsshub.app/cls/telegraph/red",               # 财联社-加红电报
    
    # --- 第二梯队：权威官媒 (新华社 + 澎湃 + 第一财经) ---
    "https://rsshub.app/news/xhsxw",                      # 新华社新闻
    "https://rsshub.app/thepaper/channel/25951",          # 澎湃-财经
    "https://rsshub.app/thepaper/channel/25950",          # 澎湃-时事
    "https://rsshub.app/yicai/headline",                  # 第一财经-头条
    "https://rsshub.app/yicai/latest",                    # 第一财经-最新
    
    # --- 第三梯队：深度与科技 (虎嗅 + 36Kr + 少数派) ---
    "https://rsshub.app/huxiu/channel/103",               # 虎嗅-商业消费
    "https://rsshub.app/36kr/newsflashes",                # 36Kr快讯
    "https://rsshub.app/sspai/index",                     # 少数派
    "https://rsshub.app/woshipm/popular/daily",           # 人人都是产品经理
    
    # --- 第四梯队：研报与深度 ---
    "https://rsshub.app/eastmoney/report/strategyreport", # 东方财富-策略研报
    "https://rsshub.app/infzm/2",                         # 南方周末
]

# 输出配置
OUTPUT_DIR = 'output'
DATE_STR = datetime.now().strftime('%Y%m%d')
AUDIO_FILENAME = f'briefing_{DATE_STR}.mp3'
AUDIO_FILE = f'{OUTPUT_DIR}/{AUDIO_FILENAME}'
MD_FILE = f'{OUTPUT_DIR}/briefing_{DATE_STR}.md'   # 保存 Markdown 源码
HTML_FILE = f'{OUTPUT_DIR}/briefing_{DATE_STR}.html' # 保存生成的网页
RSS_FILE = 'feed.xml'

# 语音配置
VOICE_NAME = 'zh-CN-YunxiNeural'

# ========== 工具函数 ==========

def clean_text_for_tts(text: str) -> str:
    """TTS 清洗：去掉 Markdown 符号，保留文字"""
    text = re.sub(r'#+\s?', '', text)         # 去标题
    text = re.sub(r'\*\*|__|\*', '', text)    # 去加粗
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text) # 去链接
    text = re.sub(r'>\s?', '', text)          # 去引用
    text = re.sub(r'[-*]{3,}', '', text)      # 去分割线
    return text.strip()

def cleanup_old_files(days_to_keep: int = 3):
    """清理旧文件"""
    print(f"🧹 清理 {days_to_keep} 天前的旧文件...")
    now = time.time()
    cutoff = now - (days_to_keep * 86400)
    if not os.path.exists(OUTPUT_DIR): return
    
    files = glob.glob(os.path.join(OUTPUT_DIR, '*'))
    for f in files:
        if os.path.basename(f).startswith('.'): continue
        if os.path.getmtime(f) < cutoff:
            try:
                os.remove(f)
            except: pass

def send_bark_notification(title: str, content: str, click_url: str = None):
    """Bark 推送"""
    if not BARK_KEY: return
    try:
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
        print(f"⚠️ Bark 失败: {e}")

def generate_html_file(markdown_text: str, output_path: str, audio_filename: str):
    """生成仿公众号风格的移动端 HTML"""
    print("🎨 正在生成 HTML 网页...")
    
    # 1. Markdown 转 HTML
    html_body = markdown.markdown(markdown_text)
    
    # 2. 定义 CSS 样式 (移动端优化)
    template = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <title>晨间猎手内参</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Helvetica Neue", Arial, sans-serif;
                background-color: #f7f7f7;
                color: #333;
                line-height: 1.75;
                margin: 0;
                padding: 0;
            }}
            .container {{
                max-width: 650px;
                margin: 0 auto;
                background: #fff;
                padding: 20px 18px;
                min-height: 100vh;
            }}
            /* 标题样式 */
            h1 {{ font-size: 22px; font-weight: bold; margin-bottom: 10px; line-height: 1.4; }}
            h2 {{ 
                font-size: 18px; 
                margin-top: 35px; 
                margin-bottom: 15px; 
                border-left: 4px solid #d32f2f; 
                padding-left: 10px;
                font-weight: 700;
            }}
            h3 {{ font-size: 16px; font-weight: bold; margin-top: 20px; color: #444; }}
            
            /* 正文样式 */
            p {{ margin-bottom: 16px; font-size: 16px; text-align: justify; color: #333; }}
            strong {{ color: #d32f2f; font-weight: 700; }}
            
            /* 引用和列表 */
            blockquote {{
                background: #f9f9f9;
                border-left: 4px solid #ccc;
                margin: 15px 0;
                padding: 10px 15px;
                color: #666;
                font-size: 15px;
            }}
            ul {{ padding-left: 20px; }}
            li {{ margin-bottom: 8px; font-size: 16px; }}
            
            /* 播放器样式 */
            .audio-box {{
                margin: 20px 0;
                padding: 15px;
                background: #f1f3f4;
                border-radius: 8px;
                text-align: center;
            }}
            audio {{ width: 100%; margin-top: 10px; }}
            
            .meta {{ font-size: 14px; color: #888; margin-bottom: 20px; }}
            .footer {{ text-align: center; font-size: 12px; color: #ccc; margin-top: 50px; padding-bottom: 30px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>☕️ 晨间猎手内参 · 深度咖啡版</h1>
            <div class="meta">{datetime.now().strftime('%Y年%m月%d日')} | AI 商业情报</div>
            
            <div class="audio-box">
                <div style="font-weight:bold; color:#555; margin-bottom:5px;">🎧 点击收听今日简报</div>
                <audio controls src="./{audio_filename}">
                    您的浏览器不支持音频播放。
                </audio>
            </div>
            
            {html_body}
            
            <div class="footer">Powered by AI Hunter & GitHub Actions</div>
        </div>
    </body>
    </html>
    """
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(template)

def fetch_rss_articles() -> List[Dict]:
    """抓取 RSS"""
    articles = []
    now = datetime.now()
    cutoff_time = now - timedelta(hours=24)
    print(f"📰 正在从 {len(RSS_SOURCES)} 个源抓取新闻...")
    
    for source_url in RSS_SOURCES:
        try:
            feed = feedparser.parse(source_url, agent='Mozilla/5.0')
            source_name = feed.feed.get('title', '未知').replace('RSSHub', '').strip()
            
            for entry in feed.entries[:10]:
                pub_time = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    pub_time = datetime(*entry.published_parsed[:6])
                if pub_time and pub_time < cutoff_time: continue
                
                articles.append({
                    'title': entry.title,
                    'summary': entry.get('summary', '')[:200],
                    'source': source_name
                })
        except: pass
    
    print(f"📊 获取 {len(articles)} 条有效新闻")
    return articles[:50]

# ========== AI 生成逻辑 ==========

def _call_ai(prompt: str, max_tokens: int) -> str:
    if not DASHSCOPE_API_KEY: raise ValueError("无 API Key")
    
    # System Prompt: 允许 Markdown 格式
    system_prompt = """
    你是一位【商业情报猎手】。
    1. 语言风格：犀利、透彻、老练。
    2. **格式要求**：使用 Markdown 排版！
       - 用 `##` 标记板块标题。
       - 用 `###` 标记新闻小标题。
       - 用 `**` 加粗重点数据或观点。
       - 用 `-` 做列表。
    3. 内容深度：必须包含【现状层】、【猎手拆解】、【搞钱路径】。
    """
    
    url = 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions'
    headers = {'Authorization': f'Bearer {DASHSCOPE_API_KEY}', 'Content-Type': 'application/json'}
    payload = {
        'model': 'qwen3-max',
        'messages': [{'role': 'system', 'content': system_prompt}, {'role': 'user', 'content': prompt}],
        'max_tokens': max_tokens + 2000,
        'temperature': 0.7,
        'enable_thinking': True,
        'thinking_budget': 2000
    }
    
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=300)
        return resp.json()['choices'][0]['message']['content']
    except Exception as e:
        print(f"AI Error: {e}")
        return "生成失败"

def generate_content(articles: List[Dict]) -> str:
    print("✍️  正在生成文稿 (Flash + Deep Dive)...")
    
    # 整理素材
    news_pool = "\n".join([f"- {a['title']} ({a['source']})" for a in articles[:40]])
    date_str = datetime.now().strftime('%Y年%m月%d日')
    
    prompt = f"""
    今天是{date_str}。请基于以下素材，撰写一份完整的【晨间猎手内参】。
    
    **文章结构要求：**
    
    ## 第一部分：全景扫描
    （模仿“早报快讯”风格，按时间轴排列，总共12-15条。国内/国际/财经/科技分类。）
    格式示例：
    - **08:00** 标题内容。（来源）
    
    ## 第二部分：猎手深度分析
    （选出3-4个最影响钱袋子的话题，深度拆解。）
    
    ### 话题一：[标题]
    1. **现状**：发生什么？
    2. **猎手拆解**：利益链条与底层逻辑。
    3. **搞钱路径**：普通人如何应对？
    
    (以此类推...)
    
    新闻素材：
    {news_pool}
    """
    return _call_ai(prompt, max_tokens=6000)

async def generate_audio(text: str, output_path: str):
    print(f"🎙️  生成音频...")
    # 清洗掉 HTML/Markdown 符号供 TTS 阅读
    clean_text = clean_text_for_tts(text)
    communicate = edge_tts.Communicate(clean_text, voice=VOICE_NAME, rate='+5%')
    await communicate.save(output_path)

def generate_rss(audio_url: str):
    today = datetime.now().strftime('%Y-%m-%d')
    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>晨间猎手</title><item><title>{today}</title>
<enclosure url="{audio_url}" type="audio/mpeg" length="100000"/><guid>{today}</guid>
</item></channel></rss>"""
    with open(RSS_FILE, 'w') as f: f.write(content)

# ========== 主程序 ==========

def main():
    print("🚀 启动任务...")
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        
        # 1. 获取新闻
        articles = fetch_rss_articles()
        if not articles: articles = [{'title': '无新闻', 'source': 'System'}]

        # 2. AI 生成 Markdown 文稿
        full_markdown = generate_content(articles)
        
        # 3. 保存 Markdown 源码
        with open(MD_FILE, 'w', encoding='utf-8') as f:
            f.write(full_markdown)
            
        # 4. 生成 HTML 网页 (核心步骤)
        generate_html_file(full_markdown, HTML_FILE, AUDIO_FILENAME)
        
        # 5. 生成音频
        asyncio.run(generate_audio(full_markdown, AUDIO_FILE))
        
        # 6. 生成链接 & 推送
        # 构造 GitHub Pages 的访问链接
        # 格式: https://username.github.io/repo/output/briefing_date.html
        if '/' in GITHUB_REPO:
            username, repo_name = GITHUB_REPO.split('/')
            page_url = f"https://{username}.github.io/{repo_name}/{OUTPUT_DIR}/briefing_{DATE_STR}.html"
            rss_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{OUTPUT_DIR}/{AUDIO_FILENAME}"
        else:
            page_url = "https://github.com" # 兜底
            rss_url = ""

        generate_rss(rss_url)
        
        # Bark 推送：点击直接跳转到 HTML 网页
        summary = clean_text_for_tts(full_markdown)[:80]
        send_bark_notification(
            f"{datetime.now().strftime('%m月%d日')}晨间猎手", 
            summary, 
            click_url=page_url
        )
        
        cleanup_old_files()
        print("✅ 任务完成")
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
