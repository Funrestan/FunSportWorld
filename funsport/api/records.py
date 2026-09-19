"""跑步记录。"""
import json
from ..crypto.decrypt import parse_data_field, get_field
from ..logger import ok


RECORDS_PATH = "/api/v70230/runnings/records"
GET_ONE_PATH = "/api/v70260/runnings/get_one_record"


def fetch_records(client):
    """读取记录摘要，保留服务端未提供达标状态时的未知值。"""
    biz = client.call("POST", RECORDS_PATH, "{}")
    data = parse_data_field(biz)
    if isinstance(data, list):
        arr = data
    elif isinstance(data, dict):
        arr = data.get("list") or data.get("records") or []
    else:
        arr = get_field(biz, "list") or []
    rows = []
    for r in arr:
        rows.append({
            "rrid": r.get("rrid", 0),
            "total_dis": r.get("totalDis", 0.0),
            "total_time": r.get("totalTime", 0),
            "start_time": r.get("startTime", 0),
            "complete": r.get("complete"),
            "avg_step_freq": r.get("avgStepFreq", 0),
            "calorie": r.get("calorie", 0),
            "avg_power": r.get("avgPower", 0),
            "total_steps": r.get("totalSteps", 0),
            "uuid": r.get("uuid", ""),
        })
    ok(f"记录 {len(rows)} 条")
    return rows


def fetch_one_record(client, rrid):
    """读取指定记录详情，并拒绝把空值或非对象误当成有效详情。"""
    body = json.dumps({"rrid": rrid, "uuid": None, "calculateBadge": False})
    biz = client.call("POST", GET_ONE_PATH, body)
    inner = parse_data_field(biz)
    if isinstance(inner, dict) and "data" in inner:
        inner = parse_data_field(inner)
    if not isinstance(inner, dict) or not inner:
        raise RuntimeError("详情为空或格式不是对象")
    return inner
