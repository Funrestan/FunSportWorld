"""OBS 对象组装。"""
import gzip
import base64
import json

from .geom import round_to
from ..coordinates import bd09_to_gcj02, checkpoint_coordinates


def gz(data: bytes) -> str:
    """按 OBS 字段约定压缩字节并编码为 Base64 字符串。"""
    return base64.b64encode(gzip.compress(data)).decode()


def gz_str(s: str) -> str:
    """将 UTF-8 文本编码成 OBS 使用的压缩字段。"""
    return gz(s.encode())


def gz_json(v) -> str:
    """将对象序列化为紧凑 JSON 后压缩，不再嵌套额外引号。"""
    return gz(json.dumps(v, separators=(",", ":")).encode())


def conv_point(p, start_ms):
    """把生成器的 BD 采样转换成 App MyLocation 的 GCJ 坐标字段。"""
    glat, glng = bd09_to_gcj02(p["gLat"], p["gLng"])
    return {
        "avgSpeed": round_to(p["avgSpeed"], 4),
        "bdA": round_to(p["bdA"], 2),
        "bdD": round_to(p["bdD"], 2),
        "bdG": p["bdG"],
        "bdS": round_to(p["bdS"], 4),
        "coorType": "gcj02",
        "count": p["count"],
        "dtr": 0.0,
        "flag": start_ms,
        "gLat": round_to(glat, 7),
        "gLng": round_to(glng, 7),
        "gainTime": p["gainTime"],
        "id": p["id"],
        "lat": -1.0, "lng": -1.0,
        "locType": p["locType"],
        "locationId": "",
        "queueNum": 0,
        "radius": round_to(p["radius"], 2),
        "speed": round_to(p["speed"], 4),
        "state": p["state"],
        "stepDistance": 0.0,
        "totalDis": round_to(p["totalDis"], 4),
        "totalTime": p["totalTime"],
        "type": p["type"],
        "validDis": round_to(p["validDis"], 4),
        "validTime": p["validTime"],
    }


def five_point_payload(points, start_ms):
    """保留源点位身份和状态，两套坐标统一到同一位置，不推断通过。"""
    out = []
    for i, p in enumerate(points):
        bd, gcj, _, _ = checkpoint_coordinates(p)
        out.append({
            "flag": start_ms,
            "glat": round(gcj[0], 7),
            "glon": round(gcj[1], 7),
            "id": p["id"] if p.get("id") is not None else i + 1,
            "isFixed": p.get("isFixed", 0),
            "isPass": p.get("isPass") is True,
            "lat": round(bd[0], 7),
            "lon": round(bd[1], 7),
            "pointName": p.get("pointName", ""),
            "position": p.get("position", 999),
            "state": p.get("state", 0),
        })
    return out


def five_point_wrapper(points, start_ms, metadata=None):
    """保留接口提供的跑区和围栏，保持官方 PointJsonEntity 的双层结构。"""
    five = five_point_payload(points, start_ms)
    metadata = metadata or {}
    fences = metadata.get("geoFencesJson", "[]")
    if fences is not None and not isinstance(fences, str):
        fences = json.dumps(fences, separators=(",", ":"))
    return json.dumps({
        "useZip": False,
        "fivePointJson": json.dumps(five, separators=(",", ":")),
        "runAreaId": metadata.get("runAreaId", -1),
        "geoFencesJson": fences,
        "freedomShowFence": metadata.get("freedomShowFence", False),
    }, separators=(",", ":"))


def build_windows(track, rrid):
    """将十秒距离和步数窗口转换成 App 的速度及步频记录。"""
    start_ms = track["startTime"]
    total_time = track["totalTime"]
    sp, stf = [], []
    for i, a in enumerate(track["speedPerTenSec"]):
        b = track["stepsPerTenSec"][i]
        lo = i * 10
        hi = min(i * 10 + 10, total_time)
        wid = (rrid % 100000) * 1000 + hi
        sp.append({"beginTime": start_ms + lo * 1000, "distance": a["value"],
                   "endTime": start_ms + hi * 1000, "flag": start_ms,
                   "id": wid, "queueNum": 0, "state": 0})
        stf.append({"avgDiff": 0.0, "beginTime": start_ms + lo * 1000,
                    "endTime": start_ms + hi * 1000, "flag": start_ms,
                    "id": wid, "maxDiff": 0.0, "minDiff": 1000.0,
                    "queueNum": 0, "state": 0, "stepsNum": int(b["value"])})
    return sp, stf


def build_laps(track, start_ms):
    """按累计里程拆分每公里和末尾不足一公里的分段统计。"""
    laps = []
    locs = track["locations"]
    prev_d = prev_t = prev_steps = 0
    gain = 0.0
    alt0 = locs[0]["bdA"] if locs else 0.0
    for i, pt in enumerate(locs):
        if i > 0:
            dd = pt["bdA"] - locs[i - 1]["bdA"]
            if dd > 0:
                gain += dd
        d_now, t_now = pt["totalDis"], pt["totalTime"]
        last = i == len(locs) - 1
        if d_now - prev_d >= 1000.0 or last:
            lap_d = d_now - prev_d
            lap_t = max(1, t_now - prev_t)
            lap_steps = pt["steps"] - prev_steps
            laps.append({
                "avgCadence": round_to(lap_steps / (lap_t / 60.0), 2),
                "avgPace": round_to((lap_t / 60.0) / max(lap_d / 1000.0, 0.001), 2),
                "avgStride": round_to(lap_d / max(1, lap_steps) * 100.0, 2),
                "cumulativeDuration": t_now,
                "distance": round_to(lap_d, 4),
                "duration": lap_t,
                "elevationGain": round_to(gain, 2),
                "endAltAbs": round_to(pt["bdA"], 2),
                "endAltRel": round_to(pt["bdA"] - alt0, 2),
                "flag": start_ms,
                "id": len(laps) + 1,
                "isFullLap": lap_d >= 1000.0,
                "lapIndex": len(laps) + 1,
                "step": lap_steps,
            })
            prev_d, prev_t, prev_steps = d_now, t_now, pt["steps"]
            gain = 0.0
    return laps


def build_obs_object(track, rrid, uuid_str, uid, live_points, point_wrapper=None):
    """组装 OBS；已有方案时复用提交的同一份点位包装。"""
    start_ms = track["startTime"]
    pts = [conv_point(p, start_ms) for p in track["locations"]]
    run_wrap = {"allLocJson": json.dumps(pts, separators=(",", ":")), "useZip": False}
    sp, stf = build_windows(track, rrid)
    laps = build_laps(track, start_ms)
    fx = json.loads(point_wrapper if point_wrapper is not None else five_point_wrapper(live_points, start_ms))
    return {
        "rrid": gz_str(str(rrid)),
        "uuid": gz_str(uuid_str),
        "uid": gz_str(str(uid)),
        "run_data": gz_json(run_wrap),
        "fixed_point_json": gz_json(fx),
        "segment_json": gz_str(""),
        "speed_json": gz_json(sp),
        "step_freq_json": gz_json(stf),
        "laps_json": gz_json(laps),
        "runFaceCheck": gz_str(""),
    }


def obs_keys(track, rrid, uuid_str):
    """按开始小时、UUID 和记录 ID 生成现有的两个 OBS 对象键。"""
    import datetime
    t0 = datetime.datetime.fromtimestamp(track["startTime"] / 1000).strftime("%Y%m%d%H")
    return [
        f"run_data/{t0}/{uuid_str}.json",
        f"run_data/{rrid // 1000000}/{rrid}.json",
    ]
