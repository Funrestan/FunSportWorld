"""全局常量与本地持久化。"""
import json
import os
import time
import uuid
import random
from pathlib import Path

HOST = "https://run.gxapp.iydsj.com"
DISCOVERY = "https://discovery.gxapp.iydsj.com"


def _find_data_dir() -> Path:
    """定位 .funsport 目录。

    优先级：
    1. 环境变量 FUNSPORT_DATA_DIR
    2. 从当前文件向上找项目根（含 .git 或 funsport/ 子目录）
    3. cwd/.funsport
    """
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
    "amap_key": "",
    # ── auto 模式参数 ──
    "auto_dist_extra_min": 0.10,   # 学校要求 × (1+0.10) 起
    "auto_dist_extra_max": 0.30,   # 学校要求 × (1+0.30) 止
    "auto_pace_min_s": 360,        # 6'00"/km
    "auto_pace_max_s": 480,        # 8'00"/km
    "auto_cadence_min": 130,       # 步频下限 spm
    "auto_cadence_max": 170,       # 步频上限 spm
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


def set_config(**kwargs):
    """批量更新配置项（只更新已存在的键）。"""
    cfg = load_config()
    n = 0
    for k, v in kwargs.items():
        if v is None:
            continue
        if k in cfg:
            try:
                # 数值字段自动转类型
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