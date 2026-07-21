"""
核心聊天逻辑：
1. 打开创作者中心私信页面（带重试）
2. 滚动好友列表找到目标（多版本 DOM 兼容 + 到底检测）
3. 检查今天是否已经发过消息（已发则跳过）
4. 读取对方最近消息（含视频标题）
5. AI 生成回复并发送
"""

import time
from typing import Optional
import traceback
from playwright.sync_api import Page, Response
from utils.config import get_config
from utils.logger import setup_logger
from core.ai_reply import generate_reply

logger = setup_logger()

# ─── 多版本 DOM 选择器（抖音 A/B 测试导致不同账号页面结构不同）───

# 好友 tab 按钮
FRIEND_TAB_SELECTORS = [
    'xpath=//*[@id="sub-app"]/div/div/div[1]/div[2]',
    'xpath=//div[contains(@class, "tab") and contains(text(), "好友")]',
]

# 好友列表项（名字所在元素）
FRIEND_ITEM_SELECTORS = [
    'xpath=//*[@id="sub-app"]/div/div[1]/div[2]/div[2]//div[contains(@class, "semi-list-item-body")]',
    'xpath=//div[contains(@class, "conversation-item")]',
    'xpath=//div[@data-e2e="conversation-item"]',
]

# 好友名字 span
FRIEND_NAME_SPAN = 'xpath=.//span[contains(@class, "item-header-name-")]'

# 第一个好友（用于激活列表）
FIRST_FRIEND_SELECTORS = [
    'xpath=//*[@id="sub-app"]/div/div/div[2]/div[2]/div/div/div[1]/div/div/div/ul/div/div/div[1]/li/div',
    'xpath=//div[contains(@class, "semi-list")]//li[1]//div[contains(@class, "semi-list-item")]',
]

# 滚动容器
SCROLL_CONTAINER_SELECTORS = [
    'xpath=//*[@id="sub-app"]/div/div[1]/div[2]/div[2]/div/div/div[3]/div/div/div/ul/div',
    'xpath=//div[contains(@class, "semi-list")]//div[contains(@class, "virtual-list")]',
    'xpath=//div[contains(@class, "semi-list-body")]',
]

# "没有更多了" 提示
NO_MORE_SELECTORS = [
    'xpath=//div[contains(@class, "no-more-tip-")]',
    'xpath=//div[contains(text(), "没有更多")]',
]

# 加载中指示器
LOADING_SELECTORS = [
    'xpath=//div[contains(@class, "semi-spin")]',
    'xpath=//div[contains(@class, "loading")]',
]

# 聊天输入框
CHAT_INPUT_SELECTORS = [
    "xpath=//div[contains(@class, 'chat-input-')]",
    "xpath=//div[@contenteditable='true']",
    "xpath=//div[contains(@class, 'messageMsgInput')]",
]

# 消息列表项
MESSAGE_ITEM_SELECTORS = [
    'xpath=//div[contains(@class, "messageMessageList")]//div[@data-e2e="msg-item-content"]',
    'xpath=//div[@id="messageContent"]//div[contains(@style, "justify-content")]',
    'xpath=//div[contains(@class, "chat-message")]//div[contains(@class, "msg-item")]',
    'xpath=//div[contains(@class, "message-list")]//div[contains(@class, "message-item")]',
]

# 用户详情 API（用于 short_id 匹配模式）
USER_DETAIL_API = "aweme/v1/creator/im/user_detail/"


# ─── 工具函数 ───

def retry(name: str, func, retries: int = 3, delay: float = 5, **kwargs):
    """通用重试：页面导航等不稳定操作"""
    for attempt in range(retries):
        try:
            return func(**kwargs)
        except Exception as e:
            if attempt < retries - 1:
                logger.warning(f"{name} 失败 (第{attempt+1}次): {e}，{delay}s 后重试")
                time.sleep(delay)
            else:
                logger.error(f"{name} 最终失败: {e}")
                raise


