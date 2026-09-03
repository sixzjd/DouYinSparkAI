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
    "1. 最高优先级：严格模仿提供的【我平时说话风格】——我的语气、用词、口头禅、情绪浓度是什么样，你就什么样\n"
    "2. 不要自行添加俏皮、可爱、撒娇、网络梗或夸张表达；我平时说得平淡你就回得平淡，宁可朴素也绝不装活泼\n"
    "3. 综合最近几条消息的语境来回复，不要只盯着最后一句；顺着聊天走向自然接话\n"
    "4. 字数控制在 5-30 字，简短自然，一句话说完，整体气质贴近样本\n"
    "5. 不要加引号，不要解释你在做什么，不要写表情符号的文字描述\n"
    "6. 如果对方分享了视频，就视频内容用我的语气简短评论或表达兴趣\n"
    "7. 每次内容可以不一样，但都必须像我本人会说的话，不要重复套话\n"
    "8. 如果最后一条是我之前发的（不是今天），说明需要主动找话题续火花——"
    "可以接着之前的话题追问、分享近况、或随意问候，像真人隔了一天再开口那样自然\n"
    "9. 聊天记录里【我】之前说的话可能是自动发出的，只用来理解语境，绝不作为风格或用词的依据；"
    "风格只以【我平时说话风格】为准\n"
    "10. 绝对禁止复读：最近聊天里已经出现过的梗、词、句式（不管是我说的还是对方说的）一律不要再用。"
    "同一个词已经被来回说过两三次还接着说，会显得像复读机，非常惹人烦\n"
    "11. 察言观色：如果对方在表达不满、质疑、不耐烦（比如反问、抱怨某事被反复说），"
    "立刻收起玩笑和抬杠，换成真诚、朴实、认错的口吻回应，一句话说到点子上"
)


def generate_reply(context: str, friend_name: str, style_examples: str = "",
                   style_profile: str = "") -> str:
    """
    根据上下文生成回复
    :param context: 最近的对话流（双方消息，带 我:/对方: 标签）
    :param friend_name: 好友昵称
    :param style_examples: 用户本人最近说的话（风格样本，供 AI 模仿）
    :param style_profile: 预学习的风格摘要（有值时优先使用，省 token）
    :return: 生成的回复文本
    """
    config = get_config()
    api_key = config["ai_api_key"]
    provider = config["ai_provider"]

    if not api_key:
        logger.warning("未配置 AI_API_KEY，使用默认续火花消息")
        return _fallback_message()

    # 优先使用预学习的风格摘要，没有则用现场提取的样本
    style_section = style_profile if style_profile else style_examples

    user_prompt = (
        f"【我平时说话风格】（请模仿）\n{style_section}\n\n"
        f"【最近聊天记录】\n{context}\n\n"
        f"请模仿我的说话风格，根据最近几条消息的语境，"
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
        # 思考型模型（如 deepseek-v4-flash）会先推理再输出，推理也计入 token；
        # 上限太小会被推理占满导致正文为空（finish_reason=length），故放宽到 2000
        max_tokens=2000,
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
        # 同 openai 路径：给思考型模型留足 推理+正文 的 token 空间
        max_tokens=2000,
        temperature=0.9,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": user_prompt},
        ],
    )

    return response.content[0].text.strip()


def _fallback_message() -> str:
    """AI 不可用时的兜底消息（尽量朴素，避免发用户绝不会说的套路话）"""
    import random
    messages = [
        "在吗",
        "最近咋样",
        "在干嘛呢",
        "好久没聊了",
        "哈喽",
        "冒个泡",
        "今天忙不",
    ]
    return random.choice(messages)
