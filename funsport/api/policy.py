"""跑步策略：POST /api/v70103/runModePolicy。

返回 data.runRuleModel.minDistance（提交时 selDistance 用它）与 data.policy。
valid_time 是学校允许的跑步时间段，格式 [{"start": "HH:MM:SS", "end": "HH:MM:SS"}, ...]。
"""
import json
from copy import deepcopy

from ..crypto.decrypt import get_field
from ..logger import ok


POLICY_PATH = "/api/v70103/runModePolicy"


class PolicyInfo:
    def __init__(self, timestamp, policy, min_distance, valid_time,
                 run_rules=None, geo_fence=None, run_area_models=None,
                 freeze_run_time=0, message=""):
        self.timestamp = timestamp
        self.policy = policy
        self.min_distance = min_distance
        # list of {"start": "HH:MM:SS", "end": "HH:MM:SS"}
        self.valid_time = valid_time
        self.run_rules = deepcopy(run_rules) if run_rules is not None else {}
        self.geo_fence = deepcopy(geo_fence)
        self.run_area_models = deepcopy(run_area_models)
        # App uses this server value as the remaining frozen duration, in seconds.
        try:
            self.freeze_run_time = max(0, int(freeze_run_time or 0))
        except (TypeError, ValueError):
            self.freeze_run_time = 0
        self.message = str(message or "")


def fetch_policy(client):
    unid = client.session_data["unid"] if client.session_data else "0"
    body = json.dumps({
        "runMode": 1,
        "ruleUpdateTime": 0,
        "geoFenceUpdateTime": 0,
        "selectUnid": int(unid) if str(unid).isdigit() else 0,
        "operateType": 0,
    }, separators=(",", ":"))
    biz = client.call("POST", POLICY_PATH, body)
    ts = get_field(biz, "timestamp")
    if ts is None:
        raise RuntimeError("policy 缺 timestamp")
    policy = get_field(biz, "policy") or 0
    rule = get_field(biz, "runRuleModel") or {}

    # valid_time：优先顶层，其次 rule，再其次空
    vt = get_field(biz, "validTime")
    if vt is None:
        vt = rule.get("validTime")
    if vt is None:
        vt = []
    # 兼容字符串形式（有些学校返回 JSON 字符串）
    if isinstance(vt, str):
        try:
            vt = json.loads(vt)
        except Exception:
            vt = []
    # 兼容 dict 形式
    if isinstance(vt, dict):
        vt = [vt]
    # 只保留 start/end 都存在的项
    if isinstance(vt, list):
        vt = [
            {"start": w.get("start", ""), "end": w.get("end", "")}
            for w in vt
            if isinstance(w, dict) and w.get("start") and w.get("end")
        ]

    raw_data = biz.get("data") if isinstance(biz, dict) else None
    if isinstance(raw_data, str):
        try:
            raw_data = json.loads(raw_data)
        except (TypeError, ValueError):
            raw_data = None
    policy_message = raw_data.get("message", "") if isinstance(raw_data, dict) else ""

    p = PolicyInfo(
        timestamp=ts,
        policy=policy,
        min_distance=rule.get("minDistance", 1000),
        valid_time=vt,
        run_rules=rule,
        geo_fence=get_field(biz, "geoFence"),
        run_area_models=get_field(biz, "runAreaModels"),
        freeze_run_time=get_field(biz, "freezeRunTime") or 0,
        message=policy_message,
    )
    ok(f"[policy] ts={p.timestamp} policy={p.policy} minDist={p.min_distance} "
       f"validTime={vt} freeze={p.freeze_run_time}s")
    return p
