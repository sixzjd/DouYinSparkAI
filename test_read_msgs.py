"""本地验证：用真实 read_recent_messages 函数读消息"""
import json, time
from playwright.sync_api import sync_playwright
from core.chat import read_recent_messages, should_reply, build_context

with open("auth_state.json") as f:
    state = json.load(f)

config = {"browser_timeout": 30000, "task_retry_times": 2, "match_mode": "nickname"}

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=False, channel="msedge")
    context = browser.new_context(storage_state=state)
    page = context.new_page()

    page.goto("https://creator.douyin.com/creator-micro/data/following/chat",
              wait_until="domcontentloaded", timeout=30000)
    time.sleep(6)

    first = page.locator('xpath=//div[contains(@class, "semi-list")]//li[1]//div[contains(@class, "semi-list-item")]').first
    first.click()
    time.sleep(4)

    msgs = read_recent_messages(page, config)
    print(f"\n=== 读取到 {len(msgs)} 条消息 ===")
    for m in msgs:
        tag = "我" if m["sender"] == "me" else "对方"
        vid = " [视频]" if m["is_video"] else ""
        print(f"  [{tag}]{vid} {m['text'][:40] or m['video_title'][:40]}")

    print(f"\nshould_reply = {should_reply(msgs)}")
    if msgs:
        print(f"最后一条来自: {'我' if msgs[-1]['sender']=='me' else '对方'}")
    print(f"\nAI 上下文:\n{build_context(msgs)}")

    browser.close()
