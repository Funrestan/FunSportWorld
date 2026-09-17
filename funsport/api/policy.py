"""跑步策略：POST /api/v70103/runModePolicy。

返回 data.runRuleModel.minDistance（提交时 selDistance 用它）与 data.policy。
valid_time 是学校允许的跑步时间段，格式 [{"start": "HH:MM:SS", "end": "HH:MM:SS"}, ...]。
"""
import json

from ..crypto.decrypt import get_field
from ..logger import ok


POLICY_PATH = "/api/v70103/runModePolicy"


class PolicyInfo:
    def __init__(self, timestamp, policy, min_distance, valid_time):
        self.timestamp = timestamp
        self.policy = policy
        self.min_distance = min_distance
        # list of {"start": "HH:MM:SS", "end": "HH:MM:SS"}
        self.valid_time = valid_time


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

    p = PolicyInfo(
        timestamp=ts,
        policy=policy,
        min_distance=rule.get("minDistance", 1000),
        valid_time=vt,
    )
    ok(f"[policy] ts={p.timestamp} policy={p.policy} minDist={p.min_distance} "
       f"validTime={vt}")
    return p