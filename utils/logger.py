import logging
import os
from datetime import datetime


def setup_logger(level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("spark_ai")
    if logger.handlers:
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
