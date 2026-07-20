"""
DouYinSparkAI - 抖音智能续火花
自动检测好友消息，AI 生成个性化回复，维持火花不断
"""

import sys
import traceback

from core.browser import get_browser
from core.chat import navigate_to_chat, process_friend
from utils.config import get_config, get_tasks
from utils.logger import setup_logger


def main():
    config = get_config()
    logger = setup_logger(level=config["log_level"])

    tasks = get_tasks()
    if not tasks:
        logger.error("未找到有效任务配置，请检查 TASKS 和 COOKIES_* 环境变量")
        sys.exit(1)

    logger.info(f"共 {len(tasks)} 个账号待处理")

    pw, browser = get_browser()

    try:
        for user in tasks:
            username = user["username"]
            targets = user["targets"]
            logger.info(f"═══ 账号: {username} | 目标好友: {targets} ═══")

            context = browser.new_context()
            context.set_default_navigation_timeout(config["browser_timeout"])
            context.set_default_timeout(config["browser_timeout"])
            page = context.new_page()

            try:
                navigate_to_chat(page, user["cookies"], config)

                for friend in targets:
                    try:
                        process_friend(page, friend, config)
                    except Exception as e:
                        logger.error(f"处理好友 {friend} 出错: {e}")
                        traceback.print_exc()
                        continue

            except Exception as e:
                logger.error(f"账号 {username} 任务失败: {e}")
                traceback.print_exc()
            finally:
                context.close()

    finally:
        browser.close()
        pw.stop()

    logger.info("全部任务完成")


if __name__ == "__main__":
    main()
