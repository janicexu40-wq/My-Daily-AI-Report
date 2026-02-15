"""
test_kimi.py — 阿里云 Key 有效性 & Kimi-K2.5 独立测试
=====================================================
用法：
    # 本地运行（需先设置环境变量）
    export DASHSCOPE_API_KEY=sk-xxxxxxxxxxxx
    python test_kimi.py

    # 或者直接写入 Key（仅本地测试，勿提交）
    # 把下面 YOUR_KEY_HERE 换成真实 Key
    python test_kimi.py --key YOUR_KEY_HERE

测试范围：
    1. Qwen3-Max  ← Generation 接口，验证基础连通性
    2. Kimi-K2.5  ← MultiModalConversation 接口，验证思考模式
    3. 输出字段检查 ← 打印完整 response 结构，方便定位空输出问题
"""

import os
import sys
import json
import argparse
from http import HTTPStatus

# ── 依赖检查 ─────────────────────────────────────────────
try:
    import dashscope
    from dashscope import Generation, MultiModalConversation
except ImportError:
    print("❌ 未安装 dashscope，请先运行：pip install dashscope")
    sys.exit(1)

# ── 参数解析 ─────────────────────────────────────────────
parser = argparse.ArgumentParser(description="测试阿里云 Dashscope Key 和 Kimi-K2.5")
parser.add_argument("--key", help="直接传入 API Key（可选，也可用环境变量）")
args = parser.parse_args()

API_KEY = args.key or os.getenv("DASHSCOPE_API_KEY")
if not API_KEY:
    print("❌ 未找到 API Key")
    print("   方式 1：export DASHSCOPE_API_KEY=sk-xxx && python test_kimi.py")
    print("   方式 2：python test_kimi.py --key sk-xxx")
    sys.exit(1)

dashscope.api_key = API_KEY
print(f"\n🔑 Key 前缀：{API_KEY[:8]}...{API_KEY[-4:]}")
print("=" * 55)


# ══════════════════════════════════════════════════════════
# 测试 1：Qwen3-Max（Generation 接口）
# ══════════════════════════════════════════════════════════
def test_qwen():
    print("\n【测试 1】Qwen3-Max — Generation 接口")
    print("-" * 40)
    try:
        response = Generation.call(
            model="qwen3-max",
            messages=[
                {"role": "user", "content": "用一句话介绍你自己。"}
            ]
        )

        print(f"  status_code : {response.status_code}")

        if response.status_code == HTTPStatus.OK:
            # 检查两条输出路径
            text_via_output = getattr(response.output, 'text', None)
            try:
                text_via_choices = response.output.choices[0].message.content
            except (AttributeError, IndexError, TypeError):
                text_via_choices = None

            print(f"  output.text              : {repr(text_via_output[:80]) if text_via_output else '⚠️ 空'}")
            print(f"  output.choices[0].content: {repr(str(text_via_choices)[:80]) if text_via_choices else '⚠️ 空'}")

            final = text_via_choices or text_via_output
            if final and final.strip():
                print(f"\n  ✅ Qwen3-Max 正常，有效输出路径：{'choices' if text_via_choices else 'output.text'}")
                print(f"  📝 内容：{final.strip()[:120]}")
            else:
                print("\n  ❌ Qwen3-Max 响应成功但两条路径均为空！")
                print(f"  🔍 完整 output 结构：{response.output}")
        else:
            print(f"  ❌ 调用失败：{response.message}")
            print(f"  🔍 错误码：{response.status_code}")

    except Exception as e:
        print(f"  ❌ 异常：{e}")


# ══════════════════════════════════════════════════════════
# 测试 2：Kimi-K2.5（MultiModalConversation 接口）
# ══════════════════════════════════════════════════════════
def test_kimi():
    print("\n【测试 2】Kimi-K2.5 — MultiModalConversation + enable_thinking")
    print("-" * 40)
    print("  ⏳ 思考模式耗时较长，请耐心等待（通常 15-40 秒）...")

    try:
        response = MultiModalConversation.call(
            model="kimi-k2.5",
            messages=[
                {"role": "system", "content": "你是一个简洁的助手。"},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "用一句话介绍你自己，说明你的模型名称。"}
                    ]
                }
            ],
            extra_body={"enable_thinking": True}
        )

        print(f"  status_code : {response.status_code}")

        if response.status_code == HTTPStatus.OK:
            raw_content = response.output.choices[0].message.content
            print(f"  content 类型 : {type(raw_content).__name__}")

            # content 可能是字符串或列表（含 thinking block）
            if isinstance(raw_content, list):
                print(f"  content 块数 : {len(raw_content)} 个")
                for i, block in enumerate(raw_content):
                    btype = block.get("type", "?") if isinstance(block, dict) else "?"
                    btext = block.get("text", "") if isinstance(block, dict) else str(block)
                    print(f"    block[{i}] type={btype}  text={repr(btext[:60])}")

                # 只取 type=text 的块（排除 thinking）
                final_text = "\n".join(
                    b.get("text", "") for b in raw_content
                    if isinstance(b, dict) and b.get("type") == "text"
                )
            else:
                final_text = raw_content or ""

            if final_text and final_text.strip():
                print(f"\n  ✅ Kimi-K2.5 正常")
                print(f"  📝 内容：{final_text.strip()[:200]}")
            else:
                print("\n  ❌ Kimi-K2.5 响应成功但输出为空！")
                print(f"  🔍 raw_content = {repr(raw_content)}")

        else:
            print(f"  ❌ 调用失败：{response.message}")
            print(f"  🔍 错误码：{response.status_code}")
            if "region" in str(response.message).lower() or "area" in str(response.message).lower():
                print("  ⚠️  地域限制：kimi-k2.5 仅支持中国大陆（北京）地域的 API Key")

    except Exception as e:
        print(f"  ❌ 异常：{e}")
        err = str(e).lower()
        if "region" in err or "not support" in err or "area" in err:
            print("  ⚠️  地域限制：kimi-k2.5 仅支持中国大陆（北京）地域的 API Key")
        if "multimodal" in err or "not found" in err:
            print("  ⚠️  接口问题：请确认 dashscope 版本 >= 1.14，运行 pip install -U dashscope")


# ══════════════════════════════════════════════════════════
# 测试 3：Key 基本信息检查（余额/配额 - 仅供参考）
# ══════════════════════════════════════════════════════════
def test_key_info():
    print("\n【测试 3】Key 连通性快速验证（最小调用）")
    print("-" * 40)
    try:
        response = Generation.call(
            model="qwen-turbo",   # 最便宜的模型，用于验证 Key 是否有效
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=5
        )
        if response.status_code == HTTPStatus.OK:
            print("  ✅ Key 有效，可正常访问阿里云百炼平台")
        elif response.status_code == 401:
            print("  ❌ Key 无效或已过期（401 Unauthorized）")
        elif response.status_code == 403:
            print("  ❌ Key 无权限，请检查是否开通了对应模型（403 Forbidden）")
        else:
            print(f"  ⚠️  返回状态：{response.status_code} — {response.message}")
    except Exception as e:
        print(f"  ❌ 连接失败：{e}")


# ══════════════════════════════════════════════════════════
# 主入口
# ══════════════════════════════════════════════════════════
if __name__ == "__main__":
    test_key_info()   # 先验 Key 连通性
    test_qwen()       # 再测 Qwen（输出路径诊断）
    test_kimi()       # 最后测 Kimi（最慢，放最后）

    print("\n" + "=" * 55)
    print("测试完成。如果 Kimi-K2.5 报地域错误，需要：")
    print("  1. 登录 https://bailian.console.aliyun.com/")
    print("  2. 确认 API Key 所属地域为「华北2（北京）」")
    print("  3. 如果是「华东」等其他地域的 Key，需重新创建")
    print("=" * 55)
