"""OBS 对象组装。"""
import gzip
import base64
import json
import math

from .geom import round_to


def bd09_to_gcj02(bd_lat, bd_lng):
    X_PI = math.pi * 3000.0 / 180.0
    x = bd_lng - 0.0065
    y = bd_lat - 0.006
    z = math.sqrt(x * x + y * y) - 0.00002 * math.sin(y * X_PI)
    theta = math.atan2(y, x) - 0.000003 * math.cos(x * X_PI)
    return z * math.sin(theta), z * math.cos(theta)


def gz(data: bytes) -> str:
    return base64.b64encode(gzip.compress(data)).decode()


def gz_str(s: str) -> str:
    return gz(s.encode())


def gz_json(v) -> str:
    return gz(json.dumps(v, separators=(",", ":")).encode())


def conv_point(p, start_ms):
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
    out = []
    for i, p in enumerate(points):
        out.append({
            "flag": start_ms,
            "glat": float(p.get("glat", 0.0)),
            "glon": float(p.get("glon", 0.0)),
            "id": i + 1,
            "isFixed": p.get("isFixed", 0),
            "isPass": True,
            "lat": float(p.get("lat", 0.0)),
            "lon": float(p.get("lon", 0.0)),
            "pointName": p.get("pointName", ""),
            "position": 999,
            "state": 0,
        })
    return out


def five_point_wrapper(points, start_ms):
    five = five_point_payload(points, start_ms)
    return json.dumps({
        "useZip": False,
        "fivePointJson": json.dumps(five, separators=(",", ":")),
        "runAreaId": -1,
        "geoFencesJson": "[]",
        "freedomShowFence": False,
    }, separators=(",", ":"))


def build_windows(track, rrid):
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


def build_obs_object(track, rrid, uuid_str, uid, live_points):
    start_ms = track["startTime"]
    pts = [conv_point(p, start_ms) for p in track["locations"]]
    run_wrap = {"allLocJson": json.dumps(pts, separators=(",", ":")), "useZip": False}
    sp, stf = build_windows(track, rrid)
    laps = build_laps(track, start_ms)
    five = five_point_payload(live_points, start_ms)
    fx = {
        "fivePointJson": json.dumps(five, separators=(",", ":")),
        "freedomShowFence": False,
        "geoFencesJson": "[]",
        "runAreaId": -1,
        "useZip": False,
    }
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
    import datetime
    t0 = datetime.datetime.fromtimestamp(track["startTime"] / 1000).strftime("%Y%m%d%H")
    return [
        f"run_data/{t0}/{uuid_str}.json",
        f"run_data/{rrid // 1000000}/{rrid}.json",
    ]
