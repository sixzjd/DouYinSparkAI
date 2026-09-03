"""
风格预学习脚本：
1. 登录创作者中心，逐个打开目标好友聊天
2. 收集"我"的历史消息（尽量多）
3. 用 AI 总结成一段精简的风格描述
4. 输出到 logs/style_profile.txt

由 learn_style.yml 工作流调用，结果写入仓库变量 STYLE_PROFILE，
之后每日续火花时直接使用这段描述，不再每次传原始样本，省 token。
"""

import os
import sys
import json
import time

from playwright.sync_api import sync_playwright
from utils.config import get_config, get_tasks
from utils.logger import setup_logger
from core.chat import (
    navigate_to_chat,
    is_logged_in,
    find_and_click_friend,
    read_recent_messages,
    UserIdCollector,
    SCROLL_CONTAINER_SELECTORS,
    MESSAGE_ITEM_SELECTORS,
    _try_locator,
)

logger = setup_logger()


def collect_my_messages(page, config, targets, id_collector=None):
    """遍历所有目标好友，收集"我"发的消息文本"""
    all_my_msgs = []

    for target in targets:
        logger.info(f"── 收集好友 {target} 的聊天记录 ──")
        if not find_and_click_friend(page, target, config, id_collector):
            logger.warning(f"好友 {target} 未找到，跳过")
            continue

        # 先向上滚动加载更多历史消息
        _scroll_up_for_history(page)

        messages = read_recent_messages(page, config)
        my_msgs = [
            m["text"] for m in messages
            if m["sender"] == "me" and not m["is_video"] and m["text"]
        ]
        all_my_msgs.extend(my_msgs)
        logger.info(f"从 {target} 收集到 {len(my_msgs)} 条我的消息")
        time.sleep(1)

    return all_my_msgs


def _scroll_up_for_history(page, scrolls=5):
    """在聊天区域向上滚动，加载更多历史消息"""
    # 聊天消息区域的滚动容器（不同于好友列表的）
    chat_scroll_selectors = [
        'xpath=//div[contains(@class, "box-content")]/..',
        'xpath=//div[contains(@class, "messageMessageList")]',
        '[class*="box-content"]',
    ]
    scroll_el = _try_locator(page, chat_scroll_selectors, timeout=3000)
    if not scroll_el:
        logger.debug("未找到聊天滚动容器，使用已有消息")
        return

    handle = scroll_el.element_handle()
    for _ in range(scrolls):
        page.evaluate("(el) => el.scrollTop -= 800", handle)
        time.sleep(0.5)
    # 滚回底部
    page.evaluate("(el) => el.scrollTop = el.scrollHeight", handle)
    time.sleep(1)


def summarize_style(my_msgs, config):
    """用 AI 将原始消息总结为精简的风格描述"""
    if not my_msgs:
        return ""

    # 去重 + 最多取 50 条（够 AI 分析即可）
    unique_msgs = list(dict.fromkeys(my_msgs))[-50:]

    from openai import OpenAI
    client = OpenAI(
        api_key=config["ai_api_key"],
        base_url=config["ai_base_url"],
    )

    prompt = (
        "下面是我在抖音私信里发给不同好友的消息样本。"
        "请分析我的说话风格，用中文写一段 100 字以内的风格描述，"
        "涵盖：语气（平淡/热情/幽默等）、常用词/口头禅、句子长度偏好、"
        "情绪表达方式、会不会用网络梗/表情。"
        "只输出风格描述本身，不要加标题或前缀。\n\n"
        f"【消息样本】\n" + "\n".join(unique_msgs)
    )

    try:
        response = client.chat.completions.create(
            model=config["ai_model"],
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
            temperature=0.3,
        )
        if response.choices and response.choices[0].message.content:
            return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"AI 风格总结失败: {e}")

    # 兜底：直接拼接原始样本（截断）
    return "\n".join(unique_msgs[:20])


def main():
    config = get_config()
    tasks = get_tasks()

    if not tasks:
        logger.error("未找到有效任务（检查 TASKS / COOKIES_* 环境变量）")
        sys.exit(1)

    if not config["ai_api_key"]:
        logger.error("未配置 AI_API_KEY，无法进行风格学习")
        sys.exit(1)

    all_msgs = []  # 跨账号累计，避免只拿到最后一个账号 / 全部跳过时 NameError

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=config["headless"])

        for user in tasks:
            logger.info(f"═══ 用户: {user['username']} ({user['unique_id']}) ═══")

            # 创建 context（注入登录态）
            if user["storage_state"]:
                context = browser.new_context(storage_state=user["storage_state"])
            else:
                context = browser.new_context()
                context.add_cookies(user["cookies"])

            page = context.new_page()

            # short_id 模式：注册响应拦截
            id_collector = None
            if config["match_mode"] == "short_id":
                id_collector = UserIdCollector()
                page.on("response", id_collector.on_response)

            navigate_to_chat(page, user["cookies"], config,
                             has_storage_state=bool(user["storage_state"]))

            if not is_logged_in(page):
                logger.error("登录态无效，跳过")
                context.close()
                continue

            # 收集消息
            user_msgs = collect_my_messages(
                page, config, user["targets"], id_collector
            )
            all_msgs.extend(user_msgs)
            logger.info(f"共收集到 {len(user_msgs)} 条我的消息")

            context.close()

        browser.close()

    if not all_msgs:
        logger.error("未收集到任何消息，无法生成风格描述")
        sys.exit(1)

    # AI 总结
    profile = summarize_style(all_msgs, config)
    if not profile:
        logger.error("风格总结为空")
        sys.exit(1)

    # 输出
    os.makedirs("logs", exist_ok=True)
    with open("logs/style_profile.txt", "w", encoding="utf-8") as f:
        f.write(profile)

    logger.info(f"风格学习完成，结果已保存到 logs/style_profile.txt")
    logger.info(f"内容: {profile}")


if __name__ == "__main__":
    main()
