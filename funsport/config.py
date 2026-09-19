"""全局常量与本地持久化。"""
import json
import os
import time
import uuid
import random
import tempfile
from pathlib import Path

HOST = "https://run.gxapp.iydsj.com"
DISCOVERY = "https://discovery.gxapp.iydsj.com"


def _find_data_dir() -> Path:
    """定位 .funsport 目录。"""
    env = os.environ.get("FUNSPORT_DATA_DIR", "").strip()
    if env:
        p = Path(env).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    here = Path(__file__).resolve()
    for parent in [here.parent] + list(here.parents):
        if (parent / ".git").exists() or (parent / "funsport").is_dir():
            p = parent / ".funsport"
            p.mkdir(exist_ok=True)
            return p
        if parent.name == "funsport":
            p = parent.parent / ".funsport"
            p.mkdir(exist_ok=True)
            return p

    p = Path(os.getcwd()) / ".funsport"
    p.mkdir(exist_ok=True)
    return p


DATA_DIR = _find_data_dir()

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
    """先完整写入同目录临时文件，再原子替换，避免配置只写了一半。"""
    path = Path(path)
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                         dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


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
    idn.setdefault("city", "成都市")
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
    "amap_key": "",
    "city": "成都市",

    # ── 开始时间提前量（分钟）──
    "start_before_min": 30,
    "start_before_max": 300,

    # ── auto 模式参数 ──
    "auto_dist_extra_min": 0.10,
    "auto_dist_extra_max": 0.30,
    "auto_pace_min_s": 360,
    "auto_pace_max_s": 480,
    "auto_cadence_min": 130,
    "auto_cadence_max": 170,
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


def get_city() -> str:
    """优先级：config.json > identity.json > 默认。"""
    cfg = load_config()
    c = (cfg.get("city") or "").strip()
    if c:
        return c
    idn = load_identity()
    return (idn.get("city") or "成都市").strip()


def get_start_before_range() -> tuple:
    """返回 (min, max) 分钟。保证 min <= max，且都 >= 1。"""
    cfg = load_config()
    bmin = max(1, int(cfg.get("start_before_min", 30)))
    bmax = max(bmin, int(cfg.get("start_before_max", 300)))
    return bmin, bmax


def set_start_before(minutes: int, max_minutes: int = None):
    """设置提交时间提前量（分钟）。max 缺省 = min（固定）。"""
    cfg = load_config()
    cfg["start_before_min"] = int(minutes)
    cfg["start_before_max"] = int(max_minutes if max_minutes is not None else minutes)
    save_config(cfg)


def clear_loop_cache():
    """删除环缓存（下次 --use-map 强制重新生成）。"""
    p = DATA_DIR / "campus_loop_bd.json"
    if p.exists():
        p.unlink()
        return True
    return False


def set_config(**kwargs):
    """批量更新配置项（只更新已存在的键）。"""
    cfg = load_config()
    n = 0
    for k, v in kwargs.items():
        if v is None:
            continue
        if k in cfg:
            try:
                if isinstance(cfg[k], float):
                    cfg[k] = float(v)
                elif isinstance(cfg[k], int):
                    cfg[k] = int(v)
                else:
                    cfg[k] = v
                n += 1
            except (ValueError, TypeError):
                pass
    save_config(cfg)
    return n


# ── 缓存 ────────────────────────────────────────────────────
def load_points_cache(with_metadata=False):
    """兼容旧缓存读取，并按需返回点位、跑区信息和所属账号上下文。"""
    v = load_json(POINTS_CACHE)
    if not isinstance(v, dict) or not v:
        return None
    if with_metadata:
        return v
    return v.get("ts"), v.get("points", [])

def save_points_cache(points, metadata=None, context=None):
    """同时缓存点位和原始跑区信息，避免下一次序列化丢失元数据。"""
    save_json(POINTS_CACHE, {"ts": int(time.time() * 1000), "points": points,
                             "metadata": metadata or {}, "context": context})


def load_ai_sports():
    return load_json(AI_SPORTS) or []

def save_ai_sports(lst):
    save_json(AI_SPORTS, lst)
