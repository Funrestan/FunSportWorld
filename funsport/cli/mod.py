"""CLI 共享助手：参数解析、日志、客户端构造。"""
import sys
import datetime

from ..api.client import ApiClient
from ..config import load_identity, load_session, load_config
from ..api import login as api_login


def usage():
    print(r"""FunSportWorld CLI（无参数启动 GUI）

  init    [--user 手机号 --pass 密码 --city 城市 --lat 纬度 --lng 经度
           --key 高德Key --device keep|new]
                                           一次性初始化（账号/城市/坐标/高德Key/设备）
  login   --user <手机号> --pass <密码> [--remember]
                                           登录并保存会话
  logout                                   登出并清理本地会话
  points                                   查看整组打卡点
  policy                                   查看跑步策略（学校要求）
  lbs-amap --key <高德Key>                 写入高德 Key
  loop-rebuild                             强制重建校园环
  config  [--set k=v ...]                  查看/设置配置
  run    [--dist km] [--pace 秒/km] [--auto] [--use-map] [--cadence spm]
                                           跑步全链
  ai-list                                  AI 运动项目列表
  ai     --sport <id> [--mode min|count] [--score n]
                                           AI 运动提交
  records                                  跑步记录列表
  ai-records --sport <id>                  AI 运动记录
  semester                                 学期完成度
  cheat  [--page n]                        违规自查
  rank   main|indoor|history [...]         排行榜
  record-info --rrid <id>                  跑步详情
  ai-info --id <id>                        AI 记录详情
""")


def parse_flags(rest):
    """把 ['--user', 'x', '--pass', 'y'] 解析成 [('user','x'), ('pass','y')]。"""
    out = []
    i = 0
    while i < len(rest):
        k = rest[i].lstrip("-")
        if i + 1 < len(rest) and not rest[i + 1].startswith("-"):
            out.append((k, rest[i + 1]))
            i += 2
        else:
            out.append((k, "1"))
            i += 1
    return out


def get(flags, name):
    for k, v in flags:
        if k == name:
            return v
    return None


def logger():
    from ..logger import log

    def cb(s):
        log.info(s)
    return cb


def silent():
    def cb(s):
        pass
    return cb


def auto_login(identity):
    """从 config.json 读取账号密码自动登录。"""
    cfg = load_config()
    if cfg.get("remember") and cfg.get("username") and cfg.get("password"):
        print("[login] 使用已保存的账号自动登录…")
        client = ApiClient(identity, None)
        sess = api_login.login(client, cfg["username"], cfg["password"])
        return sess
    raise RuntimeError("未登录：先执行 init 或 login")


def make_client():
    """构造已登录客户端；无会话时自动登录。"""
    identity = load_identity()
    sess = load_session()
    if sess.get("uid"):
        return ApiClient(identity, sess)
    s = auto_login(identity)
    return ApiClient(identity, s)


def fmt_hms(ms):
    return datetime.datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M:%S")


def now_ms():
    from ..crypto.envelope import now_ms as _now
    return _now()


def jstr(v, keys):
    """从 json 里按 keys 顺序取第一个字符串值。"""
    for k in keys:
        val = v.get(k)
        if isinstance(val, str):
            return val
        if isinstance(val, (int, float)):
            return str(val)
    return "-"


def print_rows(rows):
    print(f"{'时间':<20} {'距离m':>8} {'时长':>8} {'配速':>7} {'步频':>5} {'达标':>4} rrid")
    for r in rows:
        t = fmt_hms(r["start_time"])[5:]
        p = r["total_time"] / (r["total_dis"] / 1000) if r["total_dis"] > 0 else 0
        pace = f"{int(p//60)}:{int(p%60):02d}"
        dur = f"{r['total_time']//3600}:{r['total_time']%3600//60:02d}:{r['total_time']%60:02d}"
        print(f"{t:<20} {r['total_dis']:>8.0f} {dur:>8} {pace:>7} "
              f"{r['avg_step_freq']:>5} {'是' if r['complete'] else '否':>4} {r['rrid']}")


def parse_pace(s):
    if ":" in s:
        m, sec = s.split(":")
        return int(m) * 60 + int(sec)
    return int(float(s))