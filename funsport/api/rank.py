"""排行榜。"""
import json
from ..config import DISCOVERY
from ..crypto.decrypt import parse_data_field
from ..logger import ok


RANK_PATH = "/api/v41/rank"
HISTORY_PATH = "/api/v41/historyRank"
INDOOR_PATH = "/api/v43/runnings/indoor/studentRank"


def _unid(client):
    return int(client.session_data["unid"]) if client.session_data else 0


def _parse_rows(biz):
    data = parse_data_field(biz)
    arr = []
    if isinstance(data, list):
        arr = data
    elif isinstance(data, dict):
        for k in ("list", "records", "rankList", "ranks"):
            if isinstance(data.get(k), list):
                arr = data[k]
                break
    rows = []
    for i, r in enumerate(arr):
        name = r.get("name") or r.get("userName") or r.get("nickname")
        if not name:
            continue
        length = r.get("length") or r.get("totalDis") or r.get("dis") or 0
        rows.append({
            "sort": r.get("sort") or r.get("rank") or (i + 1),
            "name": name,
            "length": float(length),
            "gender": r.get("gender", -1),
        })
    return rows


def main_rank(client, rtype, sort_type, gender=1, date=None):
    import datetime
    date = date or datetime.datetime.now().strftime("%Y-%m-%d")
    body = json.dumps({
        "unid": _unid(client), "type": rtype, "sortType": sort_type,
        "date": date, "gender": gender,
    })
    biz = client.call("POST", RANK_PATH, body, host=DISCOVERY)
    rows = _parse_rows(biz)
    ok(f"主榜 {len(rows)} 行")
    return rows


def history_rank(client, sort_type, gender=1):
    body = json.dumps({
        "unid": _unid(client), "sortType": sort_type, "gender": gender,
        "pageNo": 1, "pageSize": 20,
    })
    biz = client.call("POST", HISTORY_PATH, body, host=DISCOVERY)
    rows = _parse_rows(biz)
    ok(f"历史榜 {len(rows)} 行")
    return rows


def indoor_rank(client, date_range, gender=1):
    body = json.dumps({
        "pageNum": 1, "pageSize": 20, "gender": gender, "dateRange": date_range,
    })
    biz = client.call("POST", INDOOR_PATH, body, host=DISCOVERY)
    rows = _parse_rows(biz)
    ok(f"室内榜 {len(rows)} 行")
    return rows
