"""全链编排：policy → 点位 → 轨迹 → 提交 → OBS → 验证。"""
import json
import math
import random
import time
from datetime import datetime, time as dtime, timedelta

from . import policy as api_policy
from . import points as api_points
from . import submit as api_submit
from . import obs as api_obs
from . import records as api_records
from . import campus_loop as api_loop
from ..config import load_config, load_points_cache
from ..coordinates import coordinate_report
from ..diagnostics import analyze_checkpoints, format_report
from ..run_plan import RunPlan, checkpoint_distances, prepare_checkpoint_order
from ..track import generator, wire
from ..track.geom import MET_PER_DEG_LAT, MET_PER_DEG_LNG, SPEED_FLOOR, SPEED_CEIL
from ..logger import log, ok, warn, step, err


def _ring_length(ring):
    """用与现有生成器一致的距离单位估算规划环长度。"""
    total = 0.0
    for i in range(1, len(ring)):
        a, b = ring[i - 1], ring[i]
        total += math.hypot((a[0] - b[0]) * MET_PER_DEG_LAT,
                            (a[1] - b[1]) * MET_PER_DEG_LNG)
    return total


def _check_time_window(start_ms, dur, valid_time):
    """检查 [start_ms, start_ms + dur*1000] 是否落在 valid_time 任一段内。

    valid_time 格式：[{"start": "HH:MM:SS", "end": "HH:MM:SS"}, ...]
    返回 (ok, reason)。
    """
    if not valid_time:
        return True, "未配置时间窗口（跳过校验）"

    start_dt = datetime.fromtimestamp(start_ms / 1000)
    stop_dt = datetime.fromtimestamp((start_ms + dur * 1000) / 1000)
    windows_str = []
    for w in valid_time:
        try:
            ws = dtime.fromisoformat(w["start"])
            we = dtime.fromisoformat(w["end"])
        except Exception:
            continue
        windows_str.append(f"{w['start']}~{w['end']}")
        # 同时检查前一天起始的跨午夜窗口；要求整个跑步区间被包含。
        for offset in (-1, 0):
            day = start_dt.date() + timedelta(days=offset)
            begin = datetime.combine(day, ws)
            end = datetime.combine(day + timedelta(days=int(we < ws)), we)
            if begin <= start_dt and stop_dt <= end:
                return True, f"落在 {w['start']}~{w['end']} 窗口内"

    return False, (
        f"起点 {start_dt.strftime('%H:%M:%S')} / "
        f"终点 {stop_dt.strftime('%H:%M:%S')} "
        f"不在有效窗口 [{', '.join(windows_str)}]"
    )


def _resolve_params(dist, pace, cadence, auto, sel_dist,
                    dist_min, dist_max, pace_min, pace_max,
                    cadence_min, cadence_max, min_dist):
    """统一解析最终 (dist_m, pace_s, cadence_spm)。"""
    cfg = load_config()

    # ── 距离 ──
    if auto:
        ex_min = cfg.get("auto_dist_extra_min", 0.10)
        ex_max = cfg.get("auto_dist_extra_max", 0.30)
        extra = random.uniform(ex_min, ex_max)
        base = sel_dist if sel_dist > 0 else 2600
        dist_m = base * (1 + extra)
        log.info(f"[auto] 学校要求 {sel_dist}m，冗余 {extra*100:.0f}% → {dist_m:.0f}m")
    elif dist_min or dist_max:
        dmin = dist_min or cfg.get("dist_min", 1.0)
        dmax = dist_max or cfg.get("dist_max", 1.5)
        if dmin > dmax:
            dmin, dmax = dmax, dmin
        dist_m = random.uniform(dmin, dmax) * 1000
        log.info(f"[dist] 范围 {dmin:.2f}~{dmax:.2f} km 随机 → {dist_m:.0f}m")
    elif dist and dist > 0:
        dist_m = dist * 1000 if dist < 100 else dist
        log.info(f"[dist] 固定 {dist_m:.0f}m")
    else:
        dist_m = 0

    if sel_dist > 0 and dist_m < sel_dist:
        warn(f"目标 {dist_m:.0f}m < 学校要求 {sel_dist}m，自动抬到 {sel_dist}m")
        dist_m = float(sel_dist)

    if min_dist and dist_m < min_dist:
        warn(f"目标 {dist_m:.0f}m < 强制下限 {min_dist}m，抬到 {min_dist}m")
        dist_m = float(min_dist)

    # ── 配速 ──
    if auto:
        pmin = cfg.get("auto_pace_min_s", 360)
        pmax = cfg.get("auto_pace_max_s", 480)
        pace_s = random.uniform(pmin, pmax)
        log.info(f"[auto] 配速 {pmin}~{pmax} s/km 随机 → {pace_s:.0f} s/km")
    elif pace_min or pace_max:
        pmin = pace_min or cfg.get("pace_min", 360)
        pmax = pace_max or cfg.get("pace_max", 480)
        if pmin > pmax:
            pmin, pmax = pmax, pmin
        pace_s = random.uniform(pmin, pmax)
        log.info(f"[pace] 范围 {pmin}~{pmax} s/km 随机 → {pace_s:.0f} s/km")
    elif pace and pace > 0:
        pace_s = pace
        log.info(f"[pace] 固定 {pace_s:.0f} s/km")
    else:
        pace_s = 0

    # ── 步频 ──
    if auto:
        cmin = cfg.get("auto_cadence_min", 130)
        cmax = cfg.get("auto_cadence_max", 170)
        cadence_spm = random.uniform(cmin, cmax)
        log.info(f"[auto] 步频 {cmin}~{cmax} spm 随机 → {cadence_spm:.0f} spm")
    elif cadence_min or cadence_max:
        cmin = cadence_min or 130
        cmax = cadence_max or 170
        if cmin > cmax:
            cmin, cmax = cmax, cmin
        cadence_spm = random.uniform(cmin, cmax)
        log.info(f"[cadence] 范围 {cmin}~{cmax} spm 随机 → {cadence_spm:.0f} spm")
    elif cadence and cadence > 0:
        cadence_spm = cadence
        log.info(f"[cadence] 固定 {cadence_spm:.0f} spm")
    else:
        cadence_spm = 0

    return dist_m, pace_s, cadence_spm