def _try_locator(page: Page, selectors: list[str], timeout: int = 5000):
    """按优先级尝试多个选择器，返回第一个可用的 locator"""
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            loc.wait_for(timeout=timeout)
            return loc
        except Exception:
            continue
    return None


def _try_locator_all(page: Page, selectors: list[str], timeout: int = 5000):
    """按优先级尝试多个选择器，返回第一个有结果的列表"""
    for sel in selectors:
        try:
            page.locator(sel).first.wait_for(timeout=timeout)
            return page.locator(sel).all()
        except Exception:
            continue
    return []


# ─── 响应拦截（short_id 匹配模式）───

class UserIdCollector:
    """拦截创作者中心 API 响应，收集 抖音号→昵称 映射"""

    def __init__(self):
        self.mapping: dict[str, dict] = {}  # {short_id: {nickname, user_id}}

    def on_response(self, response: Response):
        if USER_DETAIL_API not in response.url:
            return
        try:
            data = response.json()
            for item in data.get("user_list", []):
                user = item.get("user", {})
                short_id = str(user.get("ShortId", ""))
                nickname = user.get("nickname", "")
                user_id = item.get("user_id", "")
                if short_id:
                    self.mapping[short_id] = {
                        "nickname": nickname,
                        "user_id": user_id,
                    }
        except Exception:
            pass  # 非目标响应，忽略


# ─── 主流程 ───

def navigate_to_chat(page: Page, cookies: list[dict], config: dict,
                     has_storage_state: bool = False):
    """导航到创作者中心私信页面（带重试）"""
    import os
    timeout = config["browser_timeout"]
    retries = config["task_retry_times"]

    # 调试：打印当前 context 中的 cookie 情况
    ctx_cookies = page.context.cookies(["https://creator.douyin.com"])
    ctx_names = [c["name"] for c in ctx_cookies]
    logger.info(f"context 中已有 {len(ctx_cookies)} 条 cookie: {ctx_names}")

    # 调试：监听主文档响应，看服务端返回
    def _on_response(resp):
        if "creator.douyin.com" in resp.url and resp.request.resource_type == "document":
            logger.info(f"[net] {resp.status} {resp.url[:100]}")

    page.on("response", _on_response)

    if has_storage_state:
        # storage_state 已包含完整登录态，直接访问私信页
        retry(
            "导航到私信页面",
            page.goto,
            retries=retries,
            delay=5,
            url="https://creator.douyin.com/creator-micro/data/following/chat",
            timeout=timeout,
        )
    else:
        # 纯 cookie 模式：先访问主页注入 cookie 再跳转
        retry(
            "打开创作者中心",
            page.goto,
            retries=retries,
            delay=5,
            url="https://creator.douyin.com/",
            timeout=timeout,
        )
        page.context.add_cookies(cookies)
        retry(
            "导航到私信页面",
            page.goto,
            retries=retries,
            delay=5,
            url="https://creator.douyin.com/creator-micro/data/following/chat",
            timeout=timeout,
        )

    time.sleep(3)

    # 调试：导航后再次检查 cookie（看服务端有没有下发新的/清除）
    after_cookies = page.context.cookies(["https://creator.douyin.com"])
    after_names = [c["name"] for c in after_cookies]
    logger.info(f"导航后 cookie ({len(after_cookies)} 条): {after_names}")
    logger.info(f"最终落地 URL: {page.url}")

    # 调试截图：记录页面实际状态
    os.makedirs("logs", exist_ok=True)
    page.screenshot(path="logs/debug_chat_page.png", full_page=True)
    logger.info("已保存页面截图 logs/debug_chat_page.png")


