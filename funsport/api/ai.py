"""AI 运动。"""
import json
import random
import uuid

from ..config import load_ai_sports, save_ai_sports
from ..crypto.envelope import now_ms
from ..crypto.decrypt import parse_data_field, get_field
from ..logger import ok, warn

AI_LIST_PATH = "/api/v1/sport/ai/list"
AI_UPLOAD_PATH = "/api/v65/sport/ai/record/upload"
AI_RECORDS_PATH = "/api/v66/sport/ai/record/infos"


class AiMode:
    def __init__(self, kind, value):
        self.kind = kind
        self.value = value

    @staticmethod
    def minutes(m):
        return AiMode("min", m)

    @staticmethod
    def count(r):
        return AiMode("count", (r // 5) * 5)

    def __repr__(self):
        return f"AiMode({self.kind},{self.value})"


class SportInfo:
    def __init__(self, sport_type=1, number=0):
        self.sport_type = sport_type
        self.number = number


def fetch_list(client):
    try:
        biz = client.call("GET", AI_LIST_PATH, "{}")
        data = parse_data_field(biz)
        arr = []
        if isinstance(data, dict):
            arr = data.get("list") or []
        if not arr:
            arr = get_field(biz, "list") or []
        out = [{"id": it["id"], "name": it.get("name", "")}
               for it in arr if "id" in it]
        save_ai_sports(out)
        ok(f"AI 项目 {len(out)} 个")
        return out
    except Exception as e:
        warn(f"AI 列表拉取失败: {e}")
        cached = load_ai_sports()
        if cached:
            ok(f"回退缓存 {len(cached)} 个")
            return cached
        raise


def fetch_info(client, sport_id):
    path = f"/api/v1/sport/ai/info?sportId={sport_id}"
    try:
        biz = client.call("GET", path, "{}")
        data = parse_data_field(biz)
        if isinstance(data, dict):
            return SportInfo(data.get("type", 1), data.get("number", 0))
    except Exception:
        pass
    return SportInfo(1, 0)


def upload(client, sport_id, mode, at=None):
    now = now_ms()
    info = fetch_info(client, sport_id)
    jitter = 0.9 + random.random() * 0.2

    REPS_PER_MIN = 90.0
    MS_PER_REP = 240.0

    if info.sport_type == 2 and mode.kind == "min":
        ms = mode.value * 60_000
        reps = round(REPS_PER_MIN * mode.value * jitter)
        score, tc = str(ms), ms
        speed = round(reps / (ms / 1000) * 60)
        consume = ms / 1000 * 0.2
    elif info.sport_type == 2 and mode.kind == "count":
        ms = max(int(mode.value * MS_PER_REP * jitter), 30_000)
        score, tc = str(ms), ms
        speed = round(mode.value / (ms / 1000) * 60)
        consume = ms / 1000 * 0.2
    elif mode.kind == "min":
        reps = round(REPS_PER_MIN * mode.value * jitter)
        score, tc, speed = str(reps), mode.value * 60_000, 0
        consume = reps * 0.07
    else:
        score = str(mode.value)
        tc = max(int(mode.value / REPS_PER_MIN * 60_000), 30_000)
        speed = 0
        consume = mode.value * 0.07

    consume_str = "0" if sport_id == 16 else f"{consume:.1f}"
    score_date = at or (now - tc)
    body = json.dumps({
        "sportId": sport_id, "type": info.sport_type,
        "score": score, "timeConsume": tc,
        "speed": str(speed), "consume": consume_str,
        "scoreDate": score_date,
        "uuid": str(uuid.uuid4()), "taskId": 0,
    }, separators=(",", ":"))
    biz = client.call("POST", AI_UPLOAD_PATH, body)
    ok(f"AI 提交 sport={sport_id} score={score}")
    return biz


def fetch_records(client, sport_id, page_size=50):
    path = f"{AI_RECORDS_PATH}?sportId={sport_id}&pageSize={page_size}&pageNum=1"
    biz = client.call("GET", path, "{}")
    data = parse_data_field(biz)
    arr = []
    if isinstance(data, dict):
        arr = data.get("list") or []
    groups = []
    for g in arr:
        recs = []
        for r in g.get("recordInfos") or []:
            recs.append({
                "id": r.get("id", 0),
                "name": r.get("name", ""),
                "score": str(r.get("score", "")),
                "type": r.get("type", 0),
                "upload_time": r.get("uploadTime", 0),
                "score_date": r.get("scoreDate", 0),
                "status": r.get("status", 0),
                "has_video": bool(r.get("mediaUrl") or r.get("exerciseMediaUrl")),
                "time_consume": r.get("timeConsume", 0),
                "speed": str(r.get("speed", "")),
                "consume": str(r.get("consume", "")),
            })
        groups.append({
            "score_date": g.get("scoreDate", 0),
            "frequency": g.get("frequency", 0),
            "records": recs,
        })
    total = 0
    if isinstance(data, dict):
        total = data.get("totalCount") or 0
    return {"groups": groups, "total_count": total}


def fetch_record_detail(client, rid):
    path = f"/api/v66/sport/ai/record/info?id={rid}"
    biz = client.call("GET", path, "{}")
    data = parse_data_field(biz)
    if not data:
        raise RuntimeError(f"记录 {rid} 无详情")
    return data
