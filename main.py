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
]

# 输出目录配置
OUTPUT_DIR = 'output'
AUDIO_FILE = f'{OUTPUT_DIR}/briefing.mp3'
TEXT_FILE = f'{OUTPUT_DIR}/briefing.txt'
RSS_FILE = 'feed.xml'

# Edge-TTS 语音配置（推荐的中文播客音色）
VOICE_NAME = 'zh-CN-YunxiNeural'  # 男声，你也可以改为 'zh-CN-XiaoxiaoNeural'（女声）

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
    返回格式: [{'title': '', 'summary': '', 'link': '', 'source': ''}]
    """
    articles = []
    now = datetime.now()
    cutoff_time = now - timedelta(hours=24)
    
    print(f"📰 开始从 {len(RSS_SOURCES)} 个源抓取新闻...")
    
    for source_url in RSS_SOURCES:
       try:
           feed = feedparser.parse(
                source_url,
                agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            )
            source_name = feed.feed.get('title', source_url)
            
            for entry in feed.entries[:15]:  # 每个源取前15条
                # 解析发布时间
                pub_time = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    pub_time = datetime(*entry.published_parsed[:6])
                
                # 只保留24小时内的新闻
                if pub_time and pub_time < cutoff_time:
                    continue
                
                articles.append({
                    'title': entry.title,
                    'summary': entry.get('summary', entry.get('description', ''))[:300],
                    'link': entry.link,
                    'source': source_name
                })
            
            print(f"  ✓ {source_name}: 获取 {len([a for a in articles if a['source'] == source_name])} 条")
            time.sleep(1)  # 避免请求过快
            
        except Exception as e:
            print(f"  ✗ 抓取失败 {source_url}: {e}")
    
    print(f"📊 共获取 {len(articles)} 条新闻\n")
    return articles[:40]  # 最多保留40条


def _call_dashscope(model: str, prompt: str, max_tokens: int, temperature: float, extra_params: dict = None) -> str:
    """
    底层 DashScope API 调用封装（所有模型共用）
    """
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
            {
                'role': 'system',
                'content': '你是一位资深财经编辑，擅长将商业新闻转化为深度投研分析。语言风格：简洁、数据驱动、直击本质。'
            },
            {
                'role': 'user',
                'content': prompt
            }
        ],
        'max_tokens': max_tokens,
        'temperature': temperature
    }
    
    # 合并额外参数（如 enable_thinking）
    if extra_params:
        payload.update(extra_params)
    
    # Thinking 模式耗时更长，非 thinking 模式 60s 够用
    timeout = 300 if extra_params and extra_params.get('enable_thinking') else 60
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        result = response.json()
        
        choice = result['choices'][0]['message']
        
        # 如果是 thinking 模式，打印推理过程长度
        if 'reasoning_content' in choice and choice['reasoning_content']:
            print(f"    💭 推理过程: {len(choice['reasoning_content'])}字")
        
        return choice['content']
    except requests.exceptions.Timeout:
        print(f"❌ API 调用超时（模型: {model}）")
        raise
    except Exception as e:
        print(f"❌ API 调用失败（模型: {model}）: {e}")
        raise


def call_qwen_flash(prompt: str, max_tokens: int = 1000) -> str:
    """
    轻量级任务专用 → qwen3-flash
    场景：选题筛选、简单分类、快速摘要
    特点：极快响应，费用最低（¥0.1/百万输入，¥0.4/百万输出）
    """
    print(f"  ⚡ 调用 qwen3-flash（轻量级任务）...")
    return _call_dashscope(
        model='qwen3-flash',
        prompt=prompt,
        max_tokens=max_tokens,
        temperature=0.7
    )


def call_qwen_max_thinking(prompt: str, max_tokens: int = 4000) -> str:
    """
    核心深度分析专用 → qwen3-max + thinking
    场景：板块A/B 的投研级深度撰写
    特点：深度推理，质量最高（¥2.5/百万输入，¥10/百万输出）
    """
    thinking_budget = min(max_tokens * 2, 16000)
    print(f"  🧠 调用 qwen3-max-thinking（深度分析，思考预算: {thinking_budget} tokens）...")
    return _call_dashscope(
        model='qwen3-max',
        prompt=prompt,
        max_tokens=max_tokens + thinking_budget,
        temperature=0.6,
        extra_params={
            'enable_thinking': True,
            'thinking_budget': thinking_budget
        }
    )


def generate_section_a_overview(articles: List[Dict]) -> str:
    """
    生成板块A：全景扫描（2000-2500字）
    要求中国内容占50%
    """
    print("✍️  正在生成【板块A：全景扫描】...")
    
    # 将新闻按来源分类
    china_news = [a for a in articles if any(keyword in a['source'] for keyword in ['36kr', '澎湃', '财新', '界面', '虎嗅'])]
    global_news = [a for a in articles if a not in china_news]
    
    # 构建新闻素材文本
    news_text = "【中国市场动态】\n"
    for i, article in enumerate(china_news[:15], 1):
        news_text += f"{i}. {article['title']}\n   {article['summary'][:150]}\n\n"
    
    news_text += "\n【全球商业科技】\n"
    for i, article in enumerate(global_news[:10], 1):
        news_text += f"{i}. {article['title']}\n   {article['summary'][:150]}\n\n"
    
    prompt = f"""
