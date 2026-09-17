"""全链编排：policy → 点位 → 轨迹 → 提交 → OBS → 验证。"""
import json
import math
import random
import time

from . import policy as api_policy
from . import points as api_points
from . import submit as api_submit
from . import obs as api_obs
from . import records as api_records
from . import campus_loop as api_loop
from ..config import load_config
from ..track import generator, wire
from ..track.geom import MET_PER_DEG_LAT, MET_PER_DEG_LNG, SPEED_FLOOR, SPEED_CEIL
from ..logger import log, ok, warn, step


def _ring_length(ring):
    total = 0.0
    for i in range(1, len(ring)):
        a, b = ring[i - 1], ring[i]
        total += math.hypot((a[0] - b[0]) * MET_PER_DEG_LAT,
                            (a[1] - b[1]) * MET_PER_DEG_LNG)
    return total


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


def run_full_flow(client, dist=0, pace=0, cadence=0, start_ms=0,
                  face_check=1, seed=0, use_map=False, auto=False,
                  dist_min=None, dist_max=None,
                  pace_min=None, pace_max=None,
                  cadence_min=None, cadence_max=None,
                  min_dist=None):
    log.info("═══ 跑步全链开始 ═══")

    step("[1/6] 拉取跑步策略…")
    pol = api_policy.fetch_policy(client)
    sel_dist = pol.min_distance
    ok(f"[policy] ts={pol.timestamp} 学校要求 {sel_dist}m")
    time.sleep(1)

    if auto and not use_map:
        use_map = True
        warn("--auto 已自动启用 --use-map")

    dist_m, pace_s, cadence_spm = _resolve_params(
        dist, pace, cadence, auto, sel_dist,
        dist_min, dist_max, pace_min, pace_max,
        cadence_min, cadence_max, min_dist,
    )
    if dist_m <= 0:
        raise RuntimeError("距离未指定（用 --dist / --dist-min / --auto）")
    if pace_s <= 0:
        pace_s = 400
        warn(f"配速未指定，用默认 {pace_s} s/km")

    dur = int(dist_m / 1000 * pace_s)
    log.info(f"最终参数：{dist_m:.0f}m / {dur}s / 配速 {pace_s:.0f}s/km "
             f"/ 步频 {cadence_spm:.0f}spm")

    step("[2/6] 拉取实时点位（整组）…")
    pts = api_points.fetch_points(client)
    if not pts:
        raise RuntimeError("点位为空")
    ok(f"点位 {len(pts)} 个")

    if use_map:
        step("[2.5/6] 生成/加载校园环（高德）…")
        ring_input = api_loop.get_campus_loop(pts)
        ring_len = _ring_length(ring_input)
        ok(f"校园环 {len(ring_input)} 点，环长 {ring_len:.0f}m")
        if dist_m < ring_len:
            warn(f"目标 {dist_m:.0f}m < 环长 {ring_len:.0f}m，抬到 "
                 f"{ring_len + 50:.0f}m 保证闭合")
            dist_m = ring_len + 50
            dur = int(dist_m / 1000 * pace_s)
        pts_bd = ring_input
    else:
        pts_bd = api_points.points_bd(pts)

    step("[3/6] 生成轨迹…")
    if seed == 0:
        seed = int(time.time() * 1000) % 2_147_483_647
    avg = dist_m / dur
    fixed_avg = min(max(avg, SPEED_FLOOR + 0.1), SPEED_CEIL - 0.1)
    if abs(fixed_avg - avg) > 1e-6:
        dur = int(round(dist_m / fixed_avg))
        warn(f"配速越界，时长修正为 {dur}s")
    start_ms = start_ms or (int(time.time() * 1000) - random.randint(30, 300) * 60_000)
    start_ms += random.randint(0, 4) * 1000

    track = generator.build(dist_m, dur, seed, start_ms, pts_bd,
                            ordered_path=use_map,
                            cadence_target=cadence_spm)

    five = wire.five_point_wrapper(pts, track["startTime"])

    step("[4/6] 提交跑步记录…")
    result = api_submit.submit_record(
        client, track,
        policy_ts=pol.timestamp, policy=pol.policy,
        min_distance=pol.min_distance,
        weight=client.session_data.get("weight", 68.0),
        face_check=face_check,
        five_point_json=five,
    )
    time.sleep(1)

    step("[5/6] 上传 OBS 对象…")
    obj = wire.build_obs_object(
        track, result["rrid"], result["uuid"],
        client.uid(), pts,
    )
    payload = json.dumps(obj, separators=(",", ":")).encode()
    keys = wire.obs_keys(track, result["rrid"], result["uuid"])
    obs_ok = api_obs.upload_both_keys(client, keys, payload)
    if obs_ok == 2:
        ok("OBS 双 key 上传成功")
    else:
        warn(f"OBS 上传 {obs_ok}/2")

    step("[6/6] 拉取详情验证…")
    time.sleep(2)
    detail_ok = False
    try:
        detail = api_records.fetch_one_record(client, result["rrid"])
        ok(f"验证 rrid={result['rrid']} complete={detail.get('complete')} "
           f"dis={detail.get('totalDis')} time={detail.get('totalTime')}")
        detail_ok = True
    except Exception as e:
        warn(f"验证失败（提交已成功）: {e}")

    log.info("═══ 跑步全链结束 ═══")
    result["obs_ok"] = obs_ok
    result["detail_ok"] = detail_ok
    result["dist"] = track["totalDistance"]
    result["dur"] = track["totalTime"]
    result["cadence_avg"] = (track["totalSteps"] / track["totalTime"] * 60
                             if track["totalTime"] > 0 else 0)
    return result