"""跑步提交。"""
import json
import uuid
from .errors import BusinessError

from ..config import HOST
from ..crypto.envelope import build_envelope, now_ms
from ..crypto.header import build_android_header, UA_ANDROID
from ..crypto.sign import signature, original_sign
from ..crypto.decrypt import get_field, decrypt_response, derive_paes_key
from ..logger import log, ok, err
from ..track.calorie import avg_power, official_kcal
from ..track.geom import round_to

RECORD_PATH = "/api/v70260/runnings/save/record"


def _android_tensec(track, start_ms, kind):
    locs = track["locations"]
    total_time = track["totalTime"]
    out = []
    seed = 60000
    w = 10
    while w <= total_time:
        lo, hi = w - 10, min(w, total_time)
        d_lo = s_lo = 0
        d_hi = s_hi = 0
        for p in locs:
            tt = p["totalTime"]
            if tt <= lo:
                d_lo, s_lo = p["totalDis"], p["steps"]
            if tt <= hi:
                d_hi, s_hi = p["totalDis"], p["steps"]
        dist = round_to(max(d_hi - d_lo, 0.0), 4)
        steps = max(s_hi - s_lo, 0)
        begin = start_ms + lo * 1000
        end = start_ms + hi * 1000
        qn = w // 10 - 1
        if kind == "speed":
            out.append({"beginTime": begin, "distance": dist, "endTime": end,
                        "flag": start_ms, "id": seed + qn, "queueNum": qn, "state": 0})
        else:
            out.append({"avgDiff": 0.0, "beginTime": begin, "endTime": end,
                        "flag": start_ms, "id": seed + qn, "maxDiff": 0.0,
                        "minDiff": 1000.0, "queueNum": qn, "state": 0,
                        "stepsNum": steps})
        w += 10
    return out


def total_ascent(locs):
    a = 0.0
    for i in range(1, len(locs)):
        d = locs[i]["bdA"] - locs[i - 1]["bdA"]
        if d > 0:
            a += d
    return a


def submit_record(client, track, policy_ts, policy, min_distance,
                  weight=68.0, face_check=1, five_point_json=""):
    """提交记录，并在业务拒绝时保留错误码和提交接口上下文。"""
    total_time = track["totalTime"]
    total_dis = track["totalDistance"]
    total_steps = track["totalSteps"]
    start_ms = track["startTime"]
    stop_ms = start_ms + total_time * 1000
    ascent = total_ascent(track["locations"])
    power = avg_power(weight, total_dis, total_time)
    kcal = official_kcal(weight, total_time, total_dis)

    run_uuid = str(uuid.uuid4()).upper()
    uid = client.uid()
    unid = int(client.session_data["unid"]) if client.session_data else 0

    dis_ceil = (total_dis * 100.0 + 0.99999) // 1 / 100.0
    speed = int(round_to(total_time / dis_ceil * 50.0 / 3.0, 2) * 1024)
    avg_step_freq = max(1, int(round_to(total_steps / total_time * 60.0, 0)))

    body = {
        "allLocJson": "",
        "sportType": 1,
        "policy": policy,
        "totalTime": total_time,
        "startTime": start_ms,
        "stopTime": stop_ms,
        "getPrize": False,
        "status": 0,
        "uuid": run_uuid,
        "uid": uid,
        "selectedUnid": unid,
        "selRunTime": total_time,
        "selDistance": min_distance,
        "totalDis": int(round_to(total_dis, 0)),
        "speed": speed,
        "validDis": int(round_to(total_dis, 0)),
        "validTime": total_time,
        "complete": True,
        "unCompleteReason": 0,
        "calorie": kcal,
        "totalSteps": total_steps,
        "avgStepFreq": avg_step_freq,
        "useMobilityTools": 0,
        "faceCheck": face_check,
        "totalAscent": int(round_to(ascent, 0)),
        "avgPower": power,
        "speedPerTenSec": _android_tensec(track, start_ms, "speed"),
        "stepsPerTenSec": _android_tensec(track, start_ms, "steps"),
        "isUpload": False,
        "more": False,
        "latitude": 0.0,
        "longitude": 0.0,
        "maxRunTime": 0,
        "minSteps": 0,
        "errorCode": 0,
        "geeToken": "",
        "unauthorized": 0,
        "themeId": 0,
        "goalId": None,
        "address": client.identity.get("city", ""),
    }
    if five_point_json:
        body["fivePointJson"] = five_point_json

    body["signature"] = signature(body, False)
    body["originalSign"] = original_sign(body, False)

    body_plain = json.dumps(body, separators=(",", ":"), ensure_ascii=False)

    android_identity = dict(client.identity)
    android_identity["platform"] = "android"
    android_identity["device_name"] = "22081212C"
    android_identity["os_version"] = "14"
    header_plain, hp_extra = build_android_header(android_identity, uid, client.token())
    header_env = build_envelope(client.env_session, header_plain, "observed")
    body_env = build_envelope(client.env_session, body_plain, "insert", now_ms() + 1)

    runes = f"{policy_ts}{uid}"
    runef = f"{run_uuid}{start_ms}"

    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "User-Agent": UA_ANDROID,
        "appVersion": "7.3.40",
        "headerSign": header_env.json,
        "runes": runes,
        "runef": runef,
    }
    for k, v in hp_extra:
        headers[k] = v

    url = HOST + RECORD_PATH
    log.info(f"→ POST {RECORD_PATH} uuid={run_uuid[:8]}…")
    resp = client.http.post(url, data=body_env.json, headers=headers, timeout=60)
    log.info(f"← HTTP {resp.status_code} len={len(resp.content)}")

    key = derive_paes_key(*body_env.key_data)
    dec = decrypt_response(resp.content, key)
    biz = dec.business
    if biz.get("error") != 10000:
        raise BusinessError(biz.get("error"), biz.get("message") or biz.get("msg"), RECORD_PATH)

    rrid = get_field(biz, "rrid") or 0
    if not rrid:
        raise RuntimeError(f"提交未返回 rrid: {biz}")
    ok(f"提交成功 rrid={rrid} uuid={run_uuid}")

    return {
        "rrid": rrid,
        "uuid": run_uuid,
        "start_ms": start_ms,
        "total_dis": total_dis,
        "total_time": total_time,
        "total_steps": total_steps,
        "avg_step_freq": avg_step_freq,
        "calorie": kcal,
        "avg_power": power,
        "sel_distance": min_distance,
    }
