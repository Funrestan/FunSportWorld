"""共用坐标约定：内部元组为 (纬度, 经度)，高德参数在请求边界才反转。"""
import math

X_PI = math.pi * 3000.0 / 180.0
CONFLICT_METERS = 5.0


def coordinate_pair(lat, lon):
    """读取有限坐标，拒绝布尔、越界和 App 常见的单轴占位值。"""
    try:
        if isinstance(lat, bool) or isinstance(lon, bool):
            return None
        lat, lon = float(lat), float(lon)
        if (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90
                and -180 <= lon <= 180 and lat not in (0, -1) and lon not in (0, -1)):
            return lat, lon
    except (TypeError, ValueError, OverflowError):
        pass
    return None


def gcj02_to_bd09(lat, lon):
    """将 GCJ-02 转为 BD-09，全精度计算，仅在输出 JSON 时取舍小数。"""
    z = math.hypot(lon, lat) + 0.00002 * math.sin(lat * X_PI)
    theta = math.atan2(lat, lon) + 0.000003 * math.cos(lon * X_PI)
    return z * math.sin(theta) + 0.006, z * math.cos(theta) + 0.0065


def bd09_to_gcj02(lat, lon):
    """先近似反算，再迭代消除正反转换残差；不宣称改善原始定位精度。"""
    x, y = lon - 0.0065, lat - 0.006
    z = math.hypot(x, y) - 0.00002 * math.sin(y * X_PI)
    theta = math.atan2(y, x) - 0.000003 * math.cos(x * X_PI)
    glat, glon = z * math.sin(theta), z * math.cos(theta)
    for _ in range(6):
        check_lat, check_lon = gcj02_to_bd09(glat, glon)
        dlat, dlon = check_lat - lat, check_lon - lon
        glat, glon = glat - dlat, glon - dlon
        if max(abs(dlat), abs(dlon)) < 1e-11:
            break
    return glat, glon


def distance_m(a, b):
    """计算同坐标系两点的球面距离，返回米。"""
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371008.8 * 2 * math.asin(math.sqrt(max(0.0, min(1.0, h))))


def checkpoint_coordinates(point):
    """以有效原生高德坐标为准统一两套坐标；缺失时才从百度推算。"""
    bd = coordinate_pair(point.get("lat"), point.get("lon"))
    gcj = coordinate_pair(point.get("glat"), point.get("glon"))
    if gcj and (gcj[0] < 1 or gcj[1] < 1):
        gcj = None
    if gcj is not None:
        canonical_bd = gcj02_to_bd09(*gcj)
        delta = distance_m(bd09_to_gcj02(*bd), gcj) if bd is not None else None
        return canonical_bd, gcj, "GCJ-02", delta
    if bd is not None:
        return bd, bd09_to_gcj02(*bd), "BD-09", None
    raise ValueError("打卡点没有可用坐标，不能生成方案")


def coordinate_report(points):
    """只返回坐标来源及双坐标差异统计，不泄露原始经纬度。"""
    sources, deltas = [], []
    for point in points:
        _, _, source, delta = checkpoint_coordinates(point)
        sources.append(source)
        if delta is not None:
            deltas.append(delta)
    return {"native_gcj": sources.count("GCJ-02"), "converted_bd": sources.count("BD-09"),
            "conflicts": sum(d > CONFLICT_METERS for d in deltas),
            "max_delta_m": round(max(deltas, default=0.0), 2)}
