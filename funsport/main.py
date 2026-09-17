"""CLI 入口。"""
import argparse
import json
import random
import sys
import time
from datetime import datetime, timedelta

from .logger import log, ok, err, warn, info
from .config import (load_identity, load_session, save_session, clear_session,
                     load_config, save_config, set_amap_key, clear_loop_cache,
                     set_config)
from .api.client import ApiClient


def make_client():
    identity = load_identity()
    sess = load_session()
    if not sess.get("uid"):
        err("未登录，先执行 login")
        sys.exit(1)
    return ApiClient(identity, sess)


def fmt_hms(ms):
    return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M:%S")


def cmd_login(args):
    from .api import login as api_login
    identity = load_identity()
    client = ApiClient(identity)
    sess = api_login.login(client, args.user, args.pass_)
    if args.remember:
        cfg = load_config()
        cfg["username"] = args.user
        cfg["password"] = args.pass_
        cfg["remember"] = True
        save_config(cfg)
        ok("凭据已保存")


def cmd_logout(args):
    from .api import login as api_login
    identity = load_identity()
    sess = load_session()
    client = ApiClient(identity, sess if sess.get("uid") else None)
    api_login.logout(client)


def cmd_points(args):
    from .api import points as api_points
    client = make_client()
    pts = api_points.fetch_points(client)
    log.info(f"共 {len(pts)} 个打卡点：")
    for i, p in enumerate(pts, 1):
        log.info(f"  {i:2}. {p.get('pointName',''):20s} "
                 f"BD=({p.get('lat')},{p.get('lon')})")


def cmd_policy(args):
    from .api import policy as api_policy
    client = make_client()
    pol = api_policy.fetch_policy(client)
    print(f"policy       = {pol.policy}")
    print(f"min_distance = {pol.min_distance} m")
    print(f"valid_time   = {pol.valid_time}")
    print(f"timestamp    = {pol.timestamp}")


def cmd_lbs_amap(args):
    set_amap_key(args.key)
    ok(f"高德 Key 已写入 config.json：{args.key[:8]}…")


def cmd_loop_rebuild(args):
    from .api import points as api_points
    from .api import campus_loop as api_loop
    client = make_client()
    clear_loop_cache()
    pts = api_points.fetch_points(client)
    ring = api_loop.get_campus_loop(pts, force_rebuild=True)
    ok(f"环已重建：{len(ring)} 点 → .funsport/campus_loop_bd.json")


def cmd_config(args):
    cfg = load_config()
    if args.set:
        # k=v 形式批量更新
        updates = {}
        for pair in args.set:
            if "=" not in pair:
                continue
            k, v = pair.split("=", 1)
            updates[k.strip()] = v.strip()
        n = set_config(**updates)
        ok(f"已更新 {n} 项")
        return
    # 无参数：打印当前配置
    for k in sorted(cfg.keys()):
        v = cfg[k]
        if k == "password" and v:
            v = v[:2] + "***"
        print(f"{k:24s} = {v}")


def cmd_run(args):
    from .api import flow
    client = make_client()

    if args.time:
        h, m = args.time.split(":")
        base = datetime.now() - timedelta(days=args.days_ago)
        dt = base.replace(hour=int(h) % 24, minute=int(m) % 60,
                          second=0, microsecond=0)
        start_ms = int(dt.timestamp() * 1000)
    elif args.ago:
        start_ms = int(time.time() * 1000) - args.ago * 60_000
    else:
        start_ms = 0  # 让 flow 随机

    tag = " / AUTO" if args.auto else (" / 真实路径" if args.use_map else "")
    log.info(f"参数：{tag.strip() or '手动'}")
    if args.dist:
        log.info(f"  --dist={args.dist} km")
    if args.dist_min or args.dist_max:
        log.info(f"  --dist-min={args.dist_min} --dist-max={args.dist_max}")
    if args.pace:
        log.info(f"  --pace={args.pace} s/km")
    if args.pace_min or args.pace_max:
        log.info(f"  --pace-min={args.pace_min} --pace-max={args.pace_max}")
    if args.cadence:
        log.info(f"  --cadence={args.cadence} spm")
    if args.cadence_min or args.cadence_max:
        log.info(f"  --cadence-min={args.cadence_min} --cadence-max={args.cadence_max}")

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
    )
    print()
    ok(f"跑步成功 rrid={result['rrid']} uuid={result['uuid']}")
    ok(f"距离 {result['dist']:.0f}m / 时长 {result['dur']}s / "
       f"平均步频 {result['cadence_avg']:.0f}spm")
    ok(f"OBS {result['obs_ok']}/2 · 验证 {'通过' if result['detail_ok'] else '未通过'}")


