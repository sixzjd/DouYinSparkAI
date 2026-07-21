"""
登录态瘦身工具
完整 storage_state 约 170KB（大量遥测/布局数据），超过 GitHub Secret 64KB 限制。
实际上只有 cookie + 安全相关 localStorage 是登录和发消息签名所必需的，
瘦身后约 30KB，可安全存入 Secret。
"""

# 需要保留的 localStorage 键（安全/签名相关）
KEEP_KEYS = ("security-sdk/", "web_secsdk", "xmst", "LOGIN_STATUS", "csrf")


def slim_state(state: dict) -> dict:
    """
    瘦身 storage_state：保留全部 cookie，localStorage 只留安全相关项。
    :param state: context.storage_state() 的返回值（含 cookies + origins）
    :return: 瘦身后的 {"cookies": [...], "origins": [...]}
    """
    slim_origins = []
    for origin in state.get("origins", []):
        kept = [
            it for it in origin.get("localStorage", [])
            if any(k in it["name"] for k in KEEP_KEYS)
        ]
        if kept:
            slim_origins.append({"origin": origin["origin"], "localStorage": kept})
    return {"cookies": state.get("cookies", []), "origins": slim_origins}
