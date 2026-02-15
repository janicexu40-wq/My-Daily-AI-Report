import os
import asyncio
import feedparser
import edge_tts
from datetime import datetime
from http import HTTPStatus
import dashscope
import glob
from aligo import Aligo # 📦 新增：阿里云盘工具

# ================= 1. 猎手雷达设置 =================
RSS_SOURCES = {
    "signals": [
        "https://www.v2ex.com/index.xml", 
        "https://www.reddit.com/r/SaaS/new/.rss",
    ],
    "shovels": [
        "https://news.ycombinator.com/rss",
        "https://stratechery.com/feed/",
    ],
    "macro": [
        "https://feed.36kr.com/feed",
    ]
}

# ================= 2. 猎手思维模型 =================
HUNTER_SYSTEM_PROMPT = """
你不再是新闻播报员，你是“晨间商业猎手”。你的任务是从信息中嗅出“钱味”。
请对输入的内容进行【深度商业拆解】，严格遵循以下框架：
... (保持你之前的 Prompt 内容不变) ...
"""

# ================= 3. 核心功能函数 =================

def fetch_rss_intel(category):
    # ... (保持原有的抓取代码不变) ...
    print(f"🕵️‍♂️ [猎手雷达] 正在扫描 {category} 频道...")
    combined_content = ""
    for url in RSS_SOURCES.get(category, []):
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:3]:
                title = getattr(entry, 'title', '无标题')
                link = getattr(entry, 'link', '无链接')
                summary = getattr(entry, 'summary', '')[:200] 
                combined_content += f"【标题】{title}\n【链接】{link}\n【摘要】{summary}\n\n"
        except Exception as e:
            print(f"⚠️ 抓取失败 {url}: {e}")
    return combined_content

def analyze_with_hunter_ai(content):
    # ... (保持原有的 AI 分析代码不变) ...
    if not content: return "无有效信号。"
    try:
        dashscope.api_key = os.getenv("DASHSCOPE_API_KEY")
        response = dashscope.Generation.call(
            model=dashscope.Generation.Models.qwen_turbo, 
            messages=[{'role': 'system', 'content': HUNTER_SYSTEM_PROMPT},
                      {'role': 'user', 'content': content}]
        )
        if response.status_code == HTTPStatus.OK: return response.output.text
        else: return "AI 暂时掉线。"
    except Exception as e: return f"错误: {e}"

# 🔥 新增功能：上传所有文件到阿里云盘
def upload_to_aliyun_drive(file_paths):
    print("☁️ [云端归档] 正在连接阿里云盘...")
    try:
        # 使用环境变量中的 Refresh Token 登录
        refresh_token = os.getenv("ALIYUN_REFRESH_TOKEN")
        if not refresh_token:
            print("❌ 未找到 ALIYUN_REFRESH_TOKEN，跳过上传。")
            return

        ali = Aligo(level=logging.INFO, refresh_token=refresh_token)
        
        # 目标文件夹 (如果不存在会自动创建)
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

# 🧹 扫地僧：只保留最近 3 天
def cleanup_old_files(output_dir="output", days_to_keep=3):
    print("🧹 [扫地僧] 开始清理 GitHub 本地旧文件...")
    now = time.time()
    cutoff = now - (days_to_keep * 86400)
    
    files = glob.glob(os.path.join(output_dir, "*"))
    for f in files:
        if os.path.basename(f).startswith("."): continue # 跳过隐藏文件
        
        # 如果文件的修改时间早于截止时间，则删除
        if os.stat(f).st_mtime < cutoff:
            try:
                os.remove(f)
                print(f"   🗑️ 已从仓库移除过期文件: {os.path.basename(f)}")
            except Exception as e:
                print(f"   ❌ 删除失败: {e}")

# ================= 4. 主程序入口 =================

async def main():
    today_str = datetime.now().strftime("%Y%m%d")
    output_dir = "output"
    if not os.path.exists(output_dir): os.makedirs(output_dir)

    # 1. 抓取与分析
    print("🚀 晨间猎手任务启动...")
    signals = fetch_rss_intel("signals")
    shovels = fetch_rss_intel("shovels")
    macro = fetch_rss_intel("macro")
    full_intel = f"=== 焦虑信号 ===\n{signals}\n=== 掘金铲子 ===\n{shovels}\n=== 宏观风向 ===\n{macro}"
    
    report = analyze_with_hunter_ai(full_intel)
    
    # 2. 生成所有文件 (MD, MP3, HTML)
    files_to_upload = []

    # MD
    md_path = os.path.join(output_dir, f"briefing_{today_str}.md")
    with open(md_path, "w", encoding="utf-8") as f: f.write(report)
    files_to_upload.append(md_path)

    # MP3
    mp3_path = os.path.join(output_dir, f"briefing_{today_str}.mp3")
    tts_text = report[:1000] # 截取前1000字播报
    communicate = edge_tts.Communicate(tts_text, "zh-CN-YunxiNeural")
    await communicate.save(mp3_path)
    files_to_upload.append(mp3_path)

    # HTML
    html_path = os.path.join(output_dir, f"briefing_{today_str}.html")
    html_content = f"""<html><body><h1>{today_str}</h1><audio controls src="briefing_{today_str}.mp3"></audio><pre>{report}</pre></body></html>"""
    with open(html_path, "w", encoding="utf-8") as f: f.write(html_content)
    files_to_upload.append(html_path)

    # 3. ☁️ 先备份：上传所有文件到阿里云盘 (关键步骤！)
    # 这一步确保了无论 GitHub 怎么删，云盘里永远有一份全量的
    upload_to_aliyun_drive(files_to_upload)

    # 4. 🧹 后清理：删除 GitHub 3天前的旧文件
    cleanup_old_files(output_dir, days_to_keep=3)

if __name__ == "__main__":
    import logging
    asyncio.run(main())
