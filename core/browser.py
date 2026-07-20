"""
Playwright 浏览器管理
"""

from playwright.sync_api import sync_playwright
from utils.config import get_config
from utils.logger import setup_logger

logger = setup_logger()


def get_browser():
    """启动浏览器，返回 (playwright, browser)"""
    config = get_config()

    pw = sync_playwright().start()

    try:
        browser = pw.chromium.launch(headless=config["headless"])
        logger.info("浏览器启动成功")
        return pw, browser
    except Exception as e:
        logger.error(f"浏览器启动失败: {e}")
        pw.stop()
        raise