def find_and_click_friend(page: Page, friend_name: str, config: dict,
                         id_collector: Optional[UserIdCollector] = None) -> bool:
    """
    在好友列表中滚动查找目标好友并点击
    借鉴：空滚动计数 + scrollTop 对比 + "没有更多"检测 + loading 等待
    """
    match_mode = config["match_mode"]

    # 点击好友 tab
    tab = _try_locator(page, FRIEND_TAB_SELECTORS, timeout=10000)
    if tab:
        tab.click()
        time.sleep(2)

    # 点击第一个好友激活列表（源项目经验：不激活则滚动不生效）
    first = _try_locator(page, FIRST_FRIEND_SELECTORS, timeout=5000)
    if first:
        first.click()
        time.sleep(1)

    found_names: set[str] = set()
    empty_scroll_count = 0
    MAX_EMPTY_SCROLLS = 10

    while True:
        items = _try_locator_all(page, FRIEND_ITEM_SELECTORS, timeout=5000)
        prev_count = len(found_names)

        for item in items:
            try:
                # 提取好友名字
                name_span = item.locator(FRIEND_NAME_SPAN)
                if name_span.count() > 0:
                    display_name = name_span.first.inner_text().strip()
                else:
                    # 兜底：取元素文本第一行
                    display_name = item.inner_text().strip().split("\n")[0]

                if not display_name or display_name in found_names:
                    continue
                found_names.add(display_name)

                # 匹配逻辑
                if match_mode == "short_id" and id_collector:
                    # 通过拦截到的 API 数据反查抖音号
                    matched_id = next(
                        (sid for sid, info in id_collector.mapping.items()
                         if info.get("nickname") == display_name),
                        None,
                    )
                    is_target = matched_id == friend_name
                else:
                    # 昵称模糊匹配
                    is_target = (
                        friend_name in display_name
                        or display_name in friend_name
                    )

                if is_target:
                    item.click()
                    logger.info(f"找到并选中好友: {display_name}")
                    time.sleep(2)
                    return True

            except Exception:
                continue

        # 本轮是否有新发现
        if len(found_names) > prev_count:
            empty_scroll_count = 0
        else:
            empty_scroll_count += 1

        # ── 到底检测（多重兜底）──

        # 1. "没有更多了" 标志
        hit_bottom = False
        for sel in NO_MORE_SELECTORS:
            if page.locator(sel).count() > 0:
                logger.info("检测到'没有更多了'，列表已到底")
                hit_bottom = True
                break
        if hit_bottom:
            break

        # 2. 连续空滚动
        if empty_scroll_count >= MAX_EMPTY_SCROLLS:
            logger.warning(f"连续 {MAX_EMPTY_SCROLLS} 次无新好友，判定到底")
            break

        # 3. 正在加载 → 等一下再继续
        loading = False
        for sel in LOADING_SELECTORS:
            if page.locator(sel).count() > 0:
                loading = True
                break
        if loading:
            time.sleep(1.5)

        # 4. 滚动
        scroll_el = _try_locator(page, SCROLL_CONTAINER_SELECTORS, timeout=2000)
        if not scroll_el:
            logger.warning("未找到滚动容器，停止搜索")
            break

        handle = scroll_el.element_handle()
        top_before = page.evaluate("(el) => el.scrollTop", handle)
        page.evaluate("(el) => el.scrollTop += 700", handle)
        time.sleep(0.3)
        top_after = page.evaluate("(el) => el.scrollTop", handle)

        if top_before == top_after:
            empty_scroll_count += 2  # 加速判定
            logger.debug(f"scrollTop 未变化 ({top_before})，可能到底")

        time.sleep(1.5)

    # 未找到：打印扫描到的全部昵称，方便用户核对 TASKS 里该填什么名字
    if found_names:
        logger.info(f"本次扫描到的会话昵称共 {len(found_names)} 个: {sorted(found_names)}")
    else:
        logger.warning("未扫描到任何会话昵称（列表可能未加载）")
    return False


