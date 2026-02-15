"""
test_kimi_v2.py — 阿里云 Key 有效性 & Kimi-K2.5 兼容性修复版
=====================================================
修复说明：
    针对 Kimi 返回的 content 结构 [{'text': '...'}] 进行了兼容，
    不再强制检查 'type': 'text' 字段，防止误报“输出为空”。
"""

import os
import sys
import json
from http import HTTPStatus

def run_test():
    # ── 1. 基础环境检查 ──────────────────────────────────────────
    try:
        import dashscope
        from dashscope import MultiModalConversation
    except ImportError:
        print("❌ 错误：未安装 dashscope。请确保 workflow 中包含 'pip install dashscope'")
        sys.exit(1)

    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        print("❌ 错误：环境变量 DASHSCOPE_API_KEY 未设置")
        sys.exit(1)
    
    dashscope.api_key = api_key
    print(f"🔑 当前 Key: {api_key[:6]}******{api_key[-4:]}")

    # ── 2. 调用 Kimi-K2.5 ───────────────────────────────────────
    print("\n🚀 正在发起 Kimi-K2.5 请求 (enable_thinking=True)...")
    print("⏳ 请耐心等待 (通常需 10-30 秒)...")

    try:
        response = MultiModalConversation.call(
            model="kimi-k2.5",
            messages=[
                {"role": "system", "content": "你是一个测试助手。"},
                {"role": "user", "content": "请回复'测试成功'这四个字，不要多余内容。"}
            ],
            extra_body={"enable_thinking": True}
        )
    except Exception as e:
        print(f"\n❌ 请求发生异常: {e}")
        return

    # ── 3. 结果解析 (修复版逻辑) ────────────────────────────────
    print(f"\n📡 响应状态码: {response.status_code}")
    
    if response.status_code == HTTPStatus.OK:
        # 获取原始内容
        raw_content = response.output.choices[0].message.content
        print(f"🔍 原始返回结构 (类型: {type(raw_content).__name__}):")
        print(json.dumps(raw_content, ensure_ascii=False, indent=2))

        # 提取文本的核心逻辑
        extracted_text = ""
        
        if isinstance(raw_content, str):
            extracted_text = raw_content
        elif isinstance(raw_content, list):
            for i, block in enumerate(raw_content):
                # 兼容情况 A: block 是字典 (标准结构 或 缺省 type 结构)
                if isinstance(block, dict):
                    # 优先取 text，不管有没有 type 字段
                    text_part = block.get("text", "")
                    if text_part:
                        extracted_text += text_part
                    # 如果是思考过程 (thinking)，通常 text 为空或在其他字段，这里主要抓最终结果
                    
                # 兼容情况 B: block 居然直接是字符串 (罕见但防御性处理)
                elif isinstance(block, str):
                    extracted_text += block
        
        # 最终判定
        if extracted_text.strip():
            print("\n✅ [测试通过] Kimi 正常工作！")
            print(f"📝 提取到的回复: {extracted_text}")
        else:
            print("\n⚠️ [警告] 响应成功但提取内容为空，请检查上方原始结构。")
    else:
        print(f"\n❌ 调用失败 (Code: {response.status_code})")
        print(f"   Message: {response.message}")
        if "Region" in str(response.message):
            print("💡 提示：请检查 Key 是否为北京地域 (cn-beijing)。")

if __name__ == "__main__":
    run_test()
