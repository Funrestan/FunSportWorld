"""CLI 子命令实现。"""
import argparse
import json
import random
import sys
import time
from datetime import datetime, timedelta

from .mod import (
    make_client, logger, parse_flags, get, fmt_hms, now_ms, jstr, print_rows,
    parse_pace,
)
from ..api.client import ApiClient
from ..config import (
    load_identity, load_session, load_config, save_config,
    save_session, clear_session, get_amap_key, clear_loop_cache,
)
from ..logger import log, ok, err, warn, info


# ── init ────────────────────────────────────────────────────
def cmd_init(args):
    from . import init_cmd
    init_cmd.cmd_init(args)


# ── login / logout ─────────────────────────────────────────
def cmd_login(args):
    from ..api import login as api_login
    identity = load_identity()
    client = ApiClient(identity)

    # 优先用命令行参数，否则从 config.json 读取
    user = getattr(args, "user", None)
    pwd = getattr(args, "pass_", None)

    if not user or not pwd:
        cfg = load_config()
        cfg_user = (cfg.get("username") or "").strip()
        cfg_pass = (cfg.get("password") or "").strip()
        if not cfg_user or not cfg_pass:
            err("未提供账号密码，且 config.json 中没有保存的凭据")
            err("用法：python -m funsport login --user 手机号 --pass 密码")
            err("或先执行：python -m funsport init")
            sys.exit(1)
        user = user or cfg_user
        pwd = pwd or cfg_pass
        ok(f"从 config.json 读取账号：{user}")

    sess = api_login.login(client, user, pwd)

    if getattr(args, "remember", False):
        cfg = load_config()
        cfg["username"] = user
        cfg["password"] = pwd
        cfg["remember"] = True
        save_config(cfg)
        ok("凭据已保存")


def cmd_logout(args):
    """请求服务器退出并释放连接；失败保留会话并让 CLI 返回错误。"""
    from ..api import login as api_login
    sess = load_session()
    if not sess.get("uid") or not sess.get("token"):
        raise ValueError("没有可用会话，无法请求服务器退出；未执行本地清理")
    client = ApiClient(load_identity(), sess)
    try:
        result = api_login.logout(client)
        if not result["local_cleared"]:
            raise RuntimeError(result["message"])
    finally:
        client.http.close()


# ── points / policy ────────────────────────────────────────
def cmd_points(args):
    from ..api import points as api_points
    client = make_client()
    pts = api_points.fetch_points(client)
    log.info(f"共 {len(pts)} 个打卡点：")
    for i, p in enumerate(pts, 1):
        log.info(f"  {i:2}. {p.get('pointName',''):20s} "
                 f"BD=({p.get('lat')},{p.get('lon')})")


def cmd_policy(args):
    from ..api import policy as api_policy
    client = make_client()
    pol = api_policy.fetch_policy(client)
    print(f"policy       = {pol.policy}")
    print(f"min_distance = {pol.min_distance} m")
    print(f"valid_time   = {pol.valid_time}")
    print(f"timestamp    = {pol.timestamp}")


# ── 高德 ────────────────────────────────────────────────────
def cmd_lbs_amap(args):
    from ..config import set_amap_key
    set_amap_key(args.key)
    ok(f"高德 Key 已写入 config.json：{args.key[:8]}…")


def cmd_loop_rebuild(args):
    from ..api import points as api_points
    from ..api import campus_loop as api_loop
    client = make_client()
    clear_loop_cache()
    pts = api_points.fetch_points(client)
    ring = api_loop.get_campus_loop(pts, force_rebuild=True)
    ok(f"环已重建：{len(ring)} 点 → .funsport/campus_loop_bd.json")


# ── config ──────────────────────────────────────────────────
def cmd_config(args):
    cfg = load_config()
    if args.set:
        from ..config import set_config
        updates = {}
        for pair in args.set:
            if "=" not in pair:
                continue
            k, v = pair.split("=", 1)
            updates[k.strip()] = v.strip()
        n = set_config(**updates)
        ok(f"已更新 {n} 项")
        return
    for k in sorted(cfg.keys()):
        v = cfg[k]
        if k == "password" and v:
            v = v[:2] + "***"
        print(f"{k:24s} = {v}")


