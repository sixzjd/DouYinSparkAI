"""
Cookie 自动获取工具
打开浏览器 → 手机抖音扫码登录 → 等待 session 完全建立 → 提取 Cookie

用法: python3 get_cookies.py
"""

import json
import time
import sys

from playwright.sync_api import sync_playwright


def main():
    print("=" * 50)
    print("  抖音 Cookie 自动获取工具")
    print("=" * 50)
    print()
    print("即将打开浏览器，请用手机抖音扫码登录。")
    print()

    with sync_playwright() as pw:
        # 优先用系统 Edge/Chrome
        browser = None
        for channel in ["msedge", "chrome", None]:
            try:
                browser = pw.chromium.launch(headless=False, channel=channel)
                break
            except Exception:
                continue
        if not browser:
            print("[!] 未找到浏览器，请先运行: python3 -m playwright install chromium")
            sys.exit(1)

        context = browser.new_context()
        page = context.new_page()

        page.goto("https://creator.douyin.com/")
        print("[*] 浏览器已打开，请扫码登录...")
        print()

        # 等待登录成功
        max_wait = 120
        logged_in = False
        for i in range(max_wait):
            time.sleep(1)
            url = page.url
            if "login" not in url and "passport" not in url and "sso" not in url:
                # URL 已跳转，但需要等 cookie 完全写入
                time.sleep(5)  # 多等几秒让所有 cookie 落盘
                logged_in = True
                break
            if (i + 1) % 15 == 0:
                print(f"[*] 已等待 {i+1} 秒...")

        if not logged_in:
            print("[!] 等待超时，请重试。")
            browser.close()
            sys.exit(1)

        print("[+] 登录成功！正在建立完整会话...")

        # 关键：访问多个页面确保所有域的 cookie 都被设置
        time.sleep(3)
        page.goto("https://creator.douyin.com/creator-micro/home")
        time.sleep(3)
        page.goto("https://creator.douyin.com/creator-micro/data/following/chat")
        time.sleep(3)

        # 提取所有 cookie
        all_cookies = context.cookies()
        browser.close()

    # 筛选 douyin 相关
    douyin_cookies = [c for c in all_cookies if "douyin" in c.get("domain", "")]

    # 检查关键 cookie
    names = [c["name"] for c in douyin_cookies]
    key_names = ["sessionid", "sessionid_ss", "sid_guard", "sid_tt", "passport_csrf_token"]
    found_keys = [k for k in key_names if k in names]
    missing_keys = [k for k in key_names if k not in names]

    print()
    print("=" * 50)
    print(f"[+] 共获取 {len(douyin_cookies)} 条 Cookie")
    print(f"[+] 关键认证 Cookie: {found_keys}")
    if missing_keys:
        print(f"[!] 缺少: {missing_keys}")
        print("[!] 可能影响登录，建议重新扫码重试")
    print("=" * 50)
    print()

    # 清理 Playwright 不兼容的字段
    for c in douyin_cookies:
        c.pop("sameSite", None)
        # expires=-1 的 session cookie 改为不设过期
        if c.get("expires", 0) < 0:
            c["expires"] = -1  # Playwright 接受 -1 表示 session cookie

    cookie_json = json.dumps(douyin_cookies, ensure_ascii=False)

    with open("cookies.json", "w", encoding="utf-8") as f:
        f.write(cookie_json)
    print("[+] 已保存到 cookies.json")
    print()
    print("─── 复制下面的 JSON 到 GitHub Secret (COOKIES_USER1) ───")
    print()
    print(cookie_json)
    print()
    print("─── 结束 ───")


if __name__ == "__main__":
    main()
