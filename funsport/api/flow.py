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


def run_full_flow(client, dist, dur, start_ms, face_check=1, seed=0,
                  use_map=False):
    log.info("═══ 跑步全链开始 ═══")

    step("[1/6] 拉取跑步策略…")
    pol = api_policy.fetch_policy(client)
    time.sleep(1)

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
        if ring_len < dist:
            warn(f"环长 {ring_len:.0f}m < 目标 {dist:.0f}m，按环长跑")
            dist = ring_len
        pts_bd = ring_input
    else:
        pts_bd = api_points.points_bd(pts)

    step("[3/6] 生成轨迹…")
    if seed == 0:
        seed = int(time.time() * 1000) % 2_147_483_647
    avg = dist / dur
    fixed_avg = min(max(avg, SPEED_FLOOR + 0.1), SPEED_CEIL - 0.1)
    if abs(fixed_avg - avg) > 1e-6:
        dur = int(round(dist / fixed_avg))
        warn(f"配速越界，时长修正为 {dur}s")
    start_ms += random.randint(0, 4) * 1000

    track = generator.build(dist, dur, seed, start_ms, pts_bd,
                            ordered_path=use_map)

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
    return result