def read_recent_messages(page: Page, config: dict) -> list[dict]:
    """
    读取当前聊天窗口的最近消息
    返回: [{"sender": "me"/"friend", "text": "...", "is_video": bool, "video_title": "..."}]
    """
    messages = []
    time.sleep(1)

    msg_items = _try_locator_all(page, MESSAGE_ITEM_SELECTORS, timeout=8000)
    if not msg_items:
        logger.warning("未找到消息列表元素")
        return messages

    # 只取最近 10 条
    for item in msg_items[-10:]:
        try:
            text = item.inner_text().strip()
            if not text:
                continue

            # 检测视频/卡片消息
            is_video = False
            video_title = ""
            card_el = item.locator(
                "xpath=.//*[contains(@class, 'video') or contains(@class, 'card') "
                "or contains(@class, 'share') or contains(@class, 'aweme')]"
            )
            if card_el.count() > 0:
                is_video = True
                video_title = text

            # 判断发送方向
            item_class = item.get_attribute("class") or ""
            parent_class = ""
            try:
                parent_class = item.locator("xpath=..").get_attribute("class") or ""
            except Exception:
                pass
            combined = (item_class + " " + parent_class).lower()
            is_self = any(kw in combined for kw in ["self", "right", "mine", "sender", "is-self"])

            messages.append({
                "sender": "me" if is_self else "friend",
                "text": text,
                "is_video": is_video,
                "video_title": video_title,
            })
        except Exception:
            continue

    return messages


def should_reply(messages: list[dict]) -> bool:
    """
    是否需要回复：只有当最后一条消息是对方发的，才回复。
    回复后最后一条变成"我的"，自然不会重复发送，直到对方再次发消息。
    这样实现"对方发了我没发 → 回复；我已发过 → 跳过"。
    """
    if not messages:
        return False  # 没读到消息，不贸然发送
    last = messages[-1]
    return last["sender"] == "friend"


def build_context(messages: list[dict]) -> str:
    """从对方最近消息构建 AI 上下文"""
    friend_msgs = [m for m in messages if m["sender"] == "friend"]
    if not friend_msgs:
        return "（对方最近没有发新消息，发一条轻松的问候续火花即可）"

    parts = []
    for msg in friend_msgs[-5:]:
        if msg["is_video"] and msg["video_title"]:
            parts.append(f"[分享了一个视频，标题/描述: {msg['video_title']}]")
        elif msg["text"]:
            parts.append(msg["text"])

    return "\n".join(parts) if parts else "（对方最近没有发新消息）"


def send_message(page: Page, text: str, config: dict) -> bool:
    """在聊天输入框中输入并发送消息"""
    chat_input = _try_locator(page, CHAT_INPUT_SELECTORS, timeout=10000)
    if not chat_input:
        logger.error("未找到聊天输入框")
        return False

    try:
        chat_input.click()
        time.sleep(0.5)

        # 逐行输入，模拟人工打字
        lines = text.split("\n")
        for i, line in enumerate(lines):
            chat_input.type(line, delay=50)
            if i < len(lines) - 1:
                chat_input.press("Shift+Enter")

        time.sleep(0.5)
        chat_input.press("Enter")
        logger.info(f"消息已发送: {text}")
        time.sleep(2)
        return True
    except Exception as e:
        logger.error(f"发送失败: {e}")
        return False


def process_friend(page: Page, friend_name: str, config: dict,
                   id_collector: Optional[UserIdCollector] = None) -> bool:
    """处理单个好友的续火花逻辑"""
    logger.info(f"── 处理好友: {friend_name} ──")

    if not find_and_click_friend(page, friend_name, config, id_collector):
        logger.warning(f"好友 {friend_name} 未找到，跳过")
        return False

    messages = read_recent_messages(page, config)
    logger.info(f"读取到 {len(messages)} 条最近消息")

    if messages:
        last = messages[-1]
        logger.info(f"最后一条消息来自: {'我' if last['sender'] == 'me' else '对方'} | 内容: {last['text'][:30]}")

    if not should_reply(messages):
        logger.info(f"无需回复 {friend_name}（最后一条是我发的，或没有可读消息），跳过")
        return True

    context = build_context(messages)
    logger.debug(f"AI 上下文: {context}")

    reply = generate_reply(context, friend_name)
    return send_message(page, reply, config)
