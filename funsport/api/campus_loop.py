"""校园闭合环：高德步行 API 把打卡点连成可跑路径。

- 输入：打卡点双坐标（原生 GCJ 优先，缺失时由 BD 转换）
- 输出：有序密集路径点（BD），供 track/generator ordered_path=True 使用
- 缓存：.funsport/campus_loop_bd.json，保存分段候选；种子选择道路，点位顺序不变
"""
import json
import hashlib
import math
import time
import requests

from .. import config as app_config
from ..config import get_amap_key, load_json, save_json
from ..logger import log, ok, warn, dim
from ..coordinates import bd09_to_gcj02, gcj02_to_bd09, checkpoint_coordinates, distance_m
from ..run_diagnostics import current_archive

AMAP_V5 = "https://restapi.amap.com/v5/direction/walking"
AMAP_V3 = "https://restapi.amap.com/v3/direction/walking"

MET_PER_DEG_LAT = 111_132.0
MET_PER_DEG_LNG = 86_600.0
CACHE_SCHEMA = 4
CACHE_PROVIDER = "amap_walking"
CACHE_TTL_MS = 86400_000
MAX_ALTERNATIVES = 3
MAX_COMBINATION_TRIES = 512
# 本工具的保守完整性阈值，不是高德或官方打卡标准。
JOIN_TOLERANCE_M = 3.0
ENDPOINT_TOLERANCE_M = 100.0

# 清洗参数
TURN_ANGLE_DEG = 120.0
MIN_SEG_M = 0.5
SLEEP_BETWEEN = 0.35


def dist_m(a, b):
    """计算同一坐标系中两点的球面距离，用于分段和端点检查。"""
    return distance_m(a, b)


def turn_angle_deg(a, b, c):
    """计算相邻折线段的转角，供原始折线的细分使用。"""
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
def _amap_walking(origin_gcj, dest_gcj, key, all_routes=False):
    """一次请求最多三条高德候选；默认仍返回首条，错误不包含Key。"""
    o = f"{origin_gcj[1]},{origin_gcj[0]}"
    d = f"{dest_gcj[1]},{dest_gcj[0]}"

    for version, url in (("v5", AMAP_V5), ("v3", AMAP_V3)):
        params = {"key": key, "origin": o, "destination": d}
        if version == "v5":
            params.update(isindoor=0, show_fields="cost,polyline,navi", alternative_route=MAX_ALTERNATIVES)
        archive = current_archive()
        started = time.monotonic()
        response = None
        captured = False
        try:
            with requests.get(url, params=params, timeout=12) as response:
                response.raise_for_status()
                data = response.json()
                if archive:
                    archive.record_message(
                        "amap-route", "GET", url.split("?")[0], request={"params": params},
                        response=data, status=response.status_code,
                        duration_ms=round((time.monotonic() - started) * 1000))
                    captured = True
                candidates = []
                fingerprints = set()
                for index in range(MAX_ALTERNATIVES):
                    pts, dist = _parse_amap(data, path_index=index)
                    if len(pts) >= 2:
                        digest = _ring_digest(_dedup_exact(pts))
                        if digest not in fingerprints:
                            candidates.append((pts, dist, version))
                            fingerprints.add(digest)
            if candidates:
                return candidates if all_routes else candidates[0]
        except (requests.RequestException, ValueError, TypeError) as exc:
            if archive and not captured:
                archive.record_message(
                    "amap-route", "GET", url.split("?")[0], request={"params": params},
                    status=response.status_code if response is not None else None,
                    error=str(exc), duration_ms=round((time.monotonic() - started) * 1000))
            pass
        if version == "v5":
            dim("高德 v5 未返回可用路线，尝试 v3")
    raise RuntimeError("高德步行路线规划失败，请检查 Web 服务 Key、权限、额度和网络；不会改用拟合环")


def _step_polylines(steps, depth=0):
    """逐个提取嵌套步骤，保留步骤边界以检查每一处接缝。"""
    if depth > 8 or not isinstance(steps, list):
        raise ValueError("高德步骤结构无效")
    for step in steps:
        if not isinstance(step, dict):
            raise ValueError("高德步骤不是对象")
        if step.get("polyline"):
            yield step["polyline"]
        elif step.get("steps"):
            yield from _step_polylines(step["steps"], depth + 1)


