"""
配置管理 - 从环境变量读取所有配置
GitHub Actions 中通过 Settings > Secrets and variables 设置
"""

import json
import os


def get_config() -> dict:
    """读取全局配置"""
    return {
        # AI 配置
        # provider: "openai"(默认, 兼容所有 OpenAI 格式的中转站) 或 "anthropic"
        "ai_provider": os.getenv("AI_PROVIDER", "openai").lower(),
        "ai_base_url": os.getenv("AI_BASE_URL", "https://api.deepseek.com"),
        "ai_api_key": os.getenv("AI_API_KEY", ""),
        "ai_model": os.getenv("AI_MODEL", "deepseek-chat"),
        # 浏览器配置
        "browser_timeout": int(os.getenv("BROWSER_TIMEOUT", "120000")),
        "headless": os.getenv("HEADLESS", "true").lower() == "true",
        # 任务配置
        "task_retry_times": int(os.getenv("TASK_RETRY_TIMES", "3")),
        "log_level": os.getenv("LOG_LEVEL", "INFO"),
        # 好友匹配模式: nickname / short_id
        "match_mode": os.getenv("MATCH_MODE", "nickname"),
    }


def get_tasks() -> list[dict]:
    """
    读取任务列表
    环境变量 TASKS 格式:
    [
      {"username": "昵称", "unique_id": "user1", "targets": ["好友A"]}
    ]
    登录态存在 COOKIES_{UNIQUE_ID} 环境变量中 (大写)。
    支持两种格式:
      1. storage_state 完整状态: {"cookies": [...], "origins": [...]}  (推荐)
      2. 纯 cookie 数组: [...]  (兼容旧版)
    """
    tasks_raw = os.getenv("TASKS", "[]")
    tasks = json.loads(tasks_raw)

    result = []
    for task in tasks:
        uid = task.get("unique_id", "")
        if not uid:
            continue

        cookie_key = f"COOKIES_{uid.upper()}"
        cookie_str = os.getenv(cookie_key, "")
        if not cookie_str:
            continue

        try:
            data = json.loads(cookie_str)
        except json.JSONDecodeError:
            continue

        # 判断格式
        if isinstance(data, dict) and "cookies" in data:
            # storage_state 完整状态格式
            storage_state = data
            cookies = data.get("cookies", [])
        else:
            # 纯 cookie 数组格式
            storage_state = None
            cookies = data

        # 清理 Playwright 不支持的字段
        for c in cookies:
            c.pop("sameSite", None)

        result.append({
            "unique_id": uid,
            "username": task.get("username", "未知用户"),
            "cookies": cookies,
            "storage_state": storage_state,
            "targets": task.get("targets", []),
        })

    return result
