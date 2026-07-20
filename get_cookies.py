"""
Cookie 自动获取工具
打开浏览器 → 手机抖音扫码登录 → 自动提取 Cookie → 输出 JSON

用法:
    python get_cookies.py

登录成功后 Cookie 会打印到终端并保存到 cookies.json 文件。
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
    print("登录成功后会自动提取 Cookie。")
    print()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        # 打开创作者中心登录页
        page.goto("https://creator.douyin.com/")
        print("[*] 浏览器已打开，请扫码登录...")
        print()

        # 等待登录成功（检测 URL 变化或特定元素出现）
        # 登录成功后会跳转到创作者中心主页
        max_wait = 120  # 最多等 2 分钟
        logged_in = False

        for i in range(max_wait):
            time.sleep(1)
            current_url = page.url

            # 登录成功的标志：URL 不再是 login 页面，或页面出现用户头像等元素
            if "login" not in current_url and "passport" not in current_url:
                # 再确认一下：检查是否有用户相关元素
                try:
                    # 创作者中心登录后通常有用户信息区域
                    user_el = page.locator(
                        'xpath=//div[contains(@class, "user") or contains(@class, "avatar") '
                        'or contains(@class, "header-info")]'
                    )
                    if user_el.count() > 0:
                        logged_in = True
                        break
                except Exception:
                    pass

                # URL 已经跳转了，大概率登录成功
                if i > 5:  # 给页面一点加载时间
                    logged_in = True
                    break

            if (i + 1) % 15 == 0:
                print(f"[*] 已等待 {i+1} 秒，仍在等待扫码...")

        if not logged_in:
            print("[!] 等待超时（2分钟），请重试。")
            browser.close()
            sys.exit(1)

        print("[+] 检测到登录成功！正在提取 Cookie...")
        time.sleep(2)  # 等 Cookie 完全写入

        # 提取所有 Cookie
        cookies = context.get_cookies()

        # 只保留 creator.douyin.com 相关的
        douyin_cookies = [
            c for c in cookies
            if "douyin.com" in c.get("domain", "")
        ]

        browser.close()

    if not douyin_cookies:
        print("[!] 未获取到有效 Cookie，请重试。")
        sys.exit(1)

    # 输出
    cookie_json = json.dumps(douyin_cookies, ensure_ascii=False)

    print()
    print("=" * 50)
    print(f"[+] 成功获取 {len(douyin_cookies)} 条 Cookie")
    print("=" * 50)
    print()

    # 保存到文件
    with open("cookies.json", "w", encoding="utf-8") as f:
        f.write(cookie_json)
    print("[+] 已保存到 cookies.json")
    print()

    # 打印到终端（方便直接复制到 GitHub Secrets）
    print("─── Cookie JSON（复制到 GitHub Secret）───")
    print()
    print(cookie_json)
    print()
    print("─── 结束 ───")
    print()
    print("提示：将上面的 JSON 粘贴到 GitHub 仓库的")
    print("Settings → Environments → user-data → Secrets → COOKIES_USER1")


if __name__ == "__main__":
    main()
