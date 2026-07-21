"""快速测试：用保存的登录态打开私信页，看是否保持登录"""
import json, time
from playwright.sync_api import sync_playwright

with open("auth_state.json") as f:
    state = json.load(f)

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=False, channel="msedge")
    context = browser.new_context(storage_state=state)
    page = context.new_page()

    print("[*] 打开私信页...")
    page.goto("https://creator.douyin.com/creator-micro/data/following/chat",
              wait_until="domcontentloaded", timeout=30000)
    time.sleep(8)

    url = page.url
    title = page.title()
    print(f"[*] 落地 URL: {url}")
    print(f"[*] 页面标题: {title}")

    # 检查是否出现登录表单
    login_form = page.query_selector('input[placeholder*="手机号"]')
    chat_list = page.query_selector('[class*="conversation"], [class*="chat-list"], [class*="message"]')

    if login_form:
        print("[!] 结果: 显示登录页 ← 登录态无效")
    elif chat_list:
        print("[+] 结果: 进入私信列表 ← 登录态有效！")
    else:
        print("[?] 结果: 无法判断，截图查看")

    page.screenshot(path="test_login_result.png", full_page=False)
    print("[*] 截图已保存: test_login_result.png")

    browser.close()
