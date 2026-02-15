import os
import asyncio
import feedparser
import edge_tts
import glob
import logging
import time
from datetime import datetime, timedelta
from http import HTTPStatus
import dashscope
from aligo import Aligo

# ================= 1. 猎手雷达设置 =================
RSS_SOURCES = {
    "signals": [ # 【焦虑信号】寻找痛点
        "https://www.v2ex.com/index.xml", 
        "https://www.reddit.com/r/SaaS/new/.rss",
    ],
    "shovels": [ # 【掘金铲子】寻找工具
        "https://news.ycombinator.com/rss",
        "https://stratechery.com/feed/",
    ],
    "macro": [ # 【宏观风向】钱往哪里流
        "https://feed.36kr.com/feed",
    ]
}

# ================= 2. 猎手思维模型 =================
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
    """抓取 RSS 并进行简单清洗"""
    print(f"🕵️‍♂️ [猎手雷达] 正在扫描 {category} 频道...")
    combined_content = ""
    for url in RSS_SOURCES.get(category, []):
        try:
            feed = feedparser.parse(url)
            # 只取前 3 条，避免 Token 溢出
            for entry in feed.entries[:3]:
                title = getattr(entry, 'title', '无标题')
                link = getattr(entry, 'link', '无链接')
                summary = getattr(entry, 'summary', '')[:200] 
                combined_content += f"【标题】{title}\n【链接】{link}\n【摘要】{summary}\n\n"
        except Exception as e:
            print(f"⚠️ 抓取失败 {url}: {e}")
    return combined_content

def analyze_with_hunter_ai(content):
    """调用通义千问进行深度分析"""
    if not content: return "今日雷达未捕捉到有效信号。"
    
    print("🧠 [猎手大脑] 正在拆解商业逻辑...")
    try:
        dashscope.api_key = os.getenv("DASHSCOPE_API_KEY")
        response = dashscope.Generation.call(
            model=dashscope.Generation.Models.qwen_turbo, 
            messages=[{'role': 'system', 'content': HUNTER_SYSTEM_PROMPT},
                      {'role': 'user', 'content': f"今日情报汇总数据：\n{content}"}]
        )
        if response.status_code == HTTPStatus.OK:
            return response.output.text
        else:
            print(f"❌ AI分析失败: {response.code} - {response.message}")
            return "AI 暂时掉线。"
    except Exception as e:
        print(f"❌ 系统错误: {e}")
        return f"系统运行出错: {e}"

def upload_to_aliyun_drive(file_paths):
    """上传文件到阿里云盘 /晨间情报 文件夹"""
    print("☁️ [云端归档] 正在连接阿里云盘...")
    try:
        refresh_token = os.getenv("ALIYUN_REFRESH_TOKEN")
        if not refresh_token:
            print("❌ 未找到 ALIYUN_REFRESH_TOKEN，跳过上传。")
            return

        # 初始化 Aligo
        ali = Aligo(level=logging.INFO, refresh_token=refresh_token)
        
        # 获取或创建目标文件夹
        remote_folder = ali.get_folder_by_path('/晨间情报')
        if not remote_folder:
            ali.create_folder('/晨间情报')
            remote_folder = ali.get_folder_by_path('/晨间情报')

        # 批量上传
        for file_path in file_paths:
            if os.path.exists(file_path):
                print(f"   ⬆️ 正在上传: {os.path.basename(file_path)}")
                ali.upload_file(file_path, remote_folder.file_id)
        
        print("✅ 所有文件已备份至阿里云盘！")
    except Exception as e:
        print(f"❌ 上传失败 (不影响本地生成): {e}")

def cleanup_old_files(output_dir="output", days_to_keep=3):
    """清理 GitHub 本地超过 3 天的旧文件"""
    print("🧹 [扫地僧] 开始清理 GitHub 本地旧文件...")
    now = time.time()
    cutoff = now - (days_to_keep * 86400)
    
    if not os.path.exists(output_dir):
        return

    files = glob.glob(os.path.join(output_dir, "*"))
    for f in files:
        if os.path.basename(f).startswith("."): continue # 跳过隐藏文件
        
        # 检查文件修改时间
        if os.stat(f).st_mtime < cutoff:
            try:
                os.remove(f)
                print(f"   🗑️ 已删除过期文件: {os.path.basename(f)}")
            except Exception as e:
                print(f"   ❌ 删除失败: {e}")

# ================= 4. 主程序入口 =================

async def main():
    
    # 🟢 关键修改：强制使用北京时间 (UTC+8)
    beijing_time = datetime.utcnow() + timedelta(hours=8)
    today_str = beijing_time.strftime("%Y%m%d")
    
    print(f"📅 当前北京时间: {beijing_time.strftime('%Y-%m-%d %H:%M:%S')}")

    output_dir = "output"
    if not os.path.exists(output_dir): os.makedirs(output_dir)

    # 1. 抓取与分析
    print("🚀 晨间猎手任务启动...")
    signals = fetch_rss_intel("signals")
    shovels = fetch_rss_intel("shovels")
    macro = fetch_rss_intel("macro")
    full_intel = f"=== 焦虑信号 ===\n{signals}\n=== 掘金铲子 ===\n{shovels}\n=== 宏观风向 ===\n{macro}"
    
    report = analyze_with_hunter_ai(full_intel)
    
    # 2. 生成文件
    files_to_upload = []

    # [MD] Markdown 原文
    md_path = os.path.join(output_dir, f"briefing_{today_str}.md")
    with open(md_path, "w", encoding="utf-8") as f: f.write(report)
    files_to_upload.append(md_path)
    print(f"✅ MD生成完毕: {md_path}")

    # [MP3] 语音播报
    mp3_path = os.path.join(output_dir, f"briefing_{today_str}.mp3")
    tts_text = report[:1000] 
    communicate = edge_tts.Communicate(tts_text, "zh-CN-YunxiNeural")
    await communicate.save(mp3_path)
    files_to_upload.append(mp3_path)
    print(f"✅ MP3生成完毕: {mp3_path}")

    # [HTML] 手机适配版网页
    html_path = os.path.join(output_dir, f"briefing_{today_str}.html")
    html_content = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>晨间猎手内参 {today_str}</title>
        <style>
            body {{ font-family: -apple-system, sans-serif; padding: 20px; line-height: 1.6; max-width: 800px; margin: 0 auto; background: #f4f4f5; }}
            .card {{ background: white; padding: 20px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
            h1 {{ color: #1a1a1a; font-size: 1.5rem; }}
            audio {{ width: 100%; margin: 15px 0; }}
            pre {{ white-space: pre-wrap; word-wrap: break-word; font-size: 15px; color: #333; }}
        </style>
    </head>
    <body>
        <div class="card">
            <h1>🕵️‍♂️ 晨间猎手内参 ({today_str})</h1>
            <p>📅 {beijing_time.strftime('%Y-%m-%d')}</p>
            <audio controls src="briefing_{today_str}.mp3"></audio>
            <hr>
            <pre>{report}</pre>
        </div>
    </body>
    </html>
    """
    with open(html_path, "w", encoding="utf-8") as f: f.write(html_content)
    files_to_upload.append(html_path)
    print(f"✅ HTML生成完毕: {html_path}")

    # 3. ☁️ 云端归档
    upload_to_aliyun_drive(files_to_upload)

    # 4. 🧹 本地清理
    cleanup_old_files(output_dir, days_to_keep=3)

if __name__ == "__main__":
    asyncio.run(main())
