"""
核心聊天逻辑：
1. 打开创作者中心私信页面（带重试）
2. 滚动好友列表找到目标（多版本 DOM 兼容 + 到底检测）
3. 判断是否需要回复（对方发了→回复；我发的但不是今天→也回复续火花）
4. 读取最近消息（含视频标题、时间标签）
5. AI 生成回复并发送
"""

import re
import time
from typing import Optional
import traceback
from playwright.sync_api import Page, Response
from utils.config import get_config
from utils.logger import setup_logger
from utils.state_utils import slim_state
from core.ai_reply import generate_reply

logger = setup_logger()

# ─── 多版本 DOM 选择器（抖音 A/B 测试导致不同账号页面结构不同）───

# 好友 tab 按钮
# 2026-09 改版后原"好友"tab 变为 semi-design 的"朋友私信"tab
FRIEND_TAB_SELECTORS = [
    'xpath=//div[contains(@class, "semi-tabs-bar") and contains(text(), "朋友私信")]',
    'xpath=//div[contains(@class, "semi-tabs-bar") and contains(text(), "全部")]',
    'xpath=//*[@id="sub-app"]/div/div/div[1]/div[2]',
    'xpath=//div[contains(@class, "tab") and contains(text(), "好友")]',
]

# 好友列表项（名字所在元素）
FRIEND_ITEM_SELECTORS = [
    # 2026-09 改版：semi-design 列表，会话是 li.semi-list-item
    'xpath=//div[contains(@class, "semi-list")]//li[contains(@class, "semi-list-item")]',
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
# 2026-09 改版后好友列表改用 react-virtualized 渲染
SCROLL_CONTAINER_SELECTORS = [
    '[class*="ReactVirtualized__List"]',
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

# 消息列表项（聊天区域）
# 真实结构: box-content 容器内的一排排 div.box-item-*；
# class 后缀哈希（如 W0TV01）随版本变化，必须用前缀子串匹配。
# 注意: 内层内容包装的 class 是 box-item-message-*，也含 "box-item-" 子串，
#       必须用 :not() 排除，否则每条消息会被读两次（且内层不带 is-me 会误判发送方）。
# 消息行里混有 time-（时间分隔）和 tip-（系统提示）需要跳过。
MESSAGE_ITEM_SELECTORS = [
    '[class*="box-content"] div[class*="box-item-"]:not([class*="box-item-message"])',
    'div[class*="box-item-"]:not([class*="box-item-message"])',
    'xpath=//div[contains(@class, "messageMessageList")]//div[@data-e2e="msg-item-content"]',
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


def is_today_label(label: str) -> bool:
    """
    判断时间分隔标签是否代表"今天"。
    抖音聊天中，今天的消息时间标签是纯 HH:MM（如 "16:43"），
    昨天显示"昨天"，本周显示"星期X"，更早显示"MM-DD"。
    """
    label = label.strip()
    if "今天" in label:
        return True
    return bool(re.fullmatch(r"\d{1,2}:\d{2}", label))


def fetch_video_description(url: str) -> str:
    """
    尝试从视频页面获取标题/描述（用于丰富 AI 上下文）。
    用 urllib 请求页面，提取 <title> 或 meta description。
    失败时静默返回空字符串（不影响主流程）。
    """
    if not url:
        return ""
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://creator.douyin.com/",
        })
        with urllib.request.urlopen(req, timeout=8) as resp:
            html = resp.read(50000).decode("utf-8", errors="ignore")

        # 优先取 meta description（通常是视频简介）
        desc_match = re.search(
            r'<meta\s+name="description"\s+content="([^"]*)"', html
        )
        if desc_match and desc_match.group(1).strip():
            return desc_match.group(1).strip()[:200]

        # 兜底取 <title>（格式一般是 "视频标题 - 抖音"）
        title_match = re.search(r"<title>([^<]+)</title>", html)
        if title_match:
            title = title_match.group(1).strip()
            # 去掉 " - 抖音" 后缀
            title = re.sub(r"\s*[-–—]\s*抖音$", "", title)
            return title[:200]

    except Exception as e:
        logger.debug(f"获取视频描述失败 ({url[:60]}): {e}")
    return ""


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


def is_logged_in(page: Page) -> bool:
    """
    判断当前会话是否处于登录态。
    依据两点：
    1. URL 没有被重定向到登录/passport/sso 页面；
    2. cookie 中存在 sessionid（创作者中心登录的核心凭证，httpOnly）。
    只有确认登录成功才去抓取/回写新 cookie，避免用坏 cookie 覆盖好 cookie。
    """
    url = page.url.lower()
    if any(k in url for k in ("login", "passport", "sso", "verify")):
        logger.warning(f"页面落在登录/验证页 ({page.url})，判定未登录")
        return False

    try:
        cdp = page.context.new_cdp_session(page)
        all_cookies = cdp.send("Network.getAllCookies").get("cookies", [])
        cdp.detach()
        names = {c["name"] for c in all_cookies}
        if "sessionid" in names or "sessionid_ss" in names:
            return True
        logger.warning(f"cookie 中缺少 sessionid（现有 {len(names)} 条），判定未登录")
        return False
    except Exception as e:
        logger.warning(f"登录态检测失败: {e}，保守判定未登录")
        return False


def capture_fresh_state(page: Page, path: str = "logs/fresh_cookies.json") -> bool:
    """
    抓取当前浏览器里的最新登录态并精简保存。
    每次成功运行后，服务端通常已对会话续期（下发新的 sessionid 等），
    把这份"新鲜" cookie 回写到 GitHub Secret，即可实现 cookie 永不过期的全自动循环。

    用 CDP Network.getAllCookies 获取完整 cookie（含 httpOnly 的 sessionid），
    再与 context.storage_state() 的 localStorage 合并，最后 slim 到 Secret 可容纳的大小。
    """
    import os
    import json

    try:
        cdp = page.context.new_cdp_session(page)
        cdp_cookies = cdp.send("Network.getAllCookies").get("cookies", [])
        cdp.detach()

        # storage_state 提供 origins(localStorage)；其 cookies 用 CDP 的更全版本替换
        state = page.context.storage_state()
        state["cookies"] = cdp_cookies

        slim = slim_state(state)

        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(slim, f, ensure_ascii=False)

        size_kb = os.path.getsize(path) / 1024
        logger.info(f"已抓取最新登录态 → {path}（{len(cdp_cookies)} 条 cookie，{size_kb:.1f} KB）")
        return True
    except Exception as e:
        logger.error(f"抓取最新登录态失败: {e}")
        return False


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

    # short_id 模式额外诊断：打印拦截到的 抖音号→昵称 映射，
    # 若为空说明 user_detail 接口没触发，抖音号匹配无从谈起
    if match_mode == "short_id" and id_collector:
        if id_collector.mapping:
            logger.info(f"拦截到的抖音号映射共 {len(id_collector.mapping)} 条: "
                        f"{ {sid: info.get('nickname') for sid, info in id_collector.mapping.items()} }")
        else:
            logger.warning("short_id 模式但未拦截到任何用户映射（user_detail 接口未触发）")
    return False


def read_recent_messages(page: Page, config: dict) -> list[dict]:
    """
    读取当前聊天窗口的最近消息
    返回: [{"sender": "me"/"friend", "text": "...", "is_video": bool, "video_title": "..."}]
    """
    messages = []
    current_time_label = ""  # 当前消息所属的时间分隔标签
    time.sleep(1)

    msg_items = _try_locator_all(page, MESSAGE_ITEM_SELECTORS, timeout=8000)
    if not msg_items:
        logger.warning("未找到消息列表元素")
        return messages

    for item in msg_items:
        try:
            cls = item.get_attribute("class") or ""

            # 时间分隔符（time-）：记录标签文本，供后续消息关联
            if "time-" in cls:
                current_time_label = item.inner_text().strip()
                continue

            # 系统提示（tip-）：跳过
            if "tip-" in cls:
                continue

            # 发送方向：自己的消息带 is-me 前缀类
            is_self = "is-me" in cls

            # 视频/卡片消息：带 aweme-cover 封面元素
            cover = item.locator('[class*="aweme-cover"]')
            is_video = cover.count() > 0

            # 文本内容：在 pre[class*="text-item-message"] 里
            text_el = item.locator('pre[class*="text-item-message"]').first
            if text_el.count() == 0:
                text_el = item.locator("pre").first
            text = text_el.inner_text().strip() if text_el.count() > 0 else ""

            if is_video:
                # 视频卡片：尽量多拿信息（标题、作者、描述、链接）
                # 1. 卡片内所有可见文本（标题/作者/描述可能分散在不同子元素）
                card_text = item.inner_text().strip()
                video_title = card_text or text or "[视频]"

                # 2. 尝试提取视频链接（用于后续获取详细描述）
                video_url = ""
                link_el = item.locator("a[href]").first
                if link_el.count() > 0:
                    href = link_el.get_attribute("href") or ""
                    if "douyin.com" in href or "aweme" in href:
                        video_url = href

                messages.append({
                    "sender": "me" if is_self else "friend",
                    "text": text,
                    "is_video": True,
                    "video_title": video_title,
                    "video_url": video_url,
                    "time_label": current_time_label,
                })
            elif text:
                messages.append({
                    "sender": "me" if is_self else "friend",
                    "text": text,
                    "is_video": False,
                    "video_title": "",
                    "time_label": current_time_label,
                })
            # 纯表情/图片消息（text 为空且非视频）：暂不记录
        except Exception:
            continue

    # 抖音 DOM 有时会把同一条消息渲染两次（虚拟列表/表情消息），
    # 去掉"连续且完全相同"的消息，避免 AI 上下文重复
    deduped = []
    for m in messages:
        if (deduped
                and deduped[-1]["sender"] == m["sender"]
                and deduped[-1]["text"] == m["text"]
                and deduped[-1]["is_video"] == m["is_video"]):
            continue
        deduped.append(m)

    # 只保留最近 10 条
    return deduped[-10:]


def should_reply(messages: list[dict]) -> bool:
    """
    是否需要回复（续火花逻辑）：
    1. 最后一条是对方发的 → 回复
    2. 最后一条是我发的，但我今天还没发过消息 → 也回复（保持火花不断）
    3. 最后一条是我发的，且今天已经发过 → 跳过（避免重复发送）
    """
    if not messages:
        return False  # 没读到消息，不贸然发送

    last = messages[-1]
    if last["sender"] == "friend":
        return True

    # 最后一条是我发的：检查我今天是否已经发过
    sent_today = any(
        m["sender"] == "me" and is_today_label(m.get("time_label", ""))
        for m in messages
    )
    if sent_today:
        return False  # 今天已发过，跳过
    return True  # 最后一条是我发的但不是今天 → 需要续火花


def build_context(messages: list[dict]) -> str:
    """
    构建完整对话流（双方消息按顺序、带标签），让 AI 理解来龙去脉、接住话题。
    视频消息会尝试获取页面描述，让 AI 知道视频讲了什么。
    """
    if not messages:
        return "（没有可读消息，发一条轻松的问候续火花即可）"

    parts = []
    for m in messages[-8:]:
        who = "我" if m["sender"] == "me" else "对方"
        if m["is_video"]:
            title = m.get("video_title", "[视频]")
            # 尝试获取视频详细描述（标题/简介）
            url = m.get("video_url", "")
            desc = fetch_video_description(url) if url else ""
            if desc and desc != title:
                content = f"[分享了一个视频: {title} | 内容: {desc}]"
            else:
                content = f"[分享了一个视频: {title}]"
        else:
            content = m["text"]
        parts.append(f"{who}: {content}")
    return "\n".join(parts)


def build_style_examples(messages: list[dict]) -> str:
    """
    提取"我"最近说的话作为风格样本，让 AI 模仿我的语气和用词习惯。
    """
    my_msgs = [m["text"] for m in messages
               if m["sender"] == "me" and not m["is_video"] and m["text"]]
    if not my_msgs:
        return "（暂无风格样本，用轻松随意的朋友口吻）"
    return "\n".join(my_msgs[-5:])


def send_message(page: Page, text: str, config: dict) -> bool:
    """在聊天输入框中输入并发送消息"""
    if config.get("dry_run"):
        logger.info(f"[试运行] 将发送但不真正发出: {text}")
        return True

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
        logger.info(f"无需回复 {friend_name}（今天已发过消息），跳过")
        return True

    context = build_context(messages)
    style = build_style_examples(messages)
    style_profile = config.get("style_profile", "")
    logger.debug(f"AI 上下文:\n{context}")

    reply = generate_reply(context, friend_name, style_examples=style,
                           style_profile=style_profile)
    return send_message(page, reply, config)