请基于以下新闻素材，撰写一份**2000-2500字**的"全球商业科技 + 中国民生动态"概览。

# 硬性要求
1. **中国相关内容必须占50%以上**
2. 重点关注领域：
   - 社保、医保、公积金政策变化
   - 房地产市场（新房、二手房、租赁政策）
   - 消费品行业（汽车、家电、快消）
   - 科技大厂动态（阿里、腾讯、字节、华为等）
   - 制造业升级与出海

3. 写作风格：
   - 用数据说话，避免空话套话
   - 每个话题点到为止（150-200字）
   - 突出"这事跟普通人/中小企业有什么关系"

# 新闻素材
{news_text}

# 输出格式
请直接输出正文内容，不要包含任何标题或"板块A"等字样。
"""
    
    return call_qwen_max_thinking(prompt, max_tokens=3000)


def generate_section_b_deep_dive(articles: List[Dict]) -> str:
    """
    生成板块B：猎手深度分析（5-6个话题，共5000字）
    每个话题按照"现象→本质→搞钱→风险"框架分析
    """
    print("✍️  正在生成【板块B：猎手深度分析】...")
    
    # 第一步：让AI选出最值得深挖的5-6个话题
    selection_prompt = f"""
从以下新闻中，选出**5-6个最具商业价值和赚钱潜力的话题**。

# 筛选标准
1. 有明确的产业趋势或政策红利
2. 普通人或中小企业能参与（不是纯宏观话题）
3. 覆盖不同领域，避免重复

# 新闻列表
{chr(10).join([f"{i+1}. {a['title']}" for i, a in enumerate(articles[:30])])}

# 输出格式
请直接输出话题列表，格式如下：
1. 话题名称（20字以内）
2. 话题名称
3. ...
"""
    
    selected_topics = call_qwen_flash(selection_prompt, max_tokens=500)
    print(f"  已选出话题:\n{selected_topics}\n")
    
    # 第二步：对每个话题进行深度分析
    analysis_prompt = f"""
针对以下已选定的商业话题，进行**华尔街投研级深度分析**（总计5000字左右）。

# 已选话题
{selected_topics}

# 分析框架（每个话题800-1000字）
对每个话题按照以下结构展开：

1. **现象速写**（150字）
   - 这事儿发生了什么？核心数据是什么？

2. **本质拆解**（300字）
   - 背后的商业逻辑/政策逻辑是什么？
   - 为什么现在发生？谁是受益者？

3. **搞钱路径**（300字）
   - 普通人怎么参与？（投资、副业、技能提升）
   - 中小企业有什么机会？（供应链、服务、工具）

4. **风险预警**（200字）
   - 哪些坑要避开？（政策风险、市场风险、技术门槛）
   - 什么时候该止损？

# 新闻参考
{chr(10).join([f"- {a['title']}: {a['summary'][:100]}" for a in articles[:25]])}

# 写作要求
- 用人话说专业事，避免大词空话
- 多举具体案例（公司名、产品名、数据）
- 语气像在给朋友做投资建议

# 输出格式
直接输出分析正文，每个话题用"---"分隔，不要加标题前缀。
"""
    
    return call_qwen_max_thinking(analysis_prompt, max_tokens=6000)


def assemble_full_script(section_a: str, section_b: str) -> str:
    """
    组装完整的播客文稿
    """
    date_str = datetime.now().strftime('%Y年%m月%d日 星期%w').replace('星期0', '星期日').replace('星期1', '星期一').replace('星期2', '星期二').replace('星期3', '星期三').replace('星期4', '星期四').replace('星期5', '星期五').replace('星期6', '星期六')
    
    script = f"""
欢迎收听私人晨间情报，今天是{date_str}。

接下来的40分钟，我将为你带来全球商业科技与中国民生的最新动态，以及5到6个最值得关注的深度话题分析。

首先进入全景扫描板块。

{section_a}

以上是全景扫描部分。接下来进入猎手深度分析板块，我将带你深挖几个最具商业价值的话题。

{section_b}

以上就是今日的深度情报。记住：信息差就是财富差，行动快的人永远比犹豫的人先吃到肉。

祝你今天抓住红利，规避风险。我们明天同一时间再见。
"""
    
    return script


async def generate_audio(text: str, output_path: str):
    """
    使用 Edge-TTS 生成音频
    """
    print(f"🎙️  正在生成音频（约需2-3分钟）...")
    
    communicate = edge_tts.Communicate(text, voice=VOICE_NAME, rate='+5%')  # 语速加快5%
    await communicate.save(output_path)
    
    # 获取音频时长
    file_size = os.path.getsize(output_path) / (1024 * 1024)  # MB
    print(f"  ✓ 音频已生成: {output_path} ({file_size:.1f} MB)")


def generate_rss_feed(script: str, audio_url: str):
    """
    生成符合播客标准的 RSS Feed
    """
    print("📡 正在生成 RSS Feed...")
    
    date_str = datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0800')
    episode_date = datetime.now().strftime('%Y-%m-%d')
    
    rss_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" 
     xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
     xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>私人晨间情报</title>
    <description>每日AI定制深度商业分析·仅供个人使用</description>
    <language>zh-cn</language>
    <link>https://github.com/{os.getenv('GITHUB_REPOSITORY', 'your-repo')}</link>
    <atom:link href="{audio_url.rsplit('/', 1)[0]}/feed.xml" rel="self" type="application/rss+xml"/>
    
    <itunes:author>AI情报官</itunes:author>
    <itunes:summary>40分钟深度商业情报播客</itunes:summary>
    <itunes:category text="Business"/>
    <itunes:explicit>no</itunes:explicit>
    
    <item>
      <title>{episode_date} 晨间情报</title>
      <description><![CDATA[{script[:500]}...]]></description>
      <pubDate>{date_str}</pubDate>
      <enclosure url="{audio_url}" type="audio/mpeg" length="{os.path.getsize(AUDIO_FILE)}"/>
      <guid isPermaLink="false">{episode_date}</guid>
      <itunes:duration>40:00</itunes:duration>
    </item>
  </channel>
</rss>"""
    
    with open(RSS_FILE, 'w', encoding='utf-8') as f:
        f.write(rss_content)
    
    print(f"  ✓ RSS Feed 已生成: {RSS_FILE}")


# ========== 主流程 ==========

def main():
    """主程序入口"""
    start_time = time.time()
    
    print("=" * 60)
    print("🚀 私人深度晨间情报官 启动")
    print(f"⏰ 运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60 + "\n")
    
    try:
        # 1. 创建输出目录
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        
        # 2. 抓取新闻
        articles = fetch_rss_articles()
        if len(articles) < 10:
            raise ValueError(f"新闻数量不足（仅{len(articles)}条），请检查RSS源")
        
        # 3. 生成内容（分两个板块）
        section_a = generate_section_a_overview(articles)
        section_b = generate_section_b_deep_dive(articles)
        
        # 4. 组装完整文稿
        full_script = assemble_full_script(section_a, section_b)
        
        # 5. 保存文本版本
        with open(TEXT_FILE, 'w', encoding='utf-8') as f:
            f.write(full_script)
        print(f"📄 文稿已保存: {TEXT_FILE} ({len(full_script)}字)\n")
        
        # 6. 生成音频
        asyncio.run(generate_audio(full_script, AUDIO_FILE))
        
        # 7. 生成 RSS Feed
        repo = os.getenv('GITHUB_REPOSITORY', 'your-username/your-repo')
        audio_url = f"https://raw.githubusercontent.com/{repo}/main/{AUDIO_FILE}"
        generate_rss_feed(full_script, audio_url)
        
        # 8. 发送完成通知
        elapsed = int(time.time() - start_time)
        send_bark_notification(
            "晨间情报已生成",
            f"用时{elapsed}秒·{len(full_script)}字·小宇宙可收听"
        )
        
        print("\n" + "=" * 60)
        print("✅ 全部完成！")
        print(f"📊 统计: {len(articles)}条新闻 → {len(full_script)}字文稿")
        print(f"⏱️  用时: {elapsed}秒")
        print("🔗 RSS订阅地址:")
        print(f"   https://raw.githubusercontent.com/{repo}/main/feed.xml")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ 运行失败: {e}")
        send_bark_notification("晨间情报生成失败", str(e)[:100])
        sys.exit(1)


if __name__ == '__main__':
    main()
