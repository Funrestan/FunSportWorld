"""GUI 的配置、参数校验和业务适配层；不依赖 Tk 控件。"""
import json
import math
import re
from datetime import datetime

from . import config
from .diagnostics import analyze_checkpoints


def read_object(path):
    """严格读取本地对象；文件损坏时拒绝以默认值覆盖原数据。"""
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (ValueError, OSError, UnicodeError) as exc:
        raise ValueError(path.name + " 无法读取，请先检查或备份原文件") from exc
    if not isinstance(value, dict):
        raise ValueError(path.name + " 必须是 JSON 对象，已保留原文件")
    return value


def number(value, label, low, high, integer=False):
    """把表单文本转为有限数值，并验证范围和整数要求。"""
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        raise ValueError(label + " 必须是数字") from None
    if not math.isfinite(parsed) or not low <= parsed <= high:
        raise ValueError("{} 必须在 {} 到 {} 之间".format(label, low, high))
    if integer and parsed != int(parsed):
        raise ValueError(label + " 必须是整数")
    return int(parsed) if integer else parsed


def settings_snapshot():
    """读取界面需要的配置；密码、地图 Key 和会话令牌不回填输入框。"""
    cfg = dict(config.DEFAULT_CONFIG, **read_object(config.CONFIG_FILE))
    identity = read_object(config.IDENTITY_FILE)
    session = read_object(config.SESSION_FILE)
    return {"username": cfg.get("username", ""), "password": "", "amap_key": "",
            "city": cfg.get("city", ""), "remember": bool(cfg.get("remember")),
            "diagnostic_capture": bool(cfg.get("diagnostic_capture", False)),
            "anchor_lat": str(identity.get("anchor_lat", "")),
            "anchor_lon": str(identity.get("anchor_lon", "")),
            "start_before_min": str(cfg["start_before_min"]),
            "start_before_max": str(cfg["start_before_max"]),
            "has_password": bool(cfg.get("password")),
            "has_amap_key": bool(config.get_amap_key()),
            "logged_in": bool(session.get("uid") and session.get("token"))}


def save_settings(values):
    """校验并合并设置；换账号前须退出服务器，避免丢弃仍有效的会话。"""
    cfg = dict(config.DEFAULT_CONFIG, **read_object(config.CONFIG_FILE))
    identity = read_object(config.IDENTITY_FILE)
    username = values.get("username", "").strip()
    city = values.get("city", "").strip()
    if not city:
        raise ValueError("城市不能为空")
    low = number(values["start_before_min"], "最短提前", 1, 4320, True)
    high = number(values["start_before_max"], "最长提前", 1, 4320, True)
    if high < low:
        raise ValueError("最长提前不能小于最短提前")
    lat, lon = values.get("anchor_lat", "").strip(), values.get("anchor_lon", "").strip()
    if bool(lat) != bool(lon):
        raise ValueError("纬度和经度必须同时填写或同时留空")
    coordinates = {}
    if lat:
        coordinates = {"anchor_lat": number(lat, "纬度", -90, 90),
                       "anchor_lon": number(lon, "经度", -180, 180)}
    changed_user = username != cfg.get("username", "")
    if changed_user:
        session = read_object(config.SESSION_FILE)
        current_username = session.get("username") or cfg.get("username", "")
        if session and username != current_username:
            raise ValueError("切换账号前请先点击“退出登录”，等待服务器确认退出；旧设置和会话已保留")
    changed_campus = city != cfg.get("city") or any(
        identity.get(key) != coordinates.get(key) for key in ("anchor_lat", "anchor_lon"))
    cfg.update(username=username, city=city, start_before_min=low,
               start_before_max=high, remember=bool(values.get("remember")),
               diagnostic_capture=bool(values.get("diagnostic_capture", False)))
    password = values.get("password", "")
    if not cfg["remember"] or changed_user:
        cfg["password"] = ""
    if cfg["remember"] and password:
        if not username:
            raise ValueError("保存密码前必须填写账号")
        cfg["password"] = password
    key = values.get("amap_key", "").strip()
    if values.get("clear_amap"):
        cfg["amap_key"] = ""
    elif key:
        cfg["amap_key"] = key
    for coordinate in ("anchor_lat", "anchor_lon"):
        identity.pop(coordinate, None)
    identity.update(coordinates)
    identity["city"] = city
    config.save_identity(identity)
    config.save_config(cfg)
    if changed_user or changed_campus:
        config.POINTS_CACHE.unlink(missing_ok=True)
        config.clear_loop_cache()
    snapshot = settings_snapshot()
    snapshot["reset_views"] = changed_user or changed_campus
    return snapshot


