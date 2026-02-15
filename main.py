import os
import asyncio
import feedparser  # 你的新武器
import edge_tts
from datetime import datetime
from http import HTTPStatus
import dashscope
import glob

# ================= 1. 猎手雷达设置 (借鉴 Intel Briefing) =================

# 这里把 V2EX (焦虑源) 和 Hacker News (技术源) 都加进来了
RSS_SOURCES = {
    "signals": [ # 【焦虑信号】寻找痛点、求助、吐槽
        "https://www.v2ex.com/index.xml",  # V2EX 全站热帖
        "https://www.reddit.com/r/SaaS/new/.rss", # SaaS 圈子
    ],
    "shovels": [ # 【掘金铲子】寻找工具、方案
        "https://news.ycombinator.com/rss", # Hacker News
        "https://stratechery.com/feed/",   # 深度商业分析
    ],
    "macro": [   # 【宏观风向】钱往哪里流
        "https://feed.36kr.com/feed",      # 36Kr
        # 你可以继续在这里加华尔街见闻的 RSS
    ]
}

# ================= 2. 猎手思维模型 (你的新 Prompt) =================

HUNTER_SYSTEM_PROMPT = """
你不再是新闻播报员，你是“晨间商业猎手”。你的任务是从信息中嗅出“钱味”。
请阅读以下聚合的全球情报，严格按照框架输出一份【商业情报内参】：

## 🎯 第一步：焦虑信号 (Signal)
* **逆向判断**：忽略热点情绪，指出流量正流向哪个具体细分领域？
* **痛点锁定**：谁在焦虑？(新手/老手/企业主) 他们的具体痛苦是什么？(太贵/太慢/太难)
* **机会判断**：哪里有“海量新人涌入”但“基础设施只有简陋的中游产品”，哪里就是机会。

## 🛠 第二步：掘金铲子 (Shovel)
* **生态位分析**：当前处于产业链的上游(工具)、中游(生产)还是下游(分发)？
* **避坑指南**：明确指出哪里是红海，不要去碰。
* **搞钱路径**：基于今日情报，给出一个具体的行动建议。(例如：开发某类插件、制作某类教程、提供某类数据服务)

## 📢 猎手广播 (Podcast Script)
(请生成一段300字以内的口语化播报文稿。
要求：语气犀利、自信，像个老朋友一样告诉听众今天的最大机会在哪里。
不要念新闻标题，直接说结论和机会点。)
"""

# ================= 3. 核心功能函数 =================

def fetch_rss_intel(category):
    """抓取指定分类的 RSS 情报"""
    print(f"🕵️‍♂️ [猎手雷达] 正在扫描 {category} 频道...")
    combined_content = ""
    
    # 遍历该分类下的所有源
    for url in RSS_SOURCES.get(category, []):
        try:
            # 设置超时，防止卡死
            feed = feedparser.parse(url)
            # 只取前 3 条最新内容，避免 Token 爆炸
            for entry in feed.entries[:3]:
                title = getattr(entry, 'title', '无标题')
                link = getattr(entry, 'link', '无链接')
                # 清洗摘要，去掉HTML标签过于复杂的部分，只取前200字
                summary = getattr(entry, 'summary', '')[:200] 
                combined_content += f"【标题】{title}\n【链接】{link}\n【摘要】{summary}\n\n"
        except Exception as e:
            print(f"⚠️ 抓取失败 {url}: {e}")
            
    return combined_content

def analyze_with_hunter_ai(content):
    """调用通义千问进行深度拆解"""
    if not content:
        return "今日雷达未捕捉到有效信号。"

    print("🧠 [猎手大脑] 正在拆解商业逻辑...")
    try:
        dashscope.api_key = os.getenv("DASHSCOPE_API_KEY")
        response = dashscope.Generation.call(
            model=dashscope.Generation.Models.qwen_turbo, 
            messages=[
                {'role': 'system', 'content': HUNTER_SYSTEM_PROMPT},
                {'role': 'user', 'content': f"今日情报汇总数据：\n{content}"}
            ]
        )
        
        if response.status_code == HTTPStatus.OK:
            return response.output.text
        else:
            print(f"❌ AI分析失败: {response.code} - {response.message}")
            return "AI 暂时掉线，请检查 API Key 或额度。"
            
    except Exception as e:
        print(f"❌ 系统错误: {e}")
        return "系统运行出错。"

