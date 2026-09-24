"""轨迹后处理。"""
from .geom import round_to, fmt_gain_time


def apply_post_fixes(locs, rng, start_ms, ordered_path=False):
    """有序规划只标终点；旧拟合模式保留原后处理，不伪造规划段的事件。"""
    if ordered_path:
        if locs:
            locs[-1]["type"] = 6
        return
    if len(locs) >= 4:
        ci = len(locs) - 1
        while ci > 0 and locs[ci]["type"] == -1:
            ci -= 1
        if ci > 1:
            stop_t = locs[ci]["totalTime"] + rng.randint(6, 14)
            locs[ci]["totalTime"] = stop_t
            locs[ci]["validTime"] = stop_t
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

    if locs:
        locs[0].update({"totalTime": 0, "validTime": 0, "state": 1,
                        "type": rng.choice([0, 0, 0, 7]), "locType": 1,
                        "radius": round_to(rng.uniform(1.5, 3.0), 2)})
