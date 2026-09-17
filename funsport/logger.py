"""统一日志：分级 + 彩色 + 分类前缀 + 脱敏。"""
import logging
import sys
from datetime import datetime

COLORS = {
    "ok":   "\033[92m",
    "err":  "\033[91m",
    "warn": "\033[93m",
    "info": "\033[96m",
    "dim":  "\033[90m",
}
RESET = "\033[0m"


class ColorFormatter(logging.Formatter):
    def format(self, record):
        msg = record.getMessage()
        color = RESET
        if msg.startswith("√") or "[ok]" in msg:
            color = COLORS["ok"]
        elif msg.startswith("×") or "[err]" in msg:
            color = COLORS["err"]
        elif msg.startswith("⚠") or "[warn]" in msg:
            color = COLORS["warn"]
        elif msg.startswith("[") or msg.startswith("→") or msg.startswith("←"):
            color = COLORS["info"]
        elif msg.startswith("·"):
            color = COLORS["dim"]
        ts = datetime.now().strftime("%H:%M:%S")
        return f"{COLORS['dim']}{ts}{RESET} {color}{msg}{RESET}"


def get_logger(name: str = "funsport") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(ColorFormatter())
    logger.addHandler(h)
    logger.propagate = False
    return logger


log = get_logger()


def ok(msg):    log.info(f"√ {msg}")
def err(msg):   log.error(f"× {msg}")
def warn(msg):  log.warning(f"⚠ {msg}")
def info(msg):  log.info(f"[{msg}]" if not msg.startswith("[") else msg)
def step(msg):  log.info(f"→ {msg}")
def dim(msg):   log.info(f"· {msg}")


def mask(s: str, keep: int = 6) -> str:
    """日志脱敏。"""
    if not s:
        return "(空)"
    if len(s) <= keep:
        return s
    return s[:keep] + "…" + f"({len(s)}B)"