def cmd_ai_list(args):
    from .api import ai as api_ai
    client = make_client()
    lst = api_ai.fetch_list(client)
    for s in lst:
        print(f"id={s['id']:<5} {s['name']}")


def cmd_ai(args):
    from .api import ai as api_ai
    client = make_client()
    if args.mode == "count":
        mode = api_ai.AiMode.count(args.score)
    else:
        mode = api_ai.AiMode.minutes(args.score)
    api_ai.upload(client, args.sport, mode)


def cmd_records(args):
    from .api import records as api_records
    client = make_client()
    rows = api_records.fetch_records(client)
    print(f"{'时间':<20} {'距离m':>8} {'时长':>8} {'配速':>7} {'步频':>5} {'达标':>4} rrid")
    for r in rows:
        t = fmt_hms(r["start_time"])[5:]
        p = r["total_time"] / (r["total_dis"] / 1000) if r["total_dis"] > 0 else 0
        pace = f"{int(p//60)}:{int(p%60):02d}"
        dur = f"{r['total_time']//3600}:{r['total_time']%3600//60:02d}:{r['total_time']%60:02d}"
        print(f"{t:<20} {r['total_dis']:>8.0f} {dur:>8} {pace:>7} "
              f"{r['avg_step_freq']:>5} {'是' if r['complete'] else '否':>4} {r['rrid']}")


def cmd_ai_records(args):
    from .api import ai as api_ai
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


def cmd_semester(args):
    from .api import semester as api_semester
    client = make_client()
    r = api_semester.query(client)
    s = r["summary"]
    print(f"学期：{s.sname}")
    print(f"  有效次数：{s.semester_valid_count}/{s.semester_count}")
    print(f"  有效里程：{s.semester_valid_dis/1000:.2f} km")


def cmd_cheat(args):
    from .api import cheat as api_cheat
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
    from .api import rank as api_rank
    client = make_client()
    if args.kind == "indoor":
        rows = api_rank.indoor_rank(client, args.range or 1)
    elif args.kind == "history":
        rows = api_rank.history_rank(client, args.sort or 1)
    else:
        rows = api_rank.main_rank(client, args.type or 1, args.sort or 1)
    for r in rows:
        print(f"{r['sort']:<4} {r['name']}  {r['length']/1000:.2f} km")


def cmd_ai_info(args):
    from .api import ai as api_ai
    client = make_client()
    d = api_ai.fetch_record_detail(client, args.id)
    print(json.dumps(d, ensure_ascii=False, indent=2))


def cmd_record_info(args):
    from .api import records as api_records
    client = make_client()
    d = api_records.fetch_one_record(client, args.rrid)
    print(json.dumps(d, ensure_ascii=False, indent=2))


