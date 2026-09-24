"""Location pace fields inferred from the recovered Android implementation."""
import math
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from ..coordinates import bd09_to_gcj02, coordinate_pair, distance_m
from .geom import round_to


def pace_from_distance(distance, elapsed_ms):
    """Return minutes/km after Android's upward centimetre rounding."""
    if not math.isfinite(distance) or not math.isfinite(elapsed_ms):
        return 0.0
    if distance <= 0 or elapsed_ms <= 0:
        return 0.0
    rounded_distance = math.ceil(distance * 100) / 100
    pace = elapsed_ms / (rounded_distance * 60)
    return pace if 0 < pace <= 10000 else 0.0


def _gain_time_ms(point):
    value = point.get("gainTime")
    if value:
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").timestamp() * 1000
        except (TypeError, ValueError, OverflowError, OSError):
            pass
    return _finite_number(point.get("gainTimeMs"))


def _finite_number(value):
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _wire_coordinate(point):
    coordinate = coordinate_pair(point.get("gLat"), point.get("gLng"))
    if coordinate is None:
        return None
    return tuple(round_to(value, 7) for value in bd09_to_gcj02(*coordinate))


def location_pace(previous, current):
    """Compute raw pace from two internal BD samples, using wire GCJ geometry."""
    if previous is None:
        return 0.0
    start, end = _wire_coordinate(previous), _wire_coordinate(current)
    if start is None or end is None:
        return 0.0
    previous_ms, current_ms = _gain_time_ms(previous), _gain_time_ms(current)
    elapsed_ms = ((current_ms - previous_ms)
                  if previous_ms is not None and current_ms is not None else 0)
    if elapsed_ms == 0:
        previous_seconds = _finite_number(previous.get("totalTime"))
        current_seconds = _finite_number(current.get("totalTime"))
        if previous_seconds is None or current_seconds is None:
            return 0.0
        elapsed_ms = (current_seconds - previous_seconds) * 1000
    return pace_from_distance(distance_m(start, end), elapsed_ms)


def _stored_value(value):
    # Utils.convertDouble adds 0.0001 before HALF_UP rounding to two decimals.
    return float(Decimal(str(value + 0.0001)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def apply_location_paces(locations):
    """Set final pace fields without changing event types or native GPS metadata.

    Only existing type=-1 samples are known invalid here. This does not replay
    the unavailable native validity function or certify generated locations.
    """
    previous = None
    for point in locations:
        if point.get("type") == -1:
            point["speed"] = point["avgSpeed"] = 0.0
            continue
        pace = 0.0 if point.get("type") == 5 else location_pace(previous, point)
        point["speed"] = _stored_value(pace)
        point["avgSpeed"] = _stored_value(50 / (pace * 3)) if pace > 0 else 0.0
        previous = point
