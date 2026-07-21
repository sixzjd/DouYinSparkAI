"""
DOM 诊断：dump 聊天消息区结构，摸清两件事
1. 消息时间戳/时间分隔符格式（用于判断某条消息是不是"今天"发的）
2. 视频/图文卡片结构 + 是否有内置 AI 总结入口（求真/豆包）
通过 CI 的 diag.yml 运行（需要 cookies），结果写入 logs/diag_dom.txt 并上传。
"""
import os
from core.browser import get_browser
from core.chat import navigate_to_chat, find_and_click_friend, UserIdCollector
from utils.config import get_config, get_tasks

OUT = "logs/diag_dom.txt"


def dump(page, friend):
    lines = []
    lines.append(f"\n{'='*60}\n好友: {friend}\n{'='*60}")

    # 1) 时间分隔符（time- 类）：完整 outerHTML + 文本，看日期格式
    time_els = page.query_selector_all('[class*="time-"]')
    lines.append(f"\n--- 时间分隔符 共 {len(time_els)} 个 ---")
    for i, el in enumerate(time_els[:15]):
        try:
            cls = el.get_attribute("class") or ""
            txt = (el.inner_text() or "").strip().replace("\n", " ")
            html = el.evaluate("e => e.outerHTML")
            lines.append(f"[time#{i}] class={cls[:80]}")
            lines.append(f"         text={txt!r}")
            lines.append(f"         html={html[:300]}")
        except Exception as e:
            lines.append(f"[time#{i}] err={e}")

    # 2) 消息项（box-item-，排除内层 box-item-message）：class + 文本 + 是否带时间属性
    msg_els = page.query_selector_all('div[class*="box-item-"]:not([class*="box-item-message"])')
    lines.append(f"\n--- 消息项 共 {len(msg_els)} 个 ---")
    for i, el in enumerate(msg_els[-12:]):
        try:
            cls = el.get_attribute("class") or ""
            txt = (el.inner_text() or "").strip().replace("\n", " ")
            # 看看有没有 data-* 时间戳属性
            attrs = el.evaluate("""e => {
                const o = {};
                for (const a of e.attributes) {
                    if (a.name.startsWith('data-') || a.name === 'aria-label') o[a.name] = a.value;
                }
                return o;
            }""")
            lines.append(f"[msg] class={cls[:90]}")
            lines.append(f"      text={txt[:60]!r}")
            if attrs:
                lines.append(f"      attrs={attrs}")
        except Exception as e:
            lines.append(f"[msg] err={e}")

    # 3) 视频/图文卡片（aweme-cover）：dump 卡片祖先的 outerHTML
    covers = page.query_selector_all('[class*="aweme-cover"]')
    lines.append(f"\n--- 视频/图文卡片 共 {len(covers)} 个 ---")
    for i, el in enumerate(covers[:3]):
        try:
            html = el.evaluate("e => { let n=e; for(let k=0;k<4 && n.parentElement;k++){n=n.parentElement;} return n.outerHTML; }")
            lines.append(f"[video#{i}] 卡片(向上4层)HTML:\n{html[:1500]}")
        except Exception as e:
            lines.append(f"[video#{i}] err={e}")

    return "\n".join(lines)


def main():
    config = get_config()
    tasks = get_tasks()
    if not tasks:
        print("无任务"); return
    user = tasks[0]
    pw, browser = get_browser()
    out_parts = []
    try:
        storage_state = user.get("storage_state")
        context = browser.new_context(storage_state=storage_state) if storage_state else browser.new_context()
        context.set_default_navigation_timeout(config["browser_timeout"])
        context.set_default_timeout(config["browser_timeout"])
        page = context.new_page()

        id_collector = None
        if config["match_mode"] == "short_id":
            id_collector = UserIdCollector()
            page.on("response", id_collector.on_response)

        navigate_to_chat(page, user["cookies"], config, has_storage_state=bool(storage_state))

        for friend in user["targets"]:
            try:
                if find_and_click_friend(page, friend, config, id_collector):
                    import time; time.sleep(2)
                    out_parts.append(dump(page, friend))
                else:
                    out_parts.append(f"\n好友 {friend} 未找到")
            except Exception as e:
                out_parts.append(f"\n好友 {friend} 出错: {e}")
        context.close()
    finally:
        browser.close(); pw.stop()

    os.makedirs("logs", exist_ok=True)
    content = "\n".join(out_parts)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(content)
    print(content)
    print(f"\n[+] 已写入 {OUT}")


if __name__ == "__main__":
    main()
