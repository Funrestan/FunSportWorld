"""高德静态底图与本地轨迹叠加；底图请求只发送中心和缩放，不发送轨迹。"""
import io
import math

import requests
from PIL import Image

from .config import get_amap_key
from .track.wire import bd09_to_gcj02
from .track.geom import round_to

STATIC_MAP_URL = "https://restapi.amap.com/v3/staticmap"


def project(lat, lon, zoom):
    """将 GCJ-02 经纬度映射为对应缩放级别的墨卡托像素。"""
    lat = max(-85.05112878, min(85.05112878, lat))
    size = 256 * 2 ** zoom
    sin_lat = math.sin(math.radians(lat))
    return (lon + 180) / 360 * size, (0.5 - math.log((1 + sin_lat) / (1 - sin_lat)) / (4 * math.pi)) * size


def unproject(x, y, zoom):
    """把地图像素中心转换回 GCJ-02 经纬度。"""
    size = 256 * 2 ** zoom
    return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / size)))), x / size * 360 - 180


def fit_view(coordinates, width, height):
    """选择能容纳轨迹和点位的中心与缩放，留出标记边距。"""
    if not coordinates:
        return None
    for zoom in range(17, 0, -1):
        pixels = [project(lat, lon, zoom) for lat, lon in coordinates]
        xs, ys = zip(*pixels)
        if max(xs) - min(xs) <= max(80, width - 80) and max(ys) - min(ys) <= max(80, height - 80):
            break
    center = unproject((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, zoom)
    return center, zoom


def screen_position(coordinate, center, zoom, width, height):
    """计算与静态底图相同中心、缩放下的画布坐标。"""
    x, y = project(*coordinate, zoom)
    cx, cy = project(*center, zoom)
    return width / 2 + x - cx, height / 2 + y - cy


def track_coordinates(track):
    """保留采样索引并采用上传的七位精度；None仅标无效样本，不决定连线。"""
    return [None if point.get("type") == -1 else
            tuple(round_to(value, 7) for value in bd09_to_gcj02(point["gLat"], point["gLng"]))
            for point in track.get("locations", [])]


def history_geometry(track):
    """按7.3.70可读历史地图规则抽样、着色及取起终点，不强制闭合。

    无效点被跳过而非切断；相同类型且方向变化不超过10度时隔点保留。
    该规则来自Java地图控制器，native桥接的真机效果仍需核对。
    """
    segments, previous, retained, skipped = [], None, None, 0
    start = end = None
    for point, coordinate in zip(track.get("locations", []), track_coordinates(track)):
        if coordinate is None:
            continue
        point_type = point.get("type", 0)
        heading = round_to(point.get("bdD", 0.0), 2)
        if point_type == 5:
            start = coordinate
        elif point_type == 6:
            end = coordinate
        if retained is None:
            retained = coordinate
        if previous is not None:
            if skipped >= 1 or point_type != previous[0] or abs(previous[1] - heading) > 10:
                color = "#b5b5b5" if point_type in (3, 4) else "#ff0000" if point_type in (7, 10) else "#00c18b"
                segments.append((retained, coordinate, color))
                retained, skipped = coordinate, 0
            else:
                skipped += 1
        previous = (point_type, heading)
    return {"segments": segments, "start": start, "end": end}


def fetch_background(center, zoom, width, height):
    """请求受限大小的高德底图，不记录 Key、完整 URL 或响应正文。"""
    key = get_amap_key()
    if not key:
        raise ValueError("未配置高德 Web 服务 Key；轨迹仍可离线预览")
    width, height = min(1024, max(64, int(width))), min(1024, max(64, int(height)))
    params = {"key": key, "location": "{:.7f},{:.7f}".format(center[1], center[0]),
              "zoom": max(1, min(17, int(zoom))), "size": "{}*{}".format(width, height), "scale": 1}
    try:
        with requests.get(STATIC_MAP_URL, params=params, stream=True, timeout=(5, 20)) as response:
            if response.status_code != 200:
                raise ValueError("底图服务返回 HTTP {}".format(response.status_code))
            chunks, length = [], 0
            for chunk in response.iter_content(65536):
                length += len(chunk)
                if length > 4 * 1024 * 1024:
                    raise ValueError("底图响应超过 4 MiB")
                chunks.append(chunk)
            raw = b"".join(chunks)
    except requests.RequestException:
        raise ValueError("底图网络请求失败，轨迹仍可预览；请检查网络后重试") from None
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.size != (width, height):
                raise ValueError("底图尺寸不符，已拒绝叠加以免坐标错位")
            return image.convert("RGB")
    except (OSError, Image.DecompressionBombError):
        raise ValueError("底图不是有效图片，请检查高德 Key 的 Web 服务权限和额度") from None