def cleanup_old_files(output_dir="output", days_to_keep=3):
    """🧹 自动清理 3 天前的旧文件"""
    print("🧹 [扫地僧] 开始清理过期情报...")
    now = time.time()
    cutoff = now - (days_to_keep * 86400)
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        return

    files = glob.glob(os.path.join(output_dir, "*"))
    for f in files:
        # 不删除隐藏文件
        if os.path.basename(f).startswith("."):
            continue
        if os.stat(f).st_mtime < cutoff:
            try:
                os.remove(f)
                print(f"   🗑️ 已删除过期文件: {os.path.basename(f)}")
            except Exception as e:
                print(f"   ❌ 删除失败: {e}")

# ================= 4. 主程序入口 =================

async def main():
    # 1. 准备环境
    today_str = datetime.now().strftime("%Y%m%d")
    output_dir = "output"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # 2. 全网扫描 (收集三大类情报)
    print("🚀 晨间猎手任务启动...")
    signals = fetch_rss_intel("signals")
    shovels = fetch_rss_intel("shovels")
    macro = fetch_rss_intel("macro")
    
    full_intel_text = f"=== 焦虑信号源 ===\n{signals}\n\n=== 掘金铲子源 ===\n{shovels}\n\n=== 宏观风向源 ===\n{macro}"
    
    # 3. AI 深度分析
    analysis_report = analyze_with_hunter_ai(full_intel_text)
    
    # 4. 保存文字报告 (Markdown)
    md_filename = os.path.join(output_dir, f"briefing_{today_str}.md")
    with open(md_filename, "w", encoding="utf-8") as f:
        f.write(f"# 🕵️‍♂️ 晨间猎手内参 ({today_str})\n\n")
        f.write(analysis_report)
    print(f"✅ 文字报告已保存: {md_filename}")
    
    # 5. 生成语音 (提取分析结果中的播报部分)
    # 简单策略：直接朗读 AI 生成的报告（如果报告太长，建议手动让 AI 只输出 500 字摘要）
    # 这里我们假设 Prompt 里的“猎手广播”在最后，为了保险，我们朗读全文的前 800 字
    tts_text = analysis_report[:1000] 
    
    mp3_filename = os.path.join(output_dir, f"briefing_{today_str}.mp3")
    print(f"🎙️ 正在生成语音 (使用 Yunxi 音色)...")
    
    communicate = edge_tts.Communicate(tts_text, "zh-CN-YunxiNeural")
    await communicate.save(mp3_filename)
    print(f"✅ 语音文件已生成: {mp3_filename}")

    # 6. 生成简单的 HTML (适配你的 GitHub Pages)
    html_filename = os.path.join(output_dir, f"briefing_{today_str}.html")
    html_content = f"""
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>晨间猎手内参 {today_str}</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; padding: 20px; line-height: 1.6; max-width: 800px; margin: 0 auto; background-color: #f4f4f5; }}
            .container {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
            h1 {{ color: #333; }}
            h2 {{ color: #0066cc; border-bottom: 2px solid #0066cc; padding-bottom: 10px; margin-top: 30px; }}
            audio {{ width: 100%; margin: 20px 0; }}
            .markdown-body {{ font-size: 16px; color: #333; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🕵️‍♂️ 晨间猎手内参 ({today_str})</h1>
            <audio controls src="briefing_{today_str}.mp3"></audio>
            <div class="markdown-body">
                {analysis_report.replace(chr(10), '<br>')}
            </div>
        </div>
    </body>
    </html>
    """
    with open(html_filename, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"✅ 网页文件已生成: {html_filename}")
    
    # 7. 清理旧文件
    cleanup_old_files(output_dir, days_to_keep=3)

if __name__ == "__main__":
    asyncio.run(main())
