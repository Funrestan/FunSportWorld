"""跑步策略。"""
import json
from ..crypto.decrypt import get_field
from ..logger import ok


POLICY_PATH = "/api/v70103/runModePolicy"


class PolicyInfo:
    def __init__(self, timestamp, policy, min_distance, valid_time):
        self.timestamp = timestamp
        self.policy = policy
        self.min_distance = min_distance
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
    p = PolicyInfo(ts, policy,
                   rule.get("minDistance", 1000),
                   rule.get("validTime", 0))
    ok(f"[policy] ts={p.timestamp} policy={p.policy} minDist={p.min_distance}")
    return p
