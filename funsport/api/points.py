"""校园打卡点：一次返回整组。"""
import json
import uuid

from ..config import HOST, load_points_cache, save_points_cache, POINTS_TTL_MS
from ..crypto.envelope import build_envelope, now_ms
from ..crypto.sign import md5_url_sign
from ..crypto.decrypt import parse_data_field, get_field
from ..logger import log, ok, warn, dim

POINTS_PATH = "/api/v560/get/1/distance/1"
POINT_REQUEST_SCHEMA = 2


def fetch_points(client, anchor=None, run_area_id=None, with_metadata=False, fresh=False, allow_stale=True):
    """按参考 App 请求点位；按账号、校园和请求版本隔离缓存并保留包装字段。"""
    anchor = anchor or (client.identity["anchor_lat"], client.identity["anchor_lon"])

    context = {"uid": client.uid(), "unid": str(client.session_data.get("unid", "0")),
               "anchor": list(anchor), "runAreaId": run_area_id}
    cache = load_points_cache(with_metadata=True)
    if cache and (cache.get("context") != context
                  or cache.get("metadata", {}).get("point_request_schema") != POINT_REQUEST_SCHEMA):
        cache = None
    if cache and not fresh:
        ts, pts = cache.get("ts", 0), cache.get("points", [])
        if pts and 0 <= now_ms() - ts < POINTS_TTL_MS:
            ok(f"点位缓存命中（{(now_ms()-ts)//1000}s 前，{len(pts)} 个）")
            return (pts, cache.get("metadata", {})) if with_metadata else pts

    uid = client.uid()
    unid = str(client.session_data["unid"]) if client.session_data else "0"
    lat, lon = anchor
    url = HOST + POINTS_PATH

    start_ms = now_ms()
    runec_input = f"{uid}{lon:.6f}{lat:.6f}{(start_ms//1000)*1000}"
    runec_env = build_envelope(client.env_session, runec_input, "observed")

    body = {
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
        if not fresh and allow_stale and cache and cache.get("points"):
            warn("回退最近缓存")
            return (cache["points"], cache.get("metadata", {})) if with_metadata else cache["points"]
        raise

    data = parse_data_field(biz)
    pts = []
    if isinstance(data, dict):
        pts = data.get("pointsResModels") or []
    if not pts:
        pts = get_field(biz, "pointsResModels") or []
    metadata = {"point_request_schema": POINT_REQUEST_SCHEMA}
    if isinstance(data, dict):
        for key in ("runAreaId", "geoFencesJson", "freedomShowFence"):
            if key in data:
                metadata[key] = data[key]
    if run_area_id is not None and "runAreaId" not in metadata:
        metadata["runAreaId"] = run_area_id

    if pts:
        save_points_cache(pts, metadata, context)
        ok(f"点位获取成功：整组 {len(pts)} 个")
        for p in pts[:8]:
            dim(f"  · {p.get('pointName','')} BD=({p.get('lat')},{p.get('lon')})")
    else:
        warn(f"点位为空 error={biz.get('error')}")
    return (pts, metadata) if with_metadata else pts


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
