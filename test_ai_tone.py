"""
AI 语气测试 —— 直接调用 generate_reply 查看实际生成效果（不发送任何消息）
用途：调优提示词时验证 ①语气是否贴近本人、②是否还会返回空内容。
在 CI 里通过 ai_test.yml 手动触发运行（需要 AI_* 环境变量）。
"""

from core.ai_reply import generate_reply

# 模拟"我平时说话风格"样本：偏平淡、简短、不卖萌
STYLE = "嗯\n还行\n哈哈哈哈\n行\n知道了\n明天再说\n可以"

# 几组典型场景：(场景说明, 对话上下文)
CASES = [
    ("对方调侃", "对方: 还是那种不用打开抖音就能回啊"),
    ("对方附和", "我: 那还不是你躲得快\n对方: 哈哈哈哈好吧"),
    ("对方倾诉", "我: 今天咋样\n对方: 今天好累啊"),
    ("对方发视频", "对方: [分享了一个视频: 搞笑猫咪合集]"),
]


def main():
    print("=" * 50)
    print("  AI 语气测试（仅生成，不发送）")
    print("=" * 50)
    for label, ctx in CASES:
        reply = generate_reply(ctx, "测试好友", style_examples=STYLE)
        empty = "  <- 空回复!" if not reply.strip() else ""
        print(f"[{label}] -> {reply!r}{empty}")
    print("=" * 50)


if __name__ == "__main__":
    main()
