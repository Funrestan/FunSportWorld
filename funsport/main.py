"""CLI 入口。"""
import argparse
import json
import random
import sys
import time
from datetime import datetime, timedelta

from .logger import log, ok, err, warn, info
from .config import (load_identity, load_session, save_session, clear_session,
                     load_config, save_config)
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


def cmd_run(args):
    from .api import flow
    client = make_client()
    dist = args.dist * 1000
    dur = int(dist / 1000 * args.pace)
    if args.time:
        h, m = args.time.split(":")
        base = datetime.now() - timedelta(days=args.days_ago)
        dt = base.replace(hour=int(h) % 24, minute=int(m) % 60,
                          second=0, microsecond=0)
        start_ms = int(dt.timestamp() * 1000)
    elif args.ago:
        start_ms = int(time.time() * 1000) - args.ago * 60_000
    else:
        start_ms = int(time.time() * 1000) - random.randint(30, 300) * 60_000

    log.info(f"参数：{dist:.0f}m / {dur}s / 配速 {args.pace}s/km / 开始 {fmt_hms(start_ms)}")
    result = flow.run_full_flow(client, dist, dur, start_ms,
                                face_check=1 if args.face else 0,
                                seed=args.seed)
    print()
    ok(f"跑步成功 rrid={result['rrid']} uuid={result['uuid']}")
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

    sp = sub.add_parser("run", help="跑步全链")
    sp.add_argument("--dist", type=float, default=1.2, help="距离 km")
    sp.add_argument("--pace", type=float, default=400, help="配速 秒/km")
    sp.add_argument("--ago", type=int, default=0, help="N 分钟前")
    sp.add_argument("--days-ago", type=int, default=0)
    sp.add_argument("--time", help="HH:MM")
    sp.add_argument("--face", action="store_true", default=True)
    sp.add_argument("--seed", type=int, default=0)
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
