"""轨迹后处理。"""
from .geom import round_to, fmt_gain_time
from .generator import SPEED_FLOOR, SPEED_CEIL


def apply_post_fixes(locs, rng, start_ms):
    if len(locs) >= 4:
        ci = len(locs) - 1
        while ci > 0 and locs[ci]["type"] == -1:
            ci -= 1
        if ci > 1:
            stop_t = locs[ci]["totalTime"] + rng.randint(6, 14)
            locs[ci]["totalTime"] = stop_t
            locs[ci]["validTime"] = stop_t
            stop_v = round_to(rng.uniform(2.0, 2.6), 4)
            locs[ci]["speed"] = round_to(stop_v * 3.6, 4)
            locs[ci]["avgSpeed"] = stop_v
            locs[ci]["bdS"] = round_to(rng.uniform(0.05, 0.15), 3)
            locs[ci]["gainTime"] = fmt_gain_time(start_ms + stop_t * 1000)
            locs[ci]["gainTimeMs"] = start_ms + stop_t * 1000

    if len(locs) > 2:
        sp = locs[1]
        sp.update({"type": 5, "state": 1, "locType": 1,
                   "radius": round_to(rng.uniform(2.0, 3.5), 2),
                   "speed": 0.0, "avgSpeed": 0.0, "bdS": 0.0,
                   "totalDis": 0.0, "validDis": 0.0,
                   "totalTime": 0, "validTime": 0, "steps": 0})
        last = len(locs) - 1
        locs[last].update({"type": 6, "locType": 1,
                           "radius": round_to(rng.uniform(1.5, 3.0), 2)})
        frm = int(len(locs) * 0.67)
        for i in range(frm, max(frm, len(locs) - 2)):
            if rng.random() < 0.06:
                locs[i]["type"] = rng.choice([1, 1, 2, 8])
                locs[i]["locType"] = 1

    if len(locs) > 3:
        p2 = locs[2]
        p2["avgSpeed"] = min(max(round_to(p2["totalDis"] / max(1, p2["totalTime"]), 4),
                                 SPEED_FLOOR), SPEED_CEIL)
        p2["speed"] = round_to(p2["avgSpeed"] * 3.6, 4)

    if locs:
        locs[0].update({"totalTime": 0, "validTime": 0, "state": 1,
                        "type": rng.choice([0, 0, 0, 7]), "locType": 1,
                        "radius": round_to(rng.uniform(1.5, 3.0), 2)})
        for j in range(1, len(locs)):
            if locs[j]["avgSpeed"] > 0:
                locs[0]["avgSpeed"] = locs[j]["avgSpeed"]
                locs[0]["bdS"] = locs[j]["bdS"]
                break
        if locs[0]["speed"] == 0:
            locs[0]["speed"] = round_to(rng.uniform(7.0, 13.0), 4)
