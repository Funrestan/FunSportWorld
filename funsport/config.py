"""全局常量与本地持久化。"""
import json
import os
import time
import uuid
import random
from pathlib import Path

HOST = "https://run.gxapp.iydsj.com"
DISCOVERY = "https://discovery.gxapp.iydsj.com"

DATA_DIR = Path(os.getcwd()) / ".funsport"
DATA_DIR.mkdir(exist_ok=True)

IDENTITY_FILE = DATA_DIR / "identity.json"
SESSION_FILE  = DATA_DIR / "session.json"
CONFIG_FILE   = DATA_DIR / "config.json"
POINTS_CACHE  = DATA_DIR / "points_cache.json"
AI_SPORTS     = DATA_DIR / "ai_sports.json"

POINTS_TTL_MS = 300_000


def load_json(path: Path, default=None):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


# ── 设备身份 ────────────────────────────────────────────────
def load_identity() -> dict:
    idn = load_json(IDENTITY_FILE) or {}
    dirty = False
    if not idn.get("device_id"):
        idn["device_id"] = str(uuid.uuid4()).upper()
        dirty = True
    if not idn.get("app_install_time"):
        days = 90 if idn.get("platform") == "android" else 3
        idn["app_install_time"] = int(time.time() * 1000) - days * 86400_000
        dirty = True
    if not idn.get("mac_address"):
        idn["mac_address"] = ":".join(f"{random.randint(0, 255):02x}" for _ in range(6))
        dirty = True
    idn.setdefault("platform", "ios")
    idn.setdefault("os_version", "26.5.2")
    idn.setdefault("device_name", "iPhone")
    idn.setdefault("anchor_lat", 38.901678)
    idn.setdefault("anchor_lon", 121.540241)
    idn.setdefault("city", "大连市")
    idn.setdefault("idfa", "")
    if dirty:
        save_json(IDENTITY_FILE, idn)
    return idn


def save_identity(idn: dict):
    save_json(IDENTITY_FILE, idn)


# ── 会话 ────────────────────────────────────────────────────
def load_session() -> dict:
    return load_json(SESSION_FILE) or {}

def save_session(s: dict):
    save_json(SESSION_FILE, s)

def clear_session():
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()


# ── 配置 ────────────────────────────────────────────────────
DEFAULT_CONFIG = {
    "username": "",
    "password": "",
    "remember": False,
    "dist_min": 1.0,
    "dist_max": 1.5,
    "pace_min": 360,
    "pace_max": 480,
    "face_check": True,
    "amap_key": "",            # 高德 Key（lbs-amap 写入）
}


def load_config() -> dict:
    cfg = load_json(CONFIG_FILE) or {}
    for k, v in DEFAULT_CONFIG.items():
        cfg.setdefault(k, v)
    return cfg

def save_config(c: dict):
    save_json(CONFIG_FILE, c)


def get_amap_key() -> str:
    """优先级：环境变量 FUNSPORT_AMAP_KEY > config.json > 空。"""
    env = os.environ.get("FUNSPORT_AMAP_KEY", "").strip()
    if env:
        return env
    cfg = load_config()
    return (cfg.get("amap_key") or "").strip()


def set_amap_key(key: str):
    cfg = load_config()
    cfg["amap_key"] = key
    save_config(cfg)


def clear_loop_cache():
    """删除环缓存（下次 --use-map 强制重新生成）。"""
    p = DATA_DIR / "campus_loop_bd.json"
    if p.exists():
        p.unlink()
        return True
    return False


# ── 缓存 ────────────────────────────────────────────────────
def load_points_cache():
    v = load_json(POINTS_CACHE)
    if not v:
        return None
    return v.get("ts"), v.get("points", [])

def save_points_cache(points):
    save_json(POINTS_CACHE, {"ts": int(time.time() * 1000), "points": points})


def load_ai_sports():
    return load_json(AI_SPORTS) or []

def save_ai_sports(lst):
    save_json(AI_SPORTS, lst)