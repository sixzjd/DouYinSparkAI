"""
抖音登录态获取工具
保存完整浏览器状态（Cookie + localStorage），确保 CI 能复现登录

注意：创作者中心的登录是页面内嵌扫码面板（不跳转 URL），
所以必须靠"登录表单消失"来判断登录成功，不能靠 URL。
"""

import json
import time
import sys

from playwright.sync_api import sync_playwright
from utils.state_utils import slim_state

# 登录面板的特征（出现任意一个 = 还没登录）
LOGIN_FORM_SELECTORS = [
    'input[placeholder*="手机号"]',
    'input[placeholder*="验证码"]',
    'text=扫码登录',
    'text=登录/注册',
]


def is_login_page(page) -> bool:
    """页面是否还处于登录状态（登录面板可见）"""
    for sel in LOGIN_FORM_SELECTORS:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                return True
        except Exception:
            continue
    return False


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

        page.goto("https://creator.douyin.com/", wait_until="domcontentloaded", timeout=30000)
        print("[*] 请扫码登录...（登录后会自动检测，无需其他操作）")

        # ── 等待登录：登录面板消失才算成功（最长 3 分钟） ──
        logged_in = False
        for i in range(180):
            time.sleep(1)
            if not is_login_page(page):
                # 面板消失后再等几秒确保登录态完全写入
                time.sleep(6)
                if not is_login_page(page):
                    logged_in = True
                    break
            if (i + 1) % 20 == 0:
                print(f"[*] 等待扫码中... {i+1}s")

        if not logged_in:
            print("[!] 超时：未检测到登录成功")
            browser.close()
            sys.exit(1)

        print("[+] 登录成功！")

        # ── 访问多个关键页面，确保各域 session cookie 完全写入 ──
        print("[*] 访问 www.douyin.com 写入主域 session cookie...")
        page.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=30000)
        time.sleep(5)

        print("[*] 访问创作者中心私信页...")
        page.goto(
            "https://creator.douyin.com/creator-micro/data/following/chat",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        time.sleep(6)

        # ── 抓取前自检：确认此刻登录态确实有效 ──
        if is_login_page(page):
            print("[!] 警告: 私信页仍显示登录面板，登录态可能未生效")
        else:
            print("[+] 私信页已登录，登录态有效")

        # ── 用 CDP 获取全部 cookie（含 httpOnly，不受域过滤影响） ──
        cdp = context.new_cdp_session(page)
        cdp_cookies = cdp.send("Network.getAllCookies").get("cookies", [])
        print(f"[*] CDP 获取到 {len(cdp_cookies)} 条 cookie")

        # ── 同时拿 storage_state（含 localStorage） ──
        state = context.storage_state()
        browser.close()

    # ── 合并：以 CDP cookie 为准（更全），补上 storage_state 的 localStorage ──
    ss_by_key = {}
    for c in state.get("cookies", []):
        ss_by_key[(c["name"], c.get("domain", ""))] = c

    for c in cdp_cookies:
        key = (c["name"], c.get("domain", ""))
        ss_by_key[key] = c  # CDP 覆盖 storage_state

    all_cookies = list(ss_by_key.values())
    state["cookies"] = all_cookies

    # 保存完整状态（本地备份，体积大，不用于 CI）
    with open("auth_state_full.json", "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)

    # ── 精简版：只保留 cookie + 安全相关 localStorage ──
    # 完整版约 170KB，超过 GitHub Secret 64KB 限制；
    # 大部分体积是遥测/布局数据，对登录和发消息签名没有用。
    slim = slim_state(state)
    slim_origins = slim.get("origins", [])
    with open("auth_state.json", "w", encoding="utf-8") as f:
        json.dump(slim, f, ensure_ascii=False)

    # 同时保存纯 cookie（兼容旧格式）
    douyin_cookies = [c for c in all_cookies if "douyin" in c.get("domain", "")]
    for c in douyin_cookies:
        c.pop("sameSite", None)

    with open("cookies.json", "w", encoding="utf-8") as f:
        json.dump(douyin_cookies, f, ensure_ascii=False)

    # ── 报告 ──
    import os
    cookie_names = [c["name"] for c in douyin_cookies]
    ls_count = sum(len(o.get("localStorage", [])) for o in slim_origins)
    slim_kb = os.path.getsize("auth_state.json") / 1024

    print()
    print(f"[+] Cookie 总计: {len(all_cookies)} 条 (douyin 域: {len(douyin_cookies)} 条)")
    print(f"[+] 安全 localStorage: {ls_count} 项")
    print(f"[+] auth_state.json 大小: {slim_kb:.1f} KB (GitHub Secret 限制 64KB)")
    if slim_kb > 60:
        print("[!] 警告: 体积接近 Secret 上限，请检查")
    print()
    print("[+] 已保存:")
    print("    auth_state.json      ← 精简版（粘贴到 CI 用这个）")
    print("    auth_state_full.json ← 完整版（本地备份）")
    print("    cookies.json         ← 纯 cookie（备用）")
    print()
    print("─── 将 auth_state.json 的内容粘贴到 GitHub Secret (COOKIES_USER1) ───")


if __name__ == "__main__":
    main()