def login_account(username, password):
    """只为匹配账号使用保存密码；切换登录账号前须先完成服务器退出。"""
    from .api.client import ApiClient
    from .api.login import login
    cfg = read_object(config.CONFIG_FILE)
    username = username.strip()
    if not username:
        raise ValueError("请填写账号")
    if not password and username == cfg.get("username") and cfg.get("remember"):
        password = cfg.get("password", "")
    if not password:
        raise ValueError("请填写密码，或先保存记住密码设置")
    old = read_object(config.SESSION_FILE)
    current_username = old.get("username") or cfg.get("username")
    if old and username != current_username:
        raise ValueError("登录其他账号前请先退出当前账号；本地旧会话已保留")
    read_object(config.IDENTITY_FILE)
    client = ApiClient(config.load_identity())
    try:
        session = login(client, username, password)
    finally:
        client.http.close()
    if old.get("uid") != session.get("uid"):
        config.POINTS_CACHE.unlink(missing_ok=True)
        config.clear_loop_cache()
    return "登录成功"


def with_client(action):
    """为单个后台任务创建独立客户端；无会话时不偷偷触发自动登录。"""
    from .api.client import ApiClient
    session = read_object(config.SESSION_FILE)
    if not session.get("uid") or not session.get("token"):
        raise ValueError("没有可用会话，请到设置页登录")
    read_object(config.IDENTITY_FILE)
    client = ApiClient(config.load_identity(), session)
    try:
        return action(client)
    finally:
        client.http.close()


def logout_account():
    """用已有会话调用服务端退出并释放连接，不自动登录或降级为本地退出。"""
    from .api.login import logout
    return with_client(logout)


def run_parameters(values):
    """验证跑步表单，转换成方案生成参数，时间外测试默认关闭。"""
    auto = bool(values.get("auto"))
    params = {"auto": auto, "use_map": True,
              "allow_outside_window": bool(values.get("allow_outside", False)),
              "seed": number(values.get("seed", 0), "随机种子", 0, 2147483647, True)}
    if not auto:
        params.update(dist=number(values.get("dist"), "距离 km", 0.1, 99),
                      pace=number(values.get("pace"), "配速 秒/km", 160, 520),
                      cadence=number(values.get("cadence"), "步频", 60, 220))
    mode = values.get("time_mode", "config")
    if mode == "before":
        params["before"] = number(values.get("before"), "提前分钟", 1, 4320, True)
    elif mode == "at":
        try:
            start = datetime.strptime(values.get("start_at", ""), "%Y-%m-%d %H:%M")
        except ValueError:
            raise ValueError("开始时间格式应为 YYYY-MM-DD HH:MM") from None
        age = (datetime.now() - start).total_seconds()
        if not 0 <= age <= 3 * 86400:
            raise ValueError("开始时间必须在过去三天内")
        params["start_ms"] = int(start.timestamp() * 1000)
    elif mode != "config":
        raise ValueError("未知开始时间模式")
    return params


def fetch_record_report(rrid):
    """查询指定记录并只返回诊断统计，不把原始响应交给界面。"""
    from .api.records import fetch_one_record
    return with_client(lambda client: analyze_checkpoints(fetch_one_record(client, rrid)))


def safe_text(text, secrets=()):
    """删除日志中的常见凭据、手机号码和 URL 查询串。"""
    text = re.sub(r"\x1b\[[0-9;]*m", "", str(text))
    for secret in sorted((str(s) for s in secrets if s), key=len, reverse=True):
        text = text.replace(secret, "[已隐藏]")
    text = re.sub(r"(?i)((?:password|passToken|captchaOutput|lotNumber|genTime|geeToken|token|authorization|amap_key|secret|originalSign|signature|device_id)[\"']?\s*[:=]\s*)[^,}\n]+",
                  r"\1[已隐藏]", text)
    text = re.sub(r"(https?://[^?\s]+)\?[^\s]+", r"\1?[已隐藏]", text)
    return re.sub(r"\b1[3-9]\d{9}\b", "[手机号]", text)
