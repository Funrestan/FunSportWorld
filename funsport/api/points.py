"""校园打卡点：一次返回整组。"""
import json
import uuid

from ..config import HOST, load_points_cache, save_points_cache, POINTS_TTL_MS
from ..crypto.envelope import build_envelope, now_ms
from ..crypto.sign import md5_url_sign
from ..crypto.decrypt import parse_data_field, get_field
from ..logger import log, ok, warn, dim

POINTS_PATH = "/api/v560/get/1/distance/1"


def fetch_points(client, anchor=None, run_area_id=None):
    anchor = anchor or (client.identity["anchor_lat"], client.identity["anchor_lon"])

    cache = load_points_cache()
    if cache:
        ts, pts = cache
        if pts and (now_ms() - ts) < POINTS_TTL_MS:
            ok(f"点位缓存命中（{(now_ms()-ts)//1000}s 前，{len(pts)} 个）")
            return pts

    uid = client.uid()
    unid = str(client.session_data["unid"]) if client.session_data else "0"
    lat, lon = anchor
    url = HOST + POINTS_PATH

    start_ms = now_ms()
    runec_input = f"{uid}{lon:.6f}{lat:.6f}{(start_ms//1000)*1000}"
    runec_env = build_envelope(client.env_session, runec_input, "observed")

    body = {
        "sportType": 4,
        "longitude": lon,
        "latitude": lat,
        "sign": md5_url_sign(url),
        "uuid": str(uuid.uuid4()),
        "selectedUnid": unid,
        "runec": runec_env.json,
    }
    if run_area_id:
        body["runAreaId"] = run_area_id

    try:
        biz = client.call("POST", POINTS_PATH, json.dumps(body, separators=(",", ":")))
    except Exception as e:
        warn(f"点位接口失败: {e}")
        if cache and cache[1]:
            warn("回退最近缓存")
            return cache[1]
        raise

    data = parse_data_field(biz)
    pts = []
    if isinstance(data, dict):
        pts = data.get("pointsResModels") or []
    if not pts:
        pts = get_field(biz, "pointsResModels") or []

    if pts:
        save_points_cache(pts)
        ok(f"点位获取成功：整组 {len(pts)} 个")
        for p in pts[:8]:
            dim(f"  · {p.get('pointName','')} BD=({p.get('lat')},{p.get('lon')})")
    else:
        warn(f"点位为空 error={biz.get('error')}")
    return pts


def points_bd(points):
    out = []
    for p in points:
        lat, lon = p.get("lat"), p.get("lon")
        if lat is not None and lon is not None:
            out.append((float(lat), float(lon)))
    return out


def center_bd(points):
    if not points:
        return 0.0, 0.0
    n = len(points)
    lat = sum(p.get("lat", 0) for p in points) / n
    lon = sum(p.get("lon", 0) for p in points) / n
    return lat, lon