def _parse_amap(data, path_index=0):
    """解析指定候选的完整polyline，坏坐标或断线不会污染其他候选。"""
    if not isinstance(data, dict) or str(data.get("status")) != "1":
        return [], 0
    route = data.get("route") or {}
    if not isinstance(route, dict):
        return [], 0
    paths = route.get("paths") or []
    if (not isinstance(paths, list) or type(path_index) is not int
            or not 0 <= path_index < len(paths) or not isinstance(paths[path_index], dict)):
        return [], 0
    path = paths[path_index]
    try:
        dist = int(path.get("distance", 0) or 0)
    except (ValueError, TypeError, OverflowError):
        return [], 0
    if dist <= 0:
        return [], 0
    pts = []

    try:
        polylines = list(_step_polylines(path.get("steps") or []))
    except ValueError:
        return [], 0
    if not polylines and path.get("polyline"):
        polylines.append(path["polyline"])
    for poly in polylines:
        if not isinstance(poly, str):
            return [], 0
        segment = []
        for seg in poly.split(";"):
            seg = seg.strip()
            if not seg:
                continue
            try:
                lon_s, lat_s = seg.split(",", 1)
                lat, lon = float(lat_s), float(lon_s)
            except (ValueError, TypeError):
                return [], 0
            if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
                return [], 0
            segment.append((lat, lon))
        if not segment:
            continue
        if pts and dist_m(pts[-1], segment[0]) > JOIN_TOLERANCE_M:
            return [], 0
        pts.extend(segment)
    # 容忍地图测距和折线简化差异，但拒绝远超返回里程的段内跳点。
    measured = sum(dist_m(a, b) for a, b in zip(pts, pts[1:]))
    if measured > max(dist * 1.5, dist + 100):
        return [], 0
    return pts, dist


# ── 清洗 ────────────────────────────────────────────────────
def _dedup_exact(pts):
    """仅删除相邻重复顶点，不改变路线顺序。"""
    out = []
    for p in pts:
        if not out or p != out[-1]:
            out.append(p)
    return out


def _dedup_min_dist(pts, min_m=MIN_SEG_M):
    """移除过密顶点，同时保留原有路线走向。"""
    if not pts:
        return pts
    out = [pts[0]]
    for p in pts[1:]:
        if dist_m(out[-1], p) >= min_m:
            out.append(p)
    return out


def _densify_turns(pts, max_angle=TURN_ANGLE_DEG):
    """沿现有线段补中点，不使用曲线拟合重新规划道路。"""
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
    """对高德折线做去重和线段细分。"""
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
def _points_fingerprint(checkpoints):
    """指纹包含点位顺序；同一组点改顺序也必须重新规划。"""
    s = ";".join(f"{la:.7f},{lo:.7f}" for la, lo in checkpoints)
    return hashlib.md5(s.encode()).hexdigest()