# ── run ─────────────────────────────────────────────────────
def cmd_run(args):
    """运行现有跑步链，并区分提交完成与详情、打卡点检查状态。"""
    from ..api import flow
    client = make_client()

    before = getattr(args, "before", 0) or 0
    allow_outside = getattr(args, "allow_outside", False)

    if args.time:
        h, m = args.time.split(":")
        base = datetime.now() - timedelta(days=args.days_ago)
        dt = base.replace(hour=int(h) % 24, minute=int(m) % 60,
                          second=0, microsecond=0)
        start_ms = int(dt.timestamp() * 1000)
    elif args.ago:
        start_ms = int(time.time() * 1000) - args.ago * 60_000
    else:
        start_ms = 0

    tag = " / AUTO" if args.auto else (" / 真实路径" if args.use_map else "")
    log.info(f"参数：{tag.strip() or '手动'}")

    result = flow.run_full_flow(
        client,
        dist=args.dist or 0,
        pace=args.pace or 0,
        cadence=args.cadence or 0,
        start_ms=start_ms,
        face_check=1 if args.face else 0,
        seed=args.seed,
        use_map=args.use_map,
        auto=args.auto,
        dist_min=args.dist_min,
        dist_max=args.dist_max,
        pace_min=args.pace_min,
        pace_max=args.pace_max,
        cadence_min=args.cadence_min,
        cadence_max=args.cadence_max,
        min_dist=args.min_dist,
        before=before,
        allow_outside_window=allow_outside,
    )
    print()
    ok(f"记录已提交 rrid={result['rrid']} uuid={result['uuid']}")
    ok(f"距离 {result['dist']:.0f}m / 时长 {result['dur']}s / "
       f"平均步频 {result['cadence_avg']:.0f}spm")
    info(f"OBS {result['obs_ok']}/2 · 详情读取 {'成功' if result['detail_ok'] else '失败'}")
    info("打卡点是否显示仍需以官方 App 为准，详情读取成功不代表打卡验证通过")


# ── AI ──────────────────────────────────────────────────────
def cmd_ai_list(args):
    from ..api import ai as api_ai
    client = make_client()
    lst = api_ai.fetch_list(client)
    for s in lst:
        print(f"id={s['id']:<5} {s['name']}")


def cmd_ai(args):
    from ..api import ai as api_ai
    client = make_client()
    if args.mode == "count":
        mode = api_ai.AiMode.count(args.score)
    else:
        mode = api_ai.AiMode.minutes(args.score)
    api_ai.upload(client, args.sport, mode)


def cmd_ai_records(args):
    from ..api import ai as api_ai
    client = make_client()
    page = api_ai.fetch_records(client, args.sport, 50)
    for g in page["groups"]:
        d = datetime.fromtimestamp(g["score_date"] / 1000).strftime("%Y-%m-%d")
        print(f"{d} ×{g['frequency']}：")
        for r in g["records"]:
            if r["type"] == 2:
                grade = f"{float(r['score'] or 0) / 1000:.1f} 秒"
            else:
                grade = f"{r['score']} 个"
            print(f"  {r['name']} {grade}")


def cmd_ai_info(args):
    from ..api import ai as api_ai
    client = make_client()
    d = api_ai.fetch_record_detail(client, args.id)
    print(json.dumps(d, ensure_ascii=False, indent=2))


# ── records ─────────────────────────────────────────────────
def cmd_records(args):
    from ..api import records as api_records
    client = make_client()
    rows = api_records.fetch_records(client)
    print_rows(rows)


def cmd_record_info(args):
    from ..api import records as api_records
    client = make_client()
    d = api_records.fetch_one_record(client, args.rrid)
    print(json.dumps(d, ensure_ascii=False, indent=2))


# ── semester / cheat / rank ─────────────────────────────────
def cmd_semester(args):
    from ..api import semester as api_semester
    client = make_client()
    r = api_semester.query(client)
    s = r["summary"]
    print(f"学期：{s.sname}")
    print(f"  有效次数：{s.semester_valid_count}/{s.semester_count}")
    print(f"  有效里程：{s.semester_valid_dis/1000:.2f} km")


def cmd_cheat(args):
    from ..api import cheat as api_cheat
    client = make_client()
    r = api_cheat.query(client, args.page)
    if r.is_clean():
        print("自查：干净")
    else:
        print(f"已被标记：{r.self_brief()}")
    print(f"全校违规 {len(r.list)} 条")
    for it in r.list[:20]:
        print(f"  {it.get('name','')} | {it.get('reason','')}")


def cmd_rank(args):
    from ..api import rank as api_rank
    client = make_client()
    if args.kind == "indoor":
        rows = api_rank.indoor_rank(client, args.range or 1)
    elif args.kind == "history":
        rows = api_rank.history_rank(client, args.sort or 1)
    else:
        rows = api_rank.main_rank(client, args.type or 1, args.sort or 1)
    for r in rows:
        print(f"{r['sort']:<4} {r['name']}  {r['length']/1000:.2f} km")
