"""日志配置——按天轮转，保留 7 天。"""

import logging
import os
from logging.handlers import TimedRotatingFileHandler

_LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs")


def init_logging():
    os.makedirs(_LOG_DIR, exist_ok=True)
    handler = TimedRotatingFileHandler(
        os.path.join(_LOG_DIR, "app.log"),
        when="midnight",
        backupCount=0,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.DEBUG)


init_logging()
