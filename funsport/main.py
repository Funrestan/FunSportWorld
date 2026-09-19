"""CLI 入口。"""
import argparse
import sys

from .logger import err
from .cli import cmds, init_cmd


def cmd_gui(args=None):
    """延迟导入 Tkinter，让有参数的 CLI 在无桌面环境下仍能运行。"""
    from .gui import launch
    launch()


def cmd_help(args=None):
    """显示已有命令摘要，不启动 GUI。"""
    from .cli.mod import usage
    usage()


def main(argv=None):
    """有参数时运行 CLI，无参数或 gui 子命令时打开桌面窗口。"""
    p = argparse.ArgumentParser(prog="funsport",
                                description="FunSportWorld - 校园运动自动化")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("gui", help="打开桌面 GUI").set_defaults(func=cmd_gui)
    sub.add_parser("help", help="显示命令摘要").set_defaults(func=cmd_help)

    # ── init ────────────────────────────────────────────────
    sp = sub.add_parser("init", help="一次性初始化（账号/城市/坐标/高德Key/设备）")
    sp.add_argument("--user", help="手机号（非交互模式）")
    sp.add_argument("--pass", dest="pass_", help="密码（非交互模式）")
    sp.add_argument("--city", help="城市（市级）")
    sp.add_argument("--lat", help="纬度（可空，自动拉取）")
    sp.add_argument("--lng", help="经度（可空，自动拉取）")
    sp.add_argument("--key", help="高德 LBS Key（可空）")
    sp.add_argument("--device", choices=["keep", "new"],
                    help="设备身份：keep=保留现有，new=随机生成")
    sp.add_argument("--before-min", type=int, default=30,
                    help="提交时间最短提前（分钟），默认 30")
    sp.add_argument("--before-max", type=int, default=300,
                    help="提交时间最长提前（分钟），默认 300")
    sp.set_defaults(func=init_cmd.cmd_init)

    # ── login / logout ──────────────────────────────────────
    sp = sub.add_parser("login", help="登录（无参数时从 config.json 读取账号）")
    sp.add_argument("--user", help="手机号（可空，回退 config.json）")
    sp.add_argument("--pass", dest="pass_", help="密码（可空，回退 config.json）")
    sp.add_argument("--remember", action="store_true")
    sp.set_defaults(func=cmds.cmd_login)

    sp = sub.add_parser("logout", help="登出")
    sp.set_defaults(func=cmds.cmd_logout)

    # ── points / policy ─────────────────────────────────────
    sp = sub.add_parser("points", help="查看整组打卡点")
    sp.set_defaults(func=cmds.cmd_points)

    sp = sub.add_parser("policy", help="查看跑步策略（学校要求）")
    sp.set_defaults(func=cmds.cmd_policy)

    # ── 高德 ────────────────────────────────────────────────
    sp = sub.add_parser("lbs-amap", help="配置高德 LBS Key")
    sp.add_argument("--key", required=True)
    sp.set_defaults(func=cmds.cmd_lbs_amap)

    sp = sub.add_parser("loop-rebuild", help="强制重建校园环")
    sp.set_defaults(func=cmds.cmd_loop_rebuild)

    # ── config ──────────────────────────────────────────────
    sp = sub.add_parser("config", help="查看/设置配置")
    sp.add_argument("--set", nargs="*", help="k=v 列表")
    sp.set_defaults(func=cmds.cmd_config)

    # ── run ─────────────────────────────────────────────────
    sp = sub.add_parser("run", help="跑步全链")
    sp.add_argument("--dist", type=float, default=0)
    sp.add_argument("--dist-min", type=float)
    sp.add_argument("--dist-max", type=float)
    sp.add_argument("--min-dist", type=int)
    sp.add_argument("--pace", type=float, default=0)
    sp.add_argument("--pace-min", type=float)
    sp.add_argument("--pace-max", type=float)
    sp.add_argument("--cadence", type=float, default=0)
    sp.add_argument("--cadence-min", type=float)
    sp.add_argument("--cadence-max", type=float)
    sp.add_argument("--auto", action="store_true",
                    help="全自动：距离按学校要求+冗余、配速/步频随机、自动 use-map")
    sp.add_argument("--ago", type=int, default=0)
    sp.add_argument("--days-ago", type=int, default=0)
    sp.add_argument("--time")
    sp.add_argument("--before", type=int, default=0,
                    help="提交时间提前 N 分钟（覆盖 config；默认走 config 范围随机）")
    sp.add_argument("--allow-outside", action="store_true",
                    help="仅跳过本地时间检查，不能绕过服务端 11016")
    sp.add_argument("--face", action="store_true", default=True)
    sp.add_argument("--seed", type=int, default=0)
    sp.add_argument("--use-map", action="store_true", default=True,
                    help="兼容参数；生成轨迹始终使用高德步行 API")
    sp.set_defaults(func=cmds.cmd_run)

    # ── AI ──────────────────────────────────────────────────
    sp = sub.add_parser("ai-list", help="AI 项目列表")
    sp.set_defaults(func=cmds.cmd_ai_list)

    sp = sub.add_parser("ai", help="AI 提交")
    sp.add_argument("--sport", type=int, required=True)
    sp.add_argument("--mode", choices=["min", "count"], default="min")
    sp.add_argument("--score", type=int, default=1)
    sp.set_defaults(func=cmds.cmd_ai)

    sp = sub.add_parser("ai-records", help="AI 记录")
    sp.add_argument("--sport", type=int, required=True)
    sp.set_defaults(func=cmds.cmd_ai_records)

    sp = sub.add_parser("ai-info", help="AI 记录详情")
    sp.add_argument("--id", type=int, required=True)
    sp.set_defaults(func=cmds.cmd_ai_info)

    # ── records ─────────────────────────────────────────────
    sp = sub.add_parser("records", help="跑步记录")
    sp.set_defaults(func=cmds.cmd_records)

    sp = sub.add_parser("record-info", help="跑步详情")
    sp.add_argument("--rrid", type=int, required=True)
    sp.set_defaults(func=cmds.cmd_record_info)

    # ── semester / cheat / rank ─────────────────────────────
    sp = sub.add_parser("semester", help="学期完成度")
    sp.set_defaults(func=cmds.cmd_semester)

    sp = sub.add_parser("cheat", help="违规自查")
    sp.add_argument("--page", type=int, default=1)
    sp.set_defaults(func=cmds.cmd_cheat)

    sp = sub.add_parser("rank", help="排行榜")
    sp.add_argument("kind", choices=["main", "indoor", "history"], default="main")
    sp.add_argument("--type", type=int)
    sp.add_argument("--sort", type=int)
    sp.add_argument("--range", type=int)
    sp.set_defaults(func=cmds.cmd_rank)

    args = p.parse_args(argv)
    try:
        if not args.cmd:
            cmd_gui()
        else:
            args.func(args)
    except KeyboardInterrupt:
        err("用户中断")
    except Exception as e:
        err(f"异常：{e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
