from __future__ import annotations

import logging
import os
from logging.handlers import TimedRotatingFileHandler


LOG_DIR = os.environ.get('LOG_DIR', '/app/logs')
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')


def setup_logging() -> None:
    os.makedirs(LOG_DIR, exist_ok=True)

    fmt = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    file_handler = TimedRotatingFileHandler(
        os.path.join(LOG_DIR, 'app.log'),
        when='midnight',
        interval=1,
        backupCount=30,
        encoding='utf-8',
    )
    file_handler.setFormatter(fmt)
    file_handler.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)
    console_handler.setLevel(logging.WARNING)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(file_handler)
    root.addHandler(console_handler)
