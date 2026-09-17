"""自然轨迹生成器。"""
import math

from .geom import (round_to, Rng, make_point_ring, ring_point_at, to_bd,
                   MET_PER_DEG_LAT, MET_PER_DEG_LNG, fmt_gain_time,
                   SPEED_FLOOR, SPEED_CEIL)
from ..logger import log, ok, dim


def fit_speeds(w, dts, target):
    for _ in range(24):
        cur = sum(x * dt for x, dt in zip(w, dts))
        if abs(cur - target) <= 1.0:
            break
        k = target / cur
        for i in range(len(w)):
            w[i] = min(max(w[i] * k, SPEED_FLOOR), SPEED_CEIL)
    for i in range(len(w)):
        w[i] = min(max(w[i], SPEED_FLOOR), SPEED_CEIL)


def _make_dips(rng, dur):
    dips = []
    for _ in range(rng.choice([1, 1, 2])):
        dips.append((rng.uniform(0.15, 0.75) * dur,
                     rng.uniform(25, 55), rng.uniform(0.08, 0.16)))
    return dips


def _dip_factor(tt, dips):
    f = 1.0
    for c, hw, d in dips:
        if abs(tt - c) < hw:
            f *= 1.0 - d * 0.5 * (1 + math.cos(math.pi * (tt - c) / hw))
    return f


def build(dist, dur, seed, start_ms, points_bd,
          ordered_path=False, cadence_target=0):
    """生成轨迹。

    cadence_target: 目标步频 spm（0 = 自动按速度推算）
    """
    rng = Rng(seed)
    log.info(f"[track] 生成 {dist:.0f}m / {dur}s seed={seed} "
             f"点位={len(points_bd)} 模式={'真实路径' if ordered_path else '拟合环'}"
             f" 步频={cadence_target:.0f}spm" if cadence_target > 0 else "")

    dense, arcs, (c_lat, c_lng) = make_point_ring(points_bd, ordered=ordered_path)
    ring_len = arcs[-1] if arcs else 0.0

    if ordered_path:
        direction = 1.0
        s0 = 0.0
        s_limit = dist
        jitter_sigma = 0.40
        jitter_ar = 0.55
        log.info(f"[track] 环长 {ring_len:.0f}m，只跑前 {dist:.0f}m")
    else:
        direction = rng.choice([1.0, -1.0])
        s0 = rng.uniform(0, ring_len)
        s_limit = float("inf")
        jitter_sigma = 0.75
        jitter_ar = 0.72

    phase_v = rng.uniform(0, math.tau)
    phase_l = rng.uniform(0, math.tau)

    times = []
    t = 0.0
    while t < dur:
        times.append(t)
        t += 5.0 if rng.random() < 0.80 else rng.choice([1, 2, 3, 4, 6, 7, 8])
    n_max = len(times)

    dips = _make_dips(rng, dur)
    base = dist / dur

    w = []
    for tt in times:
        ramp = 1.0
        if tt < 8.0:
            ramp = min(0.85 + 0.15 * (tt / max(1.0, min(8.0, dur / 20))), 1.0)
        if tt > dur - 8.0:
            ramp *= 1.0 + 0.03 * (tt - (dur - 8.0)) / 8.0
        km_done = (tt / dur) * dist / 1000.0
        fatigue = 1.03 if km_done <= 0.5 else max(1.03 - 0.06 * (km_done - 0.5), 0.80)
        wave = (1.0
                + 0.010 * math.sin(math.tau * tt / 115.0 + phase_v)
                + 0.035 * math.sin(math.tau * tt / 47.0 + phase_v * 2.3)
                + 0.015 * math.sin(math.tau * tt / 19.0 + phase_v * 3.7)) * _dip_factor(tt, dips)
        noise = 1.0 + rng.gauss(0, 0.008)
        w.append(base * ramp * fatigue * wave * noise)

    dts = [times[i + 1] - times[i] for i in range(n_max - 1)]
    dts.append(max(1.0, dur - times[-1]))
    fit_speeds(w, dts, dist)
    dim(f"速度拟合：{n_max} 点 平均 {dist/dur:.2f} m/s")

    kinds = []
    for _ in range(n_max):
        u = rng.random()
        if u < 0.39:
            kinds.append((3, 1))
        elif u < 0.93:
            kinds.append((0, 1))
        elif u < 0.96:
            kinds.append(rng.weighted([((-1, 4), 54), ((-1, 1), 27),
                                       ((-1, 12), 13), ((-1, 5), 3),
                                       ((-1, 6), 2)]))
        else:
            kinds.append((rng.choice([1, 1, 1, 1, 2, 2]), 1))
    for i in range(1, n_max):
        if kinds[i][0] == -1 and kinds[i - 1][0] == -1:
            kinds[i] = (rng.choice([3, 0]), 1)

    locs = []
    s = s0
    t_acc = dist_acc = steps_acc = 0.0
    jx = jy = 0.0
    alt = 82.0 + rng.uniform(-1, 1)
    n_est = max(1, int(dur / 5))
    alt_sigma = rng.uniform(3.8, 6.2) / (0.40 * n_est)

    for i in range(n_max):
        dt = dts[i]
        typ, lt = kinds[i]
        t_acc += dt
        d_step = 0.0
        if typ != -1:
            d_step = w[i] * dt
            if ordered_path and (s - s0 + d_step) > s_limit:
                d_step = max(0.0, s_limit - (s - s0))
            s += direction * d_step
            bx, by = ring_point_at(dense, arcs, s)
            jx = jitter_ar * jx + rng.gauss(0, jitter_sigma)
            jy = jitter_ar * jy + rng.gauss(0, jitter_sigma)
            px, py = bx + jx, by + jy
            dist_acc += d_step
        else:
            if locs:
                py = (locs[-1]["gLat"] - c_lat) * MET_PER_DEG_LAT
                px = (locs[-1]["gLng"] - c_lng) * MET_PER_DEG_LNG
            else:
                px = py = 0.0

        lat, lng = to_bd(px, py, c_lat, c_lng)
        alt += 0.04 * (82.0 - alt) + rng.gauss(0, alt_sigma)

        # ── 步频：优先用 cadence_target ──
        v_now = dist / dur
        if cadence_target > 0:
            cad = cadence_target * (1.0 + rng.gauss(0, 0.03))
            cad = min(max(cad, 60.0), 220.0)
        else:
            stride = (0.62 + 0.17 * v_now
                      + 0.03 * math.sin(math.tau * t_acc / 200 + phase_l)
                      + rng.gauss(0, 0.008))
            v_cad = v_now * (1 + 0.03 * math.sin(math.tau * t_acc / 70 + phase_v))
            cad = min(max(v_cad / stride * 60, 100), 200)
        steps_acc += cad / 60 * dt

        if typ == -1:
            avg_sp = round_to(dist_acc / max(1, t_acc), 4)
            gps = round_to(rng.uniform(15, 46) if rng.random() < 0.12
                           else rng.uniform(0.5, 6.0), 4)
        else:
            avg_sp = round_to(d_step / dt, 4) if dt > 0 else 0.0
            kmh = avg_sp * 3.6
            sigma = max(kmh * 0.08, 0.05)
            gps = 0.0 if rng.random() < 0.20 else round_to(max(0, kmh + rng.gauss(0, sigma)), 4)

        locs.append({
            "id": i + 1, "flag": start_ms,
            "lat": -1.0, "lng": -1.0,
            "gLat": round_to(lat, 7), "gLng": round_to(lng, 7),
            "speed": round_to(gps, 4), "avgSpeed": avg_sp,
            "radius": round_to(rng.uniform(1.4, 5.1) if typ == 3 else rng.uniform(1.4, 2.4), 2),
            "accuracy": round_to(rng.uniform(1.4, 2.4), 2),
            "type": typ, "locType": lt,
            "hasAltitude": True,
            "totalTime": int(round(t_acc)),
            "totalDis": round_to(dist_acc, 4),
            "validDis": round_to(dist_acc, 4),
            "validTime": int(round(t_acc)),
            "steps": int(steps_acc),
            "stepDistance": 0.0,
            "gainTime": fmt_gain_time(start_ms + int(t_acc * 1000)),
            "gainTimeMs": start_ms + int(t_acc * 1000),
            "queueNum": 0, "coorType": "gcj02",
            "bdA": round_to(alt, 2),
            "bdD": round_to((math.atan2(1, 1) * 180 / math.pi + rng.gauss(0, 35)) % 360, 2),
            "bdS": round_to(max(avg_sp * rng.uniform(0.6, 0.95), 0.0), 3),
            "bdG": rng.choice([1, 1, 1, -1]),
            "count": rng.randint(20, 88), "dtr": 0.0,
            "state": rng.weighted([(1, 145), (2, 256), (3, 151)]) if typ != 0
                     else rng.weighted([(1, 145), (2, 45), (3, 164)]),
            "locationId": "",
        })

        if ordered_path and (s - s0) >= s_limit - 0.5:
            break

    from .postfix import apply_post_fixes
    apply_post_fixes(locs, rng, start_ms)

    snap_radius = 20.0 if ordered_path else 40.0
    for pl in points_bd:
        best_i, best_d = None, 1e18
        for i, q in enumerate(locs):
            dd = ((q["gLat"] - pl[0]) * MET_PER_DEG_LAT) ** 2 + \
                 ((q["gLng"] - pl[1]) * MET_PER_DEG_LNG) ** 2
            if dd < best_d:
                best_d, best_i = dd, i
        if best_i is not None and best_d < snap_radius * snap_radius:
            locs[best_i]["gLat"] = round_to(pl[0], 7)
            locs[best_i]["gLng"] = round_to(pl[1], 7)

    speed_win, steps_win = [], []
    ten_t = ten_d = ten_st = 0.0
    n_used = len(locs)
    for i in range(n_used):
        ten_t += dts[i] if i < len(dts) else 0.0
        ten_d += w[i] * (dts[i] if i < len(dts) else 0.0)
        ten_st += (locs[i]["steps"] - (locs[i - 1]["steps"] if i else 0))
        while ten_t >= 10.0:
            k = 10.0 / ten_t
            out_d, out_st = ten_d * k, ten_st * k
            speed_win.append({"time": 10, "value": round_to(out_d, 2)})
            steps_win.append({"time": 10, "value": round_to(out_st, 0)})
            ten_t -= 10.0
            ten_d -= out_d
            ten_st -= out_st
    if ten_t > 1.0:
        k = min(10.0 / ten_t, 1.4)
        speed_win.append({"time": 10, "value": round_to(ten_d * k, 2)})
        steps_win.append({"time": 10, "value": round_to(ten_st * k, 0)})

    total_dis_actual = dist_acc
    total_t_actual = int(round(t_acc))
    track = {
        "totalTime": total_t_actual,
        "totalDistance": round_to(total_dis_actual, 3),
        "validDistance": round_to(total_dis_actual, 3),
        "validTime": total_t_actual,
        "startTime": start_ms,
        "startLatitude": locs[0]["gLat"] if locs else 0.0,
        "startLongitude": locs[0]["gLng"] if locs else 0.0,
        "totalSteps": int(steps_acc),
        "locations": locs,
        "speedPerTenSec": speed_win,
        "stepsPerTenSec": steps_win,
    }
    avg_cad = (track["totalSteps"] / total_t_actual * 60) if total_t_actual > 0 else 0
    ok(f"轨迹完成 {len(locs)} 点 totalDis={track['totalDistance']:.0f}m "
       f"steps={track['totalSteps']} 平均步频={avg_cad:.0f}spm")
    return track