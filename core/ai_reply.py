"""
AI 回复生成 - 支持多种 API 格式
- openai: OpenAI 兼容格式（DeepSeek / Moonshot / 通义千问 / 中转站 / Ollama 等）
- anthropic: Anthropic Claude 系列
用户只需配置 AI_PROVIDER + AI_BASE_URL + AI_API_KEY + AI_MODEL 即可
"""

from utils.config import get_config
from utils.logger import setup_logger

logger = setup_logger()

SYSTEM_PROMPT = (
    "你要扮演用户本人，给抖音好友回一条消息来续火花（保持连续互动天数）。\n"
    "要求：\n"
    "1. 仔细学习提供的【我平时说话风格】，模仿我的语气、用词和口头禅来回复\n"
    "2. 必须接住对方最后一句话的话题，顺着聊，不要答非所问、不要硬转话题\n"
    "3. 口语化、随意，像熟人之间日常闲聊，可以俏皮一点，但不要油腻、不要肉麻\n"
    "4. 字数控制在 5-30 字，简短自然，一句话说完\n"
    "5. 不要加引号，不要解释你在做什么，不要写表情符号的文字描述\n"
    "6. 如果对方分享了视频，就视频内容简短评论或表达兴趣\n"
    "7. 每次内容要不一样，有创意，不要重复套话"
)


def generate_reply(context: str, friend_name: str, style_examples: str = "") -> str:
    """
    根据上下文生成回复
    :param context: 最近的对话流（双方消息，带 我:/对方: 标签）
    :param friend_name: 好友昵称
    :param style_examples: 用户本人最近说的话（风格样本，供 AI 模仿）
    :return: 生成的回复文本
    """
    config = get_config()
    api_key = config["ai_api_key"]
    provider = config["ai_provider"]

    if not api_key:
        logger.warning("未配置 AI_API_KEY，使用默认续火花消息")
        return _fallback_message()

    user_prompt = (
        f"【我平时说话风格】（请模仿）\n{style_examples}\n\n"
        f"【最近聊天记录】\n{context}\n\n"
        f"请模仿我的说话风格，接住对方最后一句话，"
        f"生成一条我要发给好友「{friend_name}」的自然回复："
    )

    try:
        if provider == "anthropic":
            reply = _call_anthropic(config, user_prompt)
        else:
            # 默认走 openai 兼容格式（含中转站）
            reply = _call_openai_compatible(config, user_prompt)

        # 去掉可能的引号包裹
        reply = reply.strip("\"'\"\"''\n")
        logger.info(f"AI 生成回复 [{provider}]: {reply}")
        return reply if reply else _fallback_message()

    except Exception as e:
        logger.error(f"AI 生成失败 [{provider}]: {e}，使用默认消息")
        return _fallback_message()


def _call_openai_compatible(config: dict, user_prompt: str) -> str:
    """
    OpenAI 兼容格式调用
    适用于: OpenAI / DeepSeek / Moonshot / 通义千问 / 各类中转站 / Ollama
    只要对方提供 /v1/chat/completions 接口就能用
    """
    from openai import OpenAI

    client = OpenAI(
        api_key=config["ai_api_key"],
        base_url=config["ai_base_url"],
    )

    response = client.chat.completions.create(
        model=config["ai_model"],
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=100,
        temperature=0.9,
    )

    # 诊断日志：排查空回复问题
    if not response.choices:
        logger.warning(f"API 返回空 choices，model={config['ai_model']}，原始响应: {response}")
        return ""
    choice = response.choices[0]
    content = choice.message.content
    if not content:
        logger.warning(
            f"API 返回空内容，model={config['ai_model']}，"
            f"finish_reason={choice.finish_reason}，content={content!r}"
        )
        return ""
    return content.strip()


def _call_anthropic(config: dict, user_prompt: str) -> str:
    """
    Anthropic Claude API 调用
    适用于: Anthropic 官方 / 支持 Anthropic 格式的中转站
    """
    import anthropic

    client = anthropic.Anthropic(
        api_key=config["ai_api_key"],
        base_url=config["ai_base_url"] or None,  # None 则用官方默认地址
    )

    response = client.messages.create(
        model=config["ai_model"],
        max_tokens=100,
        temperature=0.9,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": user_prompt},
        ],
    )

    return response.content[0].text.strip()


def _fallback_message() -> str:
    """AI 不可用时的兜底消息"""
    import random
    messages = [
        "今天也要开心呀",
        "在干嘛呢",
        "火花不能断！",
        "今日份打卡",
        "嘿 还活着吗",
        "续个火",
        "又是新的一天",
        "想你了 冒个泡",
        "今天天气咋样",
    ]
    return random.choice(messages)
