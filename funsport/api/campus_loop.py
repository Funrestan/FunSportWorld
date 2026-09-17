"""校园闭合环：高德步行 API 把打卡点连成可跑路径。

- 输入：打卡点 BD 坐标（来自 fetch_points）
- 输出：有序密集路径点（BD），供 track/generator ordered_path=True 使用
- 缓存：.funsport/campus_loop_bd.json，按打卡点集合 MD5 失效
"""
import json
import math
import time
import requests
from pathlib import Path

from ..config import DATA_DIR, get_amap_key, load_json, save_json
from ..logger import log, ok, warn, dim

AMAP_V5 = "https://restapi.amap.com/v5/direction/walking"
AMAP_V3 = "https://restapi.amap.com/v3/direction/walking"

MET_PER_DEG_LAT = 111_132.0
MET_PER_DEG_LNG = 86_600.0
X_PI = math.pi * 3000.0 / 180.0

# 缓存文件
LOOP_CACHE = DATA_DIR / "campus_loop_bd.json"

# 清洗参数
TURN_ANGLE_DEG = 120.0
MIN_SEG_M = 0.5
SLEEP_BETWEEN = 0.35


# ── 坐标转换 ────────────────────────────────────────────────
def bd09_to_gcj02(bd_lat, bd_lng):
    x = bd_lng - 0.0065
    y = bd_lat - 0.006
    z = math.sqrt(x * x + y * y) - 0.00002 * math.sin(y * X_PI)
    theta = math.atan2(y, x) - 0.000003 * math.cos(x * X_PI)
    return z * math.sin(theta), z * math.cos(theta)


def gcj02_to_bd09(gcj_lat, gcj_lng):
    z = math.sqrt(gcj_lng * gcj_lng + gcj_lat * gcj_lat) \
        + 0.00002 * math.sin(gcj_lat * X_PI)
    theta = math.atan2(gcj_lat, gcj_lng) + 0.000003 * math.cos(gcj_lng * X_PI)
    return z * math.sin(theta) + 0.006, z * math.cos(theta) + 0.0065


def dist_m(a, b):
    dlat = (a[0] - b[0]) * MET_PER_DEG_LAT
    dlng = (a[1] - b[1]) * MET_PER_DEG_LNG
    return math.hypot(dlat, dlng)


def turn_angle_deg(a, b, c):
    v1 = (b[0] - a[0], b[1] - a[1])
    v2 = (c[0] - b[0], c[1] - b[1])
    n1 = math.hypot(*v1)
    n2 = math.hypot(*v2)
    if n1 < 1e-12 or n2 < 1e-12:
        return 0.0
    cosv = (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)
    cosv = max(-1.0, min(1.0, cosv))
    return math.degrees(math.acos(cosv))


# ── 高德查询 ────────────────────────────────────────────────
def _amap_walking(origin_gcj, dest_gcj, key):
    o = f"{origin_gcj[1]},{origin_gcj[0]}"
    d = f"{dest_gcj[1]},{dest_gcj[0]}"

    # v5
    try:
        r = requests.get(AMAP_V5, params={
            "key": key, "origin": o, "destination": d,
            "isindoor": 0, "show_fields": "cost,polyline,navi",
        }, timeout=12)
        pts, dist = _parse_amap(r.json())
        if pts:
            return pts, dist, "v5"
    except Exception as e:
        dim(f"v5 异常: {e}")

    # v3 回退
    try:
        r = requests.get(AMAP_V3, params={
            "key": key, "origin": o, "destination": d,
        }, timeout=12)
        pts, dist = _parse_amap(r.json())
        if pts:
            return pts, dist, "v3"
        raise RuntimeError(f"v3 无 polyline: {r.json().get('info')}")
    except Exception as e:
        raise RuntimeError(f"高德查询失败: {e}")


def _parse_amap(data):
    if data.get("status") != "1":
        return [], 0
    route = data.get("route") or {}
    paths = route.get("paths") or []
    if not paths:
        return [], 0
    path = paths[0]
    dist = int(path.get("distance", 0) or 0)
    pts = []

    steps = path.get("steps") or []
    for step in steps:
        poly = step.get("polyline", "") or ""
        if not poly:
            sub = step.get("steps")
            if isinstance(sub, list):
                for s2 in sub:
                    poly += (s2.get("polyline", "") or "") + ";"
            poly = poly.strip(";")
        if not poly:
            continue
        for seg in poly.split(";"):
            seg = seg.strip()
            if not seg or "," not in seg:
                continue
            lon_s, lat_s = seg.split(",", 1)
            try:
                pts.append((float(lat_s), float(lon_s)))
            except ValueError:
                continue

    if not pts:
        poly = path.get("polyline", "") or ""
        for seg in poly.split(";"):
            seg = seg.strip()
            if not seg or "," not in seg:
                continue
            lon_s, lat_s = seg.split(",", 1)
            try:
                pts.append((float(lat_s), float(lon_s)))
            except ValueError:
                continue
    return pts, dist


# ── 清洗 ────────────────────────────────────────────────────
def _dedup_exact(pts):
    out = []
    for p in pts:
        if not out or p != out[-1]:
            out.append(p)
    return out


def _dedup_min_dist(pts, min_m=MIN_SEG_M):
    if not pts:
        return pts
    out = [pts[0]]
    for p in pts[1:]:
        if dist_m(out[-1], p) >= min_m:
            out.append(p)
    return out


def _densify_turns(pts, max_angle=TURN_ANGLE_DEG):
    if len(pts) < 3:
        return pts
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        a, b, c = out[-1], pts[i], pts[i + 1]
        out.append(b)
        if turn_angle_deg(a, b, c) > max_angle:
            out.append(((b[0] + c[0]) * 0.5, (b[1] + c[1]) * 0.5))
    out.append(pts[-1])
    return out


def _sanitize(pts):
    n0 = len(pts)
    pts = _dedup_exact(pts)
    n1 = len(pts)
    pts = _dedup_min_dist(pts)
    n2 = len(pts)
    pts = _densify_turns(pts)
    n3 = len(pts)
    dim(f"清洗: exact {n0}->{n1}, min_dist {n1}->{n2}, densify {n2}->{n3}")
    return pts


# ── 主入口 ──────────────────────────────────────────────────
def _points_fingerprint(checkpoints_bd):
    """打卡点集合指纹（顺序无关）。"""
    import hashlib
    s = ";".join(f"{la:.6f},{lo:.6f}" for la, lo in sorted(checkpoints_bd))
    return hashlib.md5(s.encode()).hexdigest()


def build_loop(checkpoints_bd, key, verbose=True):
    """5 段查询 + 拼接 + 清洗，返回 BD 点数组。"""
    loop_gcj = []
    total_m = 0
    n = len(checkpoints_bd)

    for i in range(n):
        a_bd = checkpoints_bd[i]
        b_bd = checkpoints_bd[(i + 1) % n]
        a_gcj = bd09_to_gcj02(*a_bd)
        b_gcj = bd09_to_gcj02(*b_bd)

        if verbose:
            dim(f"[段 {i}] {a_bd} -> {b_bd}")
        try:
            pts, dist, src = _amap_walking(a_gcj, b_gcj, key)
        except Exception as e:
            warn(f"段 {i} 失败: {e}")
            return None

        if not pts:
            warn(f"段 {i} 无 polyline")
            return None

        pts = _dedup_exact(pts)
        if loop_gcj and dist_m(pts[0], loop_gcj[-1]) < 2.0:
            pts = pts[1:]
        if verbose:
            dim(f"  {src} {dist}m {len(pts)}点")
        loop_gcj.extend(pts)
        total_m += dist
        time.sleep(SLEEP_BETWEEN)

    # 闭合
    first_gcj = bd09_to_gcj02(*checkpoints_bd[0])
    if dist_m(loop_gcj[-1], first_gcj) > 0.1:
        loop_gcj.append(first_gcj)

    loop_gcj = _sanitize(loop_gcj)
    # 最终去重（sanitize 后 append 首点可能重复）
    loop_gcj = _dedup_exact(loop_gcj)

    loop_bd = [gcj02_to_bd09(la, lo) for la, lo in loop_gcj]
    if verbose:
        ok(f"环生成完成：{len(loop_bd)} 点，总长 {total_m:.0f}m")
    return loop_bd


def get_campus_loop(points, force_rebuild=False):
    """获取校园闭合环（带缓存）。

    points: fetch_points 返回的原始点位（含 lat/lon）
    返回：BD 坐标数组 [(lat, lon), ...]
    """
    checkpoints_bd = [(float(p["lat"]), float(p["lon"])) for p in points
                      if "lat" in p and "lon" in p]
    if len(checkpoints_bd) < 2:
        raise RuntimeError(f"打卡点不足（{len(checkpoints_bd)} 个），无法生成环")

    fp = _points_fingerprint(checkpoints_bd)

    # 缓存命中
    if not force_rebuild and LOOP_CACHE.exists():
        cached = load_json(LOOP_CACHE)
        if cached and cached.get("fingerprint") == fp:
            pts = cached.get("points") or []
            if pts:
                ok(f"环缓存命中（{len(pts)} 点，指纹 {fp[:8]}…）")
                return [(float(a), float(b)) for a, b in pts]

    key = get_amap_key()
    if not key:
        raise RuntimeError("未配置高德 Key：先执行 `lbs-amap --key <你的Key>` "
                           "或设置环境变量 FUNSPORT_AMAP_KEY")

    ok(f"高德环生成中（{len(checkpoints_bd)} 打卡点，key={key[:8]}…）")
    loop_bd = build_loop(checkpoints_bd, key)
    if not loop_bd:
        raise RuntimeError("环生成失败（高德 API 无返回）")

    save_json(LOOP_CACHE, {
        "fingerprint": fp,
        "checkpoints": checkpoints_bd,
        "points": loop_bd,
        "total": len(loop_bd),
        "ts": int(time.time() * 1000),
    })
    ok(f"环已缓存 → {LOOP_CACHE}")
    return loop_bd