def _resolve_start_ms(before, start_ms):
    """解析最终 start_ms。优先级：--before > 上游传入 > config 范围随机。"""
    if before and before > 0:
        ms = int(time.time() * 1000) - before * 60_000
        log.info(f"[time] --before 固定提前 {before} 分钟")
    elif start_ms and start_ms > 0:
        ms = start_ms
        log.info(f"[time] 上游指定 start_ms={start_ms}")
    else:
        cfg = load_config()
        bmin = max(1, int(cfg.get("start_before_min", 30)))
        bmax = max(bmin, int(cfg.get("start_before_max", 300)))
        if bmin == bmax:
            ms = int(time.time() * 1000) - bmin * 60_000
            log.info(f"[time] config 固定提前 {bmin} 分钟")
        else:
            before_min = random.randint(bmin, bmax)
            ms = int(time.time() * 1000) - before_min * 60_000
            log.info(f"[time] config 范围 {bmin}~{bmax} 分钟随机 → 提前 {before_min} 分钟")
    ms += random.randint(0, 4) * 1000
    return ms


def _build_amap_track(points, dist_m, pace_s, cadence, seed, start_ms):
    """同一种子选择高德候选道路并生成轨迹，失败时不使用拟合环替代。"""
    ring, selection = api_loop.get_campus_loop(points, route_seed=seed, with_metadata=True)
    ring_len = _ring_length(ring)
    if not math.isfinite(ring_len) or ring_len <= 0:
        raise ValueError("高德规划路线为空或没有有效长度")
    if dist_m < ring_len:
        dist_m = ring_len + 50
        warn("目标距离不足一圈，调整到 {:.0f}m；以预览显示为准".format(dist_m))
    duration = max(1, int(dist_m / 1000 * pace_s))
    avg = dist_m / duration
    fixed_avg = min(max(avg, SPEED_FLOOR + 0.1), SPEED_CEIL - 0.1)
    if abs(fixed_avg - avg) > 1e-6:
        duration = max(1, int(round(dist_m / fixed_avg)))
    if duration > 86400:
        raise ValueError("沿高德路线生成后的时长超过 24 小时，停止生成")
    track = generator.build(dist_m, duration, seed, start_ms, ring,
                            ordered_path=True, cadence_target=cadence)
    return track, {"provider": "amap_walking", "vertex_count": len(ring),
                   "ring_length_m": round(ring_len, 2),
                   "complete_laps": int((track["totalDistance"] + 0.01) // ring_len), **selection}


def prepare_run_plan(client, dist=0, pace=0, cadence=0, start_ms=0,
                  face_check=1, seed=0, use_map=True, auto=False,
                  dist_min=None, dist_max=None,
                  pace_min=None, pace_max=None,
                  cadence_min=None, cadence_max=None,
                  min_dist=None, before=None,
                  allow_outside_window=False):
    """查询后按模式确定点位顺序，用同一顺序规划和冻结数据，绝不提交。"""
    log.info("═══ 生成跑步方案（不提交） ═══")

    step("[1/6] 拉取跑步策略…")
    pol = api_policy.fetch_policy(client)
    sel_dist = pol.min_distance
    ok(f"[policy] ts={pol.timestamp} 学校要求 {sel_dist}m")

    if not use_map:
        warn("现已统一使用高德步行路线；旧的 use_map=False 不再启用拟合环")
    use_map = True

    dist_m, pace_s, cadence_spm = _resolve_params(
        dist, pace, cadence, auto, sel_dist,
        dist_min, dist_max, pace_min, pace_max,
        cadence_min, cadence_max, min_dist,
    )
    if not math.isfinite(dist_m) or dist_m <= 0:
        raise RuntimeError("距离未指定（用 --dist / --dist-min / --auto）")
    if pace_s <= 0:
        pace_s = 400
        warn(f"配速未指定，用默认 {pace_s} s/km")

    if not math.isfinite(pace_s) or not math.isfinite(cadence_spm):
        raise ValueError("配速和步频必须是有限数字")
    dur = max(1, int(dist_m / 1000 * pace_s))
    if dur > 86400:
        raise ValueError("方案时长不能超过 24 小时")
    log.info(f"最终参数：{dist_m:.0f}m / {dur}s / 配速 {pace_s:.0f}s/km "
             f"/ 步频 {cadence_spm:.0f}spm")

    # ── 开始时间 ──
    start_ms = _resolve_start_ms(before, start_ms)

    step("[2/6] 拉取实时点位（整组）…")
    pts, point_metadata = api_points.fetch_points(client, with_metadata=True, allow_stale=False)
    if not pts:
        raise RuntimeError("点位为空")
    coordinates = coordinate_report(pts)
    pts = wire.five_point_payload(pts, start_ms)
    pts, checkpoint_order = prepare_checkpoint_order(pts, pol.policy)
    ok(f"点位 {len(pts)} 个")

    step("[3/6] 依据高德步行路线生成轨迹…")
    if seed == 0:
        seed = random.SystemRandom().randrange(1, 2_147_483_648)
    track, route = _build_amap_track(pts, dist_m, pace_s, cadence_spm, seed, start_ms)

    five = wire.five_point_wrapper(pts, track["startTime"], point_metadata)

    # 地图环扩展及生成器修正会改变时长，必须用最终轨迹检查窗口。
    ok_win, reason = _check_time_window(track["startTime"], track["totalTime"], pol.valid_time)
    plan = RunPlan.create(client, {
        "track": track, "points": pts, "five_point_json": five,
        "policy_ts": pol.timestamp, "policy": pol.policy, "min_distance": pol.min_distance,
        "valid_time": pol.valid_time, "window_ok": ok_win, "window_reason": reason,
        "face_check": face_check, "weight": client.session_data.get("weight", 68.0),
        "seed": seed, "use_map": True, "route": route, "allow_outside_window": bool(allow_outside_window),
        "checkpoint_distances": checkpoint_distances(track, pts),
        "coordinate_report": coordinates,
        "checkpoint_order": checkpoint_order,
    })
    ok("方案 {} 已生成，尚未提交；{}".format(plan.plan_id, reason))
    return plan


def prepare_route_preview(client, dist, pace, cadence, start_ms=0, before=0, seed=0):
    """读取匹配账号的点位缓存，通过高德规划轨迹；不访问运动服务或提交。"""
    cache = load_points_cache(with_metadata=True)
    expected = {"uid": client.uid(), "unid": str(client.session_data.get("unid", "0")),
                "anchor": [client.identity["anchor_lat"], client.identity["anchor_lon"]], "runAreaId": None}
    if not cache or cache.get("context") != expected or not cache.get("points"):
        raise ValueError("没有匹配当前账号和校园的点位缓存。请在开放时段先读取点位；轨迹预览不会向运动服务补取点位。")
    dist, pace, cadence = float(dist), float(pace), float(cadence)
    if not all(math.isfinite(value) and value > 0 for value in (dist, pace, cadence)):
        raise ValueError("距离、配速和步频必须是有限正数")
    dist_m = dist * 1000
    duration = max(1, int(dist * pace))
    if duration > 86400:
        raise ValueError("轨迹预览时长不能超过 24 小时")
    start_ms = _resolve_start_ms(before, start_ms)
    seed = seed or random.SystemRandom().randrange(1, 2_147_483_648)
    coordinates = coordinate_report(cache["points"])
    pts = wire.five_point_payload(cache["points"], start_ms)
    distinct = {(p["lat"], p["lon"]) for p in pts}
    if len(distinct) < 2:
        raise ValueError("本地点位不足两个不同坐标，无法生成轨迹")
    track, route = _build_amap_track(pts, dist_m, pace, cadence, seed, start_ms)
    plan = RunPlan.create(client, {
        "track": track, "points": pts,
        "five_point_json": wire.five_point_wrapper(pts, start_ms, cache.get("metadata", {})),
        "policy_ts": None, "policy": None, "min_distance": None,
        "valid_time": [], "window_ok": False, "window_reason": "未获取学校策略；仅轨迹预览，不可提交",
        "face_check": None, "weight": None, "seed": seed, "use_map": True, "route": route,
        "allow_outside_window": False, "preview_only": True, "points_cached_at": cache.get("ts"),
        "checkpoint_distances": checkpoint_distances(track, pts),
        "coordinate_report": coordinates,
    })
    ok("高德轨迹预览 {} 已生成；未访问运动服务，不可提交".format(plan.plan_id))
    return plan


def submit_run_plan(client, plan, allow_outside_window=None):
    """提交已预览的同一快照；不再次随机生成、重查点位或重建路线。"""
    plan.validate(client)
    data = plan.data()
    track, pts = data["track"], data["points"]
    outside = data["allow_outside_window"] if allow_outside_window is None else bool(allow_outside_window)
    ok_win, reason = _check_time_window(track["startTime"], track["totalTime"], data["valid_time"])
    if not ok_win and not outside:
        raise ValueError("方案在有效时间外：{}；可启用时间外测试开关后再次确认".format(reason))
    if track["startTime"] + track["totalTime"] * 1000 > time.time() * 1000:
        raise ValueError("方案结束时间尚未到达，不能提交未来记录")
    if outside and not ok_win:
        warn("时间外测试：跳过本地有效时段检查，服务端仍可能拒绝或判为无效")
    plan.claim(client)

    step("[4/6] 提交跑步记录…")
    result = api_submit.submit_record(
        client, track,
        policy_ts=data["policy_ts"], policy=data["policy"],
        min_distance=data["min_distance"],
        weight=data["weight"], face_check=data["face_check"],
        five_point_json=data["five_point_json"],
    )
    time.sleep(1)

    step("[5/6] 上传 OBS 对象…")
    obj = wire.build_obs_object(
        track, result["rrid"], result["uuid"],
        client.uid(), pts, point_wrapper=data["five_point_json"],
    )
    payload = json.dumps(obj, separators=(",", ":")).encode()
    keys = wire.obs_keys(track, result["rrid"], result["uuid"])
    obs_ok = api_obs.upload_both_keys(client, keys, payload)
    if obs_ok == 2:
        ok("OBS 双 key 上传成功")
    else:
        warn(f"OBS 上传 {obs_ok}/2")

    step("[6/6] 读取详情并检查打卡字段…")
    time.sleep(2)
    detail_ok = False
    checkpoint_report = None
    try:
        detail = api_records.fetch_one_record(client, result["rrid"])
        ok(f"详情读取 rrid={result['rrid']} complete={detail.get('complete')} "
           f"dis={detail.get('totalDis')} time={detail.get('totalTime')}")
        detail_ok = True
        checkpoint_report = analyze_checkpoints(detail)
        log.info(format_report(checkpoint_report))
    except Exception as e:
        warn(f"详情检查失败（记录已提交，请勿直接重复提交）: {e}")

    log.info("═══ 跑步全链结束 ═══")
    result["obs_ok"] = obs_ok
    result["detail_ok"] = detail_ok
    result["checkpoint_report"] = checkpoint_report
    result["plan_id"] = plan.plan_id
    result["dist"] = track["totalDistance"]
    result["dur"] = track["totalTime"]
    result["cadence_avg"] = (track["totalSteps"] / track["totalTime"] * 60
                             if track["totalTime"] > 0 else 0)
    return result


def run_full_flow(client, *args, **kwargs):
    """保留 CLI 一步执行入口，内部共用 GUI 的生成与提交阶段。"""
    return submit_run_plan(client, prepare_run_plan(client, *args, **kwargs))