def main():
    p = argparse.ArgumentParser(prog="funsport",
                                description="FunSportWorld - 校园运动自动化")
    sub = p.add_subparsers(dest="cmd")

    sp = sub.add_parser("login", help="登录")
    sp.add_argument("--user", required=True)
    sp.add_argument("--pass", dest="pass_", required=True)
    sp.add_argument("--remember", action="store_true")
    sp.set_defaults(func=cmd_login)

    sp = sub.add_parser("logout", help="登出")
    sp.set_defaults(func=cmd_logout)

    sp = sub.add_parser("points", help="查看整组打卡点")
    sp.set_defaults(func=cmd_points)

    sp = sub.add_parser("policy", help="查看跑步策略（学校要求）")
    sp.set_defaults(func=cmd_policy)

    sp = sub.add_parser("lbs-amap", help="配置高德 LBS Key（写入 config.json）")
    sp.add_argument("--key", required=True, help="高德 Web 服务 Key")
    sp.set_defaults(func=cmd_lbs_amap)

    sp = sub.add_parser("loop-rebuild", help="强制重建校园环（高德）")
    sp.set_defaults(func=cmd_loop_rebuild)

    sp = sub.add_parser("config", help="查看/设置配置（config set k=v）")
    sp.add_argument("--set", nargs="*", help="k=v 列表，如 --set auto_pace_min_s=350")
    sp.set_defaults(func=cmd_config)

    # ── run ──
    sp = sub.add_parser("run", help="跑步全链")
    # 距离
    sp.add_argument("--dist", type=float, default=0, help="固定距离 km")
    sp.add_argument("--dist-min", type=float, help="距离下限 km")
    sp.add_argument("--dist-max", type=float, help="距离上限 km")
    sp.add_argument("--min-dist", type=int, help="强制里程下限 米（覆盖学校要求）")
    # 配速
    sp.add_argument("--pace", type=float, default=0, help="固定配速 秒/km")
    sp.add_argument("--pace-min", type=float, help="配速下限 秒/km")
    sp.add_argument("--pace-max", type=float, help="配速上限 秒/km")
    # 步频
    sp.add_argument("--cadence", type=float, default=0, help="固定步频 spm")
    sp.add_argument("--cadence-min", type=float, help="步频下限 spm")
    sp.add_argument("--cadence-max", type=float, help="步频上限 spm")
    # 自动
    sp.add_argument("--auto", action="store_true",
                    help="全自动：距离按学校要求+冗余、配速/步频按配置随机、自动 --use-map")
    # 时间
    sp.add_argument("--ago", type=int, default=0, help="N 分钟前")
    sp.add_argument("--days-ago", type=int, default=0)
    sp.add_argument("--time", help="HH:MM")
    # 其他
    sp.add_argument("--face", action="store_true", default=True)
    sp.add_argument("--seed", type=int, default=0)
    sp.add_argument("--use-map", action="store_true",
                    help="用高德生成的校园环替代拟合环")
    sp.set_defaults(func=cmd_run)

    sp = sub.add_parser("ai-list", help="AI 项目列表")
    sp.set_defaults(func=cmd_ai_list)

    sp = sub.add_parser("ai", help="AI 提交")
    sp.add_argument("--sport", type=int, required=True)
    sp.add_argument("--mode", choices=["min", "count"], default="min")
    sp.add_argument("--score", type=int, default=1)
    sp.set_defaults(func=cmd_ai)

    sp = sub.add_parser("records", help="跑步记录")
    sp.set_defaults(func=cmd_records)

    sp = sub.add_parser("ai-records", help="AI 记录")
    sp.add_argument("--sport", type=int, required=True)
    sp.set_defaults(func=cmd_ai_records)

    sp = sub.add_parser("semester", help="学期完成度")
    sp.set_defaults(func=cmd_semester)

    sp = sub.add_parser("cheat", help="违规自查")
    sp.add_argument("--page", type=int, default=1)
    sp.set_defaults(func=cmd_cheat)

    sp = sub.add_parser("rank", help="排行榜")
    sp.add_argument("kind", choices=["main", "indoor", "history"], default="main")
    sp.add_argument("--type", type=int)
    sp.add_argument("--sort", type=int)
    sp.add_argument("--range", type=int)
    sp.set_defaults(func=cmd_rank)

    sp = sub.add_parser("record-info", help="跑步详情")
    sp.add_argument("--rrid", type=int, required=True)
    sp.set_defaults(func=cmd_record_info)

    sp = sub.add_parser("ai-info", help="AI 记录详情")
    sp.add_argument("--id", type=int, required=True)
    sp.set_defaults(func=cmd_ai_info)

    args = p.parse_args()
    if not args.cmd:
        p.print_help()
        return

    try:
        args.func(args)
    except KeyboardInterrupt:
        err("用户中断")
    except Exception as e:
        err(f"异常：{e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)