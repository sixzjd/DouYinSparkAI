"""
抖音登录态获取工具
保存完整浏览器状态（Cookie + localStorage），确保 CI 能复现登录
"""

import json
import time
import sys

from playwright.sync_api import sync_playwright


def main():
    print("=" * 50)
    print("  抖音登录态获取工具")
    print("=" * 50)
    print()

    with sync_playwright() as pw:
        browser = None
        for channel in ["msedge", "chrome", None]:
            try:
                browser = pw.chromium.launch(headless=False, channel=channel)
                break
            except Exception:
                continue
        if not browser:
            print("[!] 未找到浏览器，请运行: python3 -m playwright install chromium")
            sys.exit(1)

        context = browser.new_context()
        page = context.new_page()

        page.goto("https://creator.douyin.com/")
        print("[*] 请扫码登录...")

        for i in range(120):
            time.sleep(1)
            url = page.url
            if "login" not in url and "passport" not in url and "sso" not in url:
                time.sleep(5)
                break
            if (i + 1) % 15 == 0:
                print(f"[*] 等待中... {i+1}s")
        else:
            print("[!] 超时")
            browser.close()
            sys.exit(1)

        print("[+] 登录成功！")

        # 访问关键页面确保状态完整
        page.goto("https://creator.douyin.com/creator-micro/data/following/chat")
        time.sleep(5)

        # 保存完整浏览器状态（cookies + localStorage origins）
        state = context.storage_state()
        browser.close()

    # 保存完整状态
    with open("auth_state.json", "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)

    # 同时保存纯 cookie（兼容旧格式）
    cookies = state.get("cookies", [])
    douyin_cookies = [c for c in cookies if "douyin" in c.get("domain", "")]
    for c in douyin_cookies:
        c.pop("sameSite", None)

    with open("cookies.json", "w", encoding="utf-8") as f:
        json.dump(douyin_cookies, f, ensure_ascii=False)

    # 报告
    cookie_names = [c["name"] for c in douyin_cookies]
    origins = state.get("origins", [])
    ls_count = sum(len(o.get("localStorage", [])) for o in origins)

    print()
    print(f"[+] Cookie: {len(douyin_cookies)} 条")
    print(f"[+] localStorage: {ls_count} 项 ({len(origins)} 个域)")
    print(f"[+] Cookie 列表: {cookie_names[:10]}...")
    print()
    print("[+] 已保存:")
    print("    auth_state.json  ← 完整状态（CI 用这个）")
    print("    cookies.json     ← 纯 cookie（备用）")
    print()
    print("─── 将 auth_state.json 的内容粘贴到 GitHub Secret (COOKIES_USER1) ───")


if __name__ == "__main__":
    main()
