"""`init` 子命令：一次性配置初始化。"""
import sys
import time
import uuid
import random
from datetime import datetime, time as dtime

from ..api.client import ApiClient
from ..api import login as api_login
from ..api import points as api_points
from ..api import campus_loop as api_loop
from ..api import policy as api_policy
from ..config import (
    load_identity, save_identity, load_config, save_config,
    set_amap_key, get_amap_key, clear_loop_cache, DATA_DIR,
)
from ..logger import ok, err, warn, step, dim


def _prompt(label, default="", secret=False):
    suffix = f" [{default}]" if default else ""
    try:
        if secret:
            import getpass
            val = getpass.getpass(f"  {label}{suffix}: ").strip()
        else:
            val = input(f"  {label}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(1)
    return val or default


def _prompt_choice(label, options, default=0):
    print(f"  {label}")
    for i, opt in enumerate(options):
        print(f"    [{chr(ord('a') + i)}] {opt}")
    while True:
        raw = _prompt("选择", chr(ord('a') + default)).lower()
        idx = ord(raw) - ord('a') if len(raw) == 1 else -1
        if 0 <= idx < len(options):
            return idx
        warn("输入无效，请重试")


def cmd_init(args):
    print()
    print("=" * 60)
    print("FunSportWorld 初始化")
    print("=" * 60)
    print()

    arg_user = getattr(args, "user", None)
    arg_pass = getattr(args, "pass_", None)
    arg_city = getattr(args, "city", None)
    arg_lat = getattr(args, "lat", None)
    arg_lng = getattr(args, "lng", None)
    arg_key = getattr(args, "key", None)
    arg_device = getattr(args, "device", None)
    arg_before_min = getattr(args, "before_min", 30) or 30
    arg_before_max = getattr(args, "before_max", 300) or 300

    non_interactive = bool(arg_user and arg_pass)
    cfg = load_config()
    idn = load_identity()

    # 1. 账号
    step("[1/6] 账号")
    if non_interactive:
        username, password = arg_user, arg_pass
        print(f"  手机号: {username}")
        print(f"  密码:   {'*' * len(password)}")
    else:
        username = _prompt("手机号", cfg.get("username", ""))
        if not username:
            err("手机号不能为空")
            sys.exit(1)
        password = _prompt("密码", "", secret=True)
        if not password:
            err("密码不能为空")
            sys.exit(1)
    print()

    # 2. 学校位置
    step("[2/6] 学校位置")
    if arg_city:
        city = arg_city
        lat = float(arg_lat) if arg_lat else None
        lng = float(arg_lng) if arg_lng else None
        print(f"  城市: {city}")
        print(f"  坐标: {lat}, {lng}" if lat is not None else "  坐标: 稍后自动拉取")
    else:
        city = _prompt("城市（市级，如「成都市」）", cfg.get("city", "成都市"))
        raw = _prompt("坐标（可选，留空自动拉取）", "")
        if raw:
            try:
                lat_s, lng_s = raw.replace("，", ",").split(",")
                lat, lng = float(lat_s.strip()), float(lng_s.strip())
            except Exception:
                warn("坐标格式错误，稍后自动拉取")
                lat = lng = None
        else:
            lat = lng = None
    print()

    # 3. 提交时间提前量
    step("[3/6] 提交时间提前量（分钟）")
    if non_interactive:
        bmin = int(arg_before_min)
        bmax = int(arg_before_max)
        if bmax < bmin:
            bmin, bmax = bmax, bmin
        print(f"  提前 {bmin}~{bmax} 分钟")
    else:
        raw = _prompt("最短提前（分钟）", str(cfg.get("start_before_min", 30)))
        try:
            bmin = max(1, int(raw))
        except ValueError:
            bmin = 30
        raw2 = _prompt("最长提前（分钟）", str(cfg.get("start_before_max", 300)))
        try:
            bmax = max(1, int(raw2))
        except ValueError:
            bmax = 300
        if bmax < bmin:
            bmin, bmax = bmax, bmin
        print(f"  → 提前 {bmin}~{bmax} 分钟" + ("（固定）" if bmin == bmax else ""))
    print()

    # 4. 高德 Key
    step("[4/6] 高德 Key（用于生成校园环，可留空）")
    current_key = get_amap_key()
    if arg_key is not None:
        amap_key = arg_key
        print(f"  Key: {amap_key[:8]}…" if amap_key else "  Key: 不配置")
    else:
        hint = f"{current_key[:8]}…" if current_key else "未配置"
        amap_key = _prompt(f"LBS Key（当前：{hint}）", "")
    print()

    # 5. 设备身份
    step("[5/6] 设备身份")
    if arg_device == "new":
        device_choice = 0
    elif arg_device == "keep":
        device_choice = 1
    elif non_interactive:
        device_choice = 1
    else:
        device_choice = _prompt_choice(
            "选择设备身份",
            [
                "随机生成新设备（会改变 device_id，可能触发风控）",
                f"保留现有设备（device_id={idn.get('device_id', '')[:13]}…）",
            ],
            default=1,
        )
    if device_choice == 0:
        idn["device_id"] = str(uuid.uuid4()).upper()
        idn["app_install_time"] = int(time.time() * 1000) - 3 * 86400_000
        idn["mac_address"] = ":".join(f"{random.randint(0, 255):02x}" for _ in range(6))
        ok("已生成新设备身份")
    else:
        dim(f"保留 device_id={idn.get('device_id', '')}")
    print()

    # 6. 保存与验证
    step("[6/6] 保存与验证")

    cfg["username"] = username
    cfg["password"] = password
    cfg["remember"] = True
    cfg["city"] = city
    cfg["start_before_min"] = bmin
    cfg["start_before_max"] = bmax
    if lat is not None:
        idn["anchor_lat"] = lat
        idn["anchor_lon"] = lng
    idn["city"] = city
    save_config(cfg)
    save_identity(idn)
    ok(f"配置已写入 {DATA_DIR}")

    if amap_key:
        set_amap_key(amap_key)
        ok(f"高德 Key 已写入：{amap_key[:8]}…")

    print()
    step("  登录测试…")
    client = ApiClient(idn, None)
    try:
        sess = api_login.login(client, username, password)
    except Exception as e:
        err(f"登录失败：{e}")
        sys.exit(1)
    ok(f"登录成功 uid={sess['uid']} name={sess['name']}")
    client.session_data = sess

    # 坐标自动拉取
    print()
    if lat is None:
        step("  拉取学校坐标（从打卡点推算）…")
        try:
            pts = api_points.fetch_points(client)
        except Exception as e:
            warn(f"拉取打卡点失败：{e}")
            pts = []
        if pts:
            lat_list = [p["lat"] for p in pts if p.get("lat") is not None]
            lng_list = [p["lon"] for p in pts if p.get("lon") is not None]
            if lat_list and lng_list:
                idn["anchor_lat"] = round(sum(lat_list) / len(lat_list), 6)
                idn["anchor_lon"] = round(sum(lng_list) / len(lng_list), 6)
                save_identity(idn)
                ok(f"坐标已获取：({idn['anchor_lat']}, {idn['anchor_lon']})")
            else:
                warn("打卡点无坐标字段")
        else:
            warn("打卡点为空，跳过坐标获取")
    else:
        dim(f"坐标已手动配置：({lat}, {lng})")

    # 环生成
    print()
    if amap_key:
        step("  生成校园环（高德）…")
        try:
            clear_loop_cache()
            pts = api_points.fetch_points(client)
            if pts:
                ring = api_loop.get_campus_loop(pts, force_rebuild=True)
                if ring:
                    ok(f"环已生成：{len(ring)} 点")
                else:
                    warn("环生成失败")
            else:
                warn("打卡点为空，跳过环生成")
        except Exception as e:
            warn(f"环生成失败：{e}")
    else:
        dim("未配置高德 Key，跳过校园环生成")

    # 时间窗口信息
    print()
    try:
        pol = api_policy.fetch_policy(client)
        if pol.valid_time:
            step("  时间窗口")
            for w in pol.valid_time:
                print(f"    {w.get('start')} ~ {w.get('end')}")
            now_t = datetime.now().time()
            inside = False
            for w in pol.valid_time:
                try:
                    ws = dtime.fromisoformat(w["start"])
                    we = dtime.fromisoformat(w["end"])
                    if ws <= now_t <= we:
                        inside = True
                        break
                except Exception:
                    continue
            if inside:
                ok("当前时间在窗口内，可以直接 run")
            else:
                warn("当前时间不在窗口内，run 会被拒绝（可加 --allow-outside 强制）")
        else:
            dim("policy 未返回时间窗口")
    except Exception as e:
        warn(f"拉取时间窗口失败：{e}")

    print()
    print("=" * 60)
    ok("初始化完成")
    print()
    print("下一步：")
    print("  python -m funsport run --auto           # 自动跑一次")
    print("  python -m funsport points               # 查看打卡点")
    print("  python -m funsport config               # 查看配置")
    print()