def _ring_digest(ring):
    """校验缓存折线的完整内容和顺序，检测意外损坏而非认证高德签名。"""
    return hashlib.sha256(json.dumps(ring, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _validate_leg_option(option, origin, destination):
    """统一检查网络或缓存的单段道路坐标、里程、来源及端点。"""
    try:
        if not isinstance(option, dict) or option.get("source") not in ("v5", "v3"):
            return None
        distance = option.get("distance")
        raw = option.get("points")
        if type(distance) is not int or distance <= 0 or not isinstance(raw, list) or len(raw) < 2:
            return None
        if any(isinstance(value, bool) for pair in raw for value in pair):
            return None
        pts = _dedup_exact([(float(lat), float(lon)) for lat, lon in raw])
        if len(pts) < 2 or any(not math.isfinite(lat) or not math.isfinite(lon)
                              or not -90 <= lat <= 90 or not -180 <= lon <= 180 for lat, lon in pts):
            return None
        if dist_m(pts[0], origin) > ENDPOINT_TOLERANCE_M or dist_m(pts[-1], destination) > ENDPOINT_TOLERANCE_M:
            return None
        measured = sum(dist_m(a, b) for a, b in zip(pts, pts[1:]))
        if measured > max(distance * 1.5, distance + 100):
            return None
        return {"points": pts, "distance": distance, "source": option["source"]}
    except (ValueError, TypeError, OverflowError):
        return None


def _fetch_route_legs(checkpoints, key, verbose=True):
    """按固定点位顺序请求各段候选；每段只发一次正常v5请求。"""
    legs = []
    for index, origin in enumerate(checkpoints):
        destination = checkpoints[(index + 1) % len(checkpoints)]
        try:
            candidates = _amap_walking(origin, destination, key, all_routes=True)
        except (requests.RequestException, RuntimeError, ValueError, TypeError):
            warn(f"段 {index} 高德规划失败，请检查服务权限或网络")
            return None
        options = []
        for pts, distance, source in candidates[:MAX_ALTERNATIVES]:
            option = _validate_leg_option({"points": pts, "distance": distance, "source": source}, origin, destination)
            if option is not None:
                options.append(option)
        if not options:
            warn(f"段 {index} 没有完整、有效的高德候选道路")
            return None
        legs.append(options)
        if verbose:
            dim(f"[段 {index}] {len(options)}条候选道路")
        time.sleep(SLEEP_BETWEEN)
    return legs


def _options_digest(legs):
    """计算分段候选的规范内容摘要，防止读取被意外改动的缓存。"""
    return hashlib.sha256(json.dumps(legs, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _validated_legs(value, checkpoints):
    """校验候选缓存的段数、每段上限和所有道路，不接受部分损坏缓存。"""
    if not isinstance(value, list) or len(value) != len(checkpoints):
        return None
    legs = []
    for index, candidates in enumerate(value):
        if not isinstance(candidates, list) or not 1 <= len(candidates) <= MAX_ALTERNATIVES:
            return None
        options = [_validate_leg_option(option, checkpoints[index], checkpoints[(index + 1) % len(checkpoints)])
                   for option in candidates]
        if any(option is None for option in options):
            return None
        if len({_ring_digest(option["points"]) for option in options}) != len(options):
            return None
        legs.append(options)
    return legs


def _assemble_loop(legs, choices):
    """拼接所选的真实道路；接缝或闭合失败时拒绝，不跨区域补直线。"""
    loop_gcj = []
    for options, choice in zip(legs, choices):
        pts = options[choice]["points"]
        if loop_gcj and dist_m(pts[0], loop_gcj[-1]) > JOIN_TOLERANCE_M:
            return None
        if loop_gcj and dist_m(pts[0], loop_gcj[-1]) < 2.0:
            pts = pts[1:]
        loop_gcj.extend(pts)
    if not loop_gcj or dist_m(loop_gcj[-1], loop_gcj[0]) > JOIN_TOLERANCE_M:
        return None
    if loop_gcj[-1] != loop_gcj[0]:
        loop_gcj.append(loop_gcj[0])
    loop_gcj = _dedup_exact(_sanitize(loop_gcj))
    if len(loop_gcj) < 2:
        return None
    if loop_gcj[-1] != loop_gcj[0]:
        loop_gcj.append(loop_gcj[0])
    return [gcj02_to_bd09(lat, lon) for lat, lon in loop_gcj]


def _select_loop(legs, checkpoints_bd, route_seed):
    """由种子确定分段道路组合，跳过断线组合，保持选择可复现。"""
    if type(route_seed) is not int:
        raise ValueError("道路随机种子必须为整数")
    counts = [len(options) for options in legs]
    total = math.prod(counts)
    for offset in range(min(total, MAX_COMBINATION_TRIES)):
        variant = (route_seed + offset) % total
        remainder = variant
        choices = []
        for count in counts:
            choices.append(remainder % count)
            remainder //= count
        ring = _validated_ring(_assemble_loop(legs, choices), checkpoints_bd)
        if ring is not None:
            return ring, {"segment_candidates": counts, "candidate_combinations": total,
                          "selected_variant": variant + 1, "road_fingerprint": _ring_digest(ring)[:12]}
    raise RuntimeError("高德候选道路无法连续闭合，停止生成；不会补直线或使用拟合环")


def build_loop(checkpoints_bd, key, verbose=True, checkpoints_gcj=None, route_seed=0):
    """请求候选并选择一条闭环，保留直接调用者的BD折线返回格式。"""
    checkpoints_gcj = checkpoints_gcj or [bd09_to_gcj02(*point) for point in checkpoints_bd]
    legs = _fetch_route_legs(checkpoints_gcj, key, verbose)
    if not legs:
        return None
    try:
        ring, _ = _select_loop(legs, checkpoints_bd, route_seed)
        return ring
    except RuntimeError:
        return None


def _validated_ring(value, checkpoints):
    """校验路线有限坐标、闭合和点位覆盖；无效缓存不得进入生成器。"""
    try:
        if not isinstance(value, list) or len(value) < 3:
            return None
        ring = [(float(lat), float(lon)) for lat, lon in value]
        if any(not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180 for lat, lon in ring):
            return None
        if len(set(ring)) < 2 or dist_m(ring[0], ring[-1]) > JOIN_TOLERANCE_M:
            return None
        if any(min(dist_m(point, vertex) for vertex in ring) > ENDPOINT_TOLERANCE_M for point in checkpoints):
            return None
        return ring
    except (ValueError, TypeError, OverflowError):
        return None


def get_campus_loop(points, force_rebuild=False, route_seed=0, with_metadata=False):
    """从完整候选缓存按种子选路，不把整个闭环固定成同一道路。

    points: fetch_points 返回的原始点位（有效 glat/glon 优先）
    默认返回BD坐标数组；with_metadata=True时同时返回候选数量和道路指纹。
    """
    cache_path = app_config.DATA_DIR / "campus_loop_bd.json"
    normalized = [checkpoint_coordinates(p) for p in points]
    checkpoints_bd = [p[0] for p in normalized]
    checkpoints_gcj = [p[1] for p in normalized]
    if len(checkpoints_bd) < 2 or len(set(checkpoints_bd)) < 2:
        raise RuntimeError(f"打卡点不足（{len(checkpoints_bd)} 个），无法生成环")

    fp = _points_fingerprint(checkpoints_gcj)

    if type(route_seed) is not int:
        raise ValueError("道路随机种子必须为整数")
    legs = None
    if not force_rebuild and cache_path.exists():
        cached = load_json(cache_path)
        if isinstance(cached, dict) and cached.get("schema") == CACHE_SCHEMA and cached.get("provider") == CACHE_PROVIDER and cached.get("fingerprint") == fp:
            stamp = cached.get("ts")
            age_ok = isinstance(stamp, (int, float)) and 0 <= time.time() * 1000 - stamp < CACHE_TTL_MS
            candidate_legs = _validated_legs(cached.get("legs"), checkpoints_gcj) if age_ok else None
            if candidate_legs is not None and cached.get("options_digest") == _options_digest(candidate_legs):
                legs = candidate_legs
                ok("高德候选缓存命中，本次仍按随机种子选择道路")
                archive = current_archive()
                if archive:
                    archive.record_message("route-cache", "CACHE", cache_path.name,
                                           request={"fingerprint": fp},
                                           response={"hit": True, "ageMs": time.time() * 1000 - stamp,
                                                     "legCount": len(candidate_legs)})

    fresh = legs is None
    if fresh:
        archive = current_archive()
        if archive:
            archive.record_message("route-cache", "CACHE", cache_path.name,
                                   request={"fingerprint": fp}, response={"hit": False})
        key = get_amap_key()
        if not key:
            raise RuntimeError("未配置高德 Key：先执行 `lbs-amap --key <你的Key>` "
                               "或设置环境变量 FUNSPORT_AMAP_KEY")
        ok(f"高德候选道路生成中（{len(checkpoints_bd)} 打卡点）")
        legs = _fetch_route_legs(checkpoints_gcj, key)
        if not legs:
            raise RuntimeError("高德未返回有效候选道路，停止生成，不使用拟合环替代")
    ring, selection = _select_loop(legs, checkpoints_bd, route_seed)
    if fresh:
        save_json(cache_path, {"schema": CACHE_SCHEMA, "provider": CACHE_PROVIDER,
                              "fingerprint": fp, "legs": legs, "options_digest": _options_digest(legs),
                              "ts": int(time.time() * 1000)})
        ok("高德分段候选已缓存，换种子可复用候选选路")
    if selection["candidate_combinations"] == 1:
        warn("高德各段仅返回一条有效道路，当前点位顺序下没有备选道路")
    else:
        ok("道路组合 {}/{}，道路指纹 {}".format(selection["selected_variant"],
                                              selection["candidate_combinations"], selection["road_fingerprint"]))
    return (ring, selection) if with_metadata else ring
