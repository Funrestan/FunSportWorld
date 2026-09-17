"""几何与随机工具。"""
import math
import random
from datetime import datetime

MET_PER_DEG_LAT = 111132.0
MET_PER_DEG_LNG = 86600.0


def round_to(x, n):
    return float(f"{x:.{n}f}")


class Rng:
    def __init__(self, seed):
        self.r = random.Random(seed)

    def random(self):           return self.r.random()
    def uniform(self, a, b):    return self.r.uniform(a, b)
    def randint(self, a, b):    return self.r.randint(a, b)
    def gauss(self, mu, sigma): return self.r.gauss(mu, sigma)
    def choice(self, items):    return self.r.choice(items)

    def weighted(self, items):
        total = sum(w for _, w in items)
        u = self.r.uniform(0, total)
        for v, w in items:
            u -= w
            if u < 0:
                return v
        return items[-1][0]


def make_point_ring(bd_points):
    n = len(bd_points)
    if n == 0:
        return [], [0.0], (0.0, 0.0)
    cx = sum(p[0] for p in bd_points) / n
    cy = sum(p[1] for p in bd_points) / n
    ordered = sorted(bd_points, key=lambda p: math.atan2(p[0] - cx, p[1] - cy))
    plane = [((p[1] - cy) * MET_PER_DEG_LNG, (p[0] - cx) * MET_PER_DEG_LAT)
             for p in ordered]

    samples = 18
    dense = []
    for i in range(n):
        p0 = plane[(i - 1) % n]
        p1 = plane[i]
        p2 = plane[(i + 1) % n]
        p3 = plane[(i + 2) % n]
        for j in range(samples):
            t = j / samples
            t2, t3 = t * t, t * t * t
            x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t
                       + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                       + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t
                       + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                       + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            dense.append((x, y))

    arcs = [0.0]
    for i in range(1, len(dense) + 1):
        a = dense[i - 1]
        b = dense[i % len(dense)]
        arcs.append(arcs[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    return dense, arcs, (cx, cy)


def ring_point_at(dense, arcs, s):
    total = arcs[-1] if arcs else 1.0
    s = s % total
    lo, hi = 0, len(arcs)
    while lo < hi:
        mid = (lo + hi) // 2
        if arcs[mid] < s:
            lo = mid + 1
        else:
            hi = mid
    i = max(lo, 1)
    a = dense[(i - 1) % len(dense)]
    b = dense[i % len(dense)]
    seg = arcs[i] - arcs[i - 1]
    t = (s - arcs[i - 1]) / seg if seg > 0 else 0.0
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def to_bd(x, y, c_lat, c_lng):
    return (c_lat + y / MET_PER_DEG_LAT, c_lng + x / MET_PER_DEG_LNG)


def fmt_gain_time(ms):
    return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M:%S")
