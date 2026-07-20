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
    "你是一个帮用户维护抖音好友关系的助手。"
    "用户需要每天给好友发消息来续火花（保持连续互动天数）。\n"
    "规则：\n"
    "1. 回复要自然、口语化，像朋友之间随便聊天，不要太正式\n"
    "2. 如果对方分享了视频，根据视频内容简短评论或表达兴趣\n"
    "3. 如果没有具体内容可回复，就发一条轻松的日常问候或闲聊\n"
    "4. 字数控制在 5-30 字，简短自然\n"
    "5. 不要加引号、不要加表情符号描述、不要解释你在做什么\n"
    "6. 每次内容要不一样，有创意"
)


def generate_reply(context: str, friend_name: str) -> str:
    """
    根据上下文生成回复
    :param context: 对方最近发的消息内容（含视频标题等）
    :param friend_name: 好友昵称
    :return: 生成的回复文本
    """
    config = get_config()
    api_key = config["ai_api_key"]
    provider = config["ai_provider"]

    if not api_key:
        logger.warning("未配置 AI_API_KEY，使用默认续火花消息")
        return _fallback_message()

    user_prompt = f"好友「{friend_name}」最近发给我的消息：\n{context}\n\n请生成一条自然的回复："

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

    return response.choices[0].message.content.strip()


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
