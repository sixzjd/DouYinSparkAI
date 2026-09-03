import logging
import os
from datetime import datetime


def setup_logger(level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("spark_ai")

    # 首次调用（通常是模块 import 时）初始化 handler；
    # 已初始化过则只同步级别，保证 main() 传入的 LOG_LEVEL 能生效
    if logger.handlers:
        logger.setLevel(getattr(logging, level.upper(), logging.INFO))
        return logger

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)s %(message)s", datefmt="%H:%M:%S"
    )

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    os.makedirs("logs", exist_ok=True)
    fh = logging.FileHandler(
        f"logs/{datetime.now().strftime('%Y-%m-%d')}.log", encoding="utf-8"
    )
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger
