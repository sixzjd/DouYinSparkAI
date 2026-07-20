"""
AI 回复生成 - 使用 OpenAI 兼容 API
支持 DeepSeek / Moonshot / 通义千问 / 本地 Ollama 等任何兼容接口
"""

from openai import OpenAI
from utils.config import get_config
from utils.logger import setup_logger

logger = setup_logger()


def generate_reply(context: str, friend_name: str) -> str:
    """
    根据上下文生成回复
    :param context: 对方最近发的消息内容（含视频标题等）
    :param friend_name: 好友昵称
    :return: 生成的回复文本
    """
    config = get_config()
    api_key = config["ai_api_key"]

    if not api_key:
        logger.warning("未配置 AI_API_KEY，使用默认续火花消息")
        return _fallback_message(friend_name)

    try:
        client = OpenAI(
            api_key=api_key,
            base_url=config["ai_base_url"],
        )

        system_prompt = (
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

        user_prompt = f"好友「{friend_name}」最近发给我的消息：\n{context}\n\n请生成一条自然的回复："

        response = client.chat.completions.create(
            model=config["ai_model"],
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=100,
            temperature=0.9,
        )

        reply = response.choices[0].message.content.strip()
        # 去掉可能的引号包裹
        reply = reply.strip("\"'\"\"''")
        logger.info(f"AI 生成回复: {reply}")
        return reply

    except Exception as e:
        logger.error(f"AI 生成失败: {e}，使用默认消息")
        return _fallback_message(friend_name)


def _fallback_message(friend_name: str) -> str:
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
    ]
    return random.choice(messages)
