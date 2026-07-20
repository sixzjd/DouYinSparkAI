"""
核心聊天逻辑：
1. 打开创作者中心私信页面
2. 找到目标好友
3. 检查今天是否已经发过消息（已发则跳过）
4. 读取对方最近消息（含视频标题）
5. AI 生成回复并发送
"""

import time
import traceback
from datetime import date

from playwright.sync_api import Page, BrowserContext
from utils.config import get_config
from utils.logger import setup_logger
from core.ai_reply import generate_reply

logger = setup_logger()

# ─── 多版本 DOM 选择器（抖音 A/B 测试导致不同账号页面结构不同）───

# 好友列表容器（创作者中心版本）
FRIEND_LIST_SELECTORS = [
    'xpath=//*[@id="sub-app"]/div/div/div[1]/div[2]',  # 好友 tab
]

# 好友列表项
FRIEND_ITEM_SELECTORS = [
    'xpath=//*[@id="sub-app"]/div/div[1]/div[2]/div[2]//div[contains(@class, "semi-list-item-body")]',
    'xpath=//div[contains(@class, "conversation-item")]//pre',
    'xpath=//div[@data-e2e="conversation-item"]',
]

# 聊天输入框
CHAT_INPUT_SELECTORS = [
    "xpath=//div[contains(@class, 'chat-input-')]",
    "xpath=//div[@contenteditable='true']",
    "xpath=//div[contains(@class, 'messageMsgInput')]",
]

# 消息列表容器
MESSAGE_LIST_SELECTORS = [
    'xpath=//div[contains(@class, "messageMessageList")]//div[@data-e2e="msg-item-content"]',
    'xpath=//div[@id="messageContent"]//div[contains(@style, "justify-content")]',
    'xpath=//div[contains(@class, "chat-message-list")]//div[contains(@class, "msg-item")]',
]

# 滚动容器
SCROLL_CONTAINER_SELECTORS = [
    'xpath=//*[@id="sub-app"]/div/div[1]/div[2]/div[2]/div/div/div[3]/div/div/div/ul/div',
    'xpath=//div[contains(@class, "semi-list")]//div[contains(@class, "virtual-list")]',
]


def _find_element(page: Page, selectors: list[str], timeout: int = 5000):
    """按优先级尝试多个选择器，返回第一个找到的 locator"""
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            loc.wait_for(timeout=timeout)
            return loc
        except Exception:
            continue
    return None


def _find_all_elements(page: Page, selectors: list[str], timeout: int = 5000):
    """按优先级尝试多个选择器，返回第一个有结果的列表"""
    for sel in selectors:
        try:
            page.locator(sel).first.wait_for(timeout=timeout)
            return page.locator(sel).all()
        except Exception:
            continue
    return []


def navigate_to_chat(page: Page, cookies: list[dict], config: dict):
    """导航到创作者中心私信页面"""
    timeout = config["browser_timeout"]

    # 先访问主页注入 cookie
    page.goto("https://creator.douyin.com/", timeout=timeout)
    page.context.add_cookies(cookies)

    # 导航到私信页面
    page.goto(
        "https://creator.douyin.com/creator-micro/data/following/chat",
        timeout=timeout,
    )
    time.sleep(3)  # 等待页面渲染


def find_and_click_friend(page: Page, friend_name: str, config: dict) -> bool:
    """在好友列表中找到目标好友并点击"""
    # 点击好友 tab
    friend_tab = _find_element(page, FRIEND_LIST_SELECTORS, timeout=10000)
    if friend_tab:
        friend_tab.click()
        time.sleep(2)

    # 滚动查找好友
    max_scrolls = 30
    for i in range(max_scrolls):
        items = _find_all_elements(page, FRIEND_ITEM_SELECTORS, timeout=5000)

        for item in items:
            try:
                text = item.inner_text().strip()
                # 好友名可能带备注、时间等，取第一行匹配
                first_line = text.split("\n")[0].strip()
                if friend_name in first_line or first_line in friend_name:
                    item.click()
                    logger.info(f"找到好友: {friend_name}")
                    time.sleep(2)
                    return True
            except Exception:
                continue

        # 滚动加载更多
        scroll_container = _find_element(page, SCROLL_CONTAINER_SELECTORS, timeout=2000)
        if scroll_container:
            el = scroll_container.element_handle()
            before = page.evaluate("(el) => el.scrollTop", el)
            page.evaluate("(el) => el.scrollTop += 600", el)
            time.sleep(1.5)
            after = page.evaluate("(el) => el.scrollTop", el)
            if before == after:
                break  # 到底了
        else:
            break

    logger.warning(f"未找到好友: {friend_name}")
    return False


def read_recent_messages(page: Page, config: dict) -> list[dict]:
    """
    读取当前聊天窗口的最近消息
    返回: [{"sender": "me"/"friend", "text": "...", "is_video": bool, "video_title": "..."}]
    """
    messages = []
    time.sleep(1)

    # 尝试获取消息列表
    msg_items = _find_all_elements(page, MESSAGE_LIST_SELECTORS, timeout=8000)

    if not msg_items:
        logger.warning("未找到消息列表元素，尝试通用提取")
        # 兜底：尝试提取页面中所有可见文本块
        return messages

    for item in msg_items[-10:]:  # 只看最近 10 条
        try:
            text = item.inner_text().strip()
            if not text:
                continue

            # 判断是否是视频消息（通常有视频标题或特定标记）
            is_video = False
            video_title = ""

            # 视频卡片通常包含标题文字，且可能有 "视频" 标记
            video_indicators = item.locator(
                "xpath=.//*[contains(@class, 'video') or contains(@class, 'card')]"
            )
            if video_indicators.count() > 0:
                is_video = True
                video_title = text  # 卡片上的文字通常就是视频标题

            # 判断发送者（靠对齐方向或特定 class）
            item_class = item.get_attribute("class") or ""
            parent_class = ""
            try:
                parent_class = item.locator("xpath=..").get_attribute("class") or ""
            except Exception:
                pass

            is_self = any(
                kw in (item_class + parent_class).lower()
                for kw in ["self", "right", "mine", "sender"]
            )

            messages.append({
                "sender": "me" if is_self else "friend",
                "text": text,
                "is_video": is_video,
                "video_title": video_title,
            })
        except Exception:
            continue

    return messages


def already_sent_today(messages: list[dict]) -> bool:
    """检查今天是否已经发过消息（简化判断：最近消息中有自己发的就算）"""
    # 注意：网页版不一定显示精确时间，这里用"最近几条有自己发的"来判断
    # 如果最后一条消息是自己发的，大概率今天已经续过了
    for msg in reversed(messages[-3:]):
        if msg["sender"] == "me":
            return True
    return False


def build_context(messages: list[dict]) -> str:
    """从最近消息中构建 AI 上下文"""
    friend_msgs = [m for m in messages if m["sender"] == "friend"]

    if not friend_msgs:
        return "（对方最近没有发新消息，发一条轻松的问候续火花即可）"

    parts = []
    for msg in friend_msgs[-5:]:  # 最近 5 条对方消息
        if msg["is_video"] and msg["video_title"]:
            parts.append(f"[分享了一个视频，标题/描述: {msg['video_title']}]")
        elif msg["text"]:
            parts.append(msg["text"])

    return "\n".join(parts) if parts else "（对方最近没有发新消息）"


def send_message(page: Page, text: str, config: dict) -> bool:
    """在聊天输入框中输入并发送消息"""
    chat_input = _find_element(page, CHAT_INPUT_SELECTORS, timeout=10000)
    if not chat_input:
        logger.error("未找到聊天输入框")
        return False

    try:
        chat_input.click()
        time.sleep(0.5)

        # 逐行输入（支持换行）
        lines = text.split("\n")
        for i, line in enumerate(lines):
            chat_input.type(line, delay=50)  # 模拟人工打字速度
            if i < len(lines) - 1:
                chat_input.press("Shift+Enter")

        time.sleep(0.5)
        chat_input.press("Enter")  # 发送
        logger.info(f"消息已发送: {text}")
        time.sleep(2)
        return True
    except Exception as e:
        logger.error(f"发送消息失败: {e}")
        return False


def process_friend(page: Page, friend_name: str, config: dict) -> bool:
    """
    处理单个好友的续火花逻辑
    返回 True 表示成功发送/已跳过，False 表示失败
    """
    logger.info(f"── 处理好友: {friend_name} ──")

    # 1. 找到好友并打开聊天
    if not find_and_click_friend(page, friend_name, config):
        return False

    # 2. 读取最近消息
    messages = read_recent_messages(page, config)
    logger.info(f"读取到 {len(messages)} 条最近消息")

    # 3. 检查是否已经发过
    if already_sent_today(messages):
        logger.info(f"今天已经给 {friend_name} 发过消息，跳过")
        return True

    # 4. 构建上下文，AI 生成回复
    context = build_context(messages)
    logger.debug(f"上下文: {context}")

    reply = generate_reply(context, friend_name)

    # 5. 发送
    return send_message(page, reply, config)
