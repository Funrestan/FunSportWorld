"""Replay the recovered checkpoint rules on generated locations."""
import copy
import json
import math
from collections import Counter

from ..coordinates import bd09_to_gcj02, checkpoint_coordinates, coordinate_pair, distance_m
from .pace import location_pace

PASS_RADIUS_M = 25.0


def _decoded(value):
    return json.loads(value) if isinstance(value, str) and value.strip() else value


def _fence_polygons(value):
    value = _decoded(value)
    if value is None or value == "":
        return []
    if isinstance(value, dict):
        value = value.get("geoFences", value.get("points"))
    if not isinstance(value, list):
        raise ValueError("Invalid checkpoint fence data")
    if value and isinstance(value[0], dict) and ("lat" in value[0] or "glat" in value[0]):
        value = [value]
    polygons = []
    for fence in value:
        vertices = fence.get("points") if isinstance(fence, dict) else fence
        if not isinstance(vertices, list) or len(vertices) < 3:
            raise ValueError("A checkpoint fence needs at least three vertices")
        polygon = []
        for vertex in vertices:
            if not isinstance(vertex, dict):
                raise ValueError("Invalid checkpoint fence vertex")
            point = {"lat": vertex.get("lat"), "lon": vertex.get("lng", vertex.get("lon")),
                     "glat": vertex.get("glat"), "glon": vertex.get("glng", vertex.get("glon"))}
            polygon.append(checkpoint_coordinates(point)[1])
        polygons.append(polygon)
    return polygons


def resolve_fences(metadata=None, geo_fence=None, run_area_models=None):
    """Prefer the selected policy fences; point responses may omit them."""
    metadata = metadata or {}
    geo_fence = _decoded(geo_fence)
    if geo_fence is not None:
        fences = geo_fence.get("geoFences", []) if isinstance(geo_fence, dict) else geo_fence
        if fences is None:
            fences = []
        if not isinstance(fences, list):
            raise ValueError("Invalid policy geoFence")
        area_id = metadata.get("runAreaId", -1)
        if area_id not in (None, -1) and run_area_models:
            area = next((item for item in run_area_models if item.get("id") == area_id), None)
            if area is None or not isinstance(area.get("fenceIds"), list):
                raise ValueError("Selected running area has no known fence mapping")
            fence_ids = area["fenceIds"]
            fences = [fence for fence in fences if fence.get("id") in fence_ids]
            if len({fence.get("id") for fence in fences}) != len(set(fence_ids)):
                raise ValueError("Selected running area references a missing fence")
        return _fence_polygons(fences), "policy"
    return _fence_polygons(metadata.get("geoFencesJson", [])), "point_metadata"


def _in_polygon(point, polygon):
    """Match GaoDeUtils.ptInPolygon's half-open longitude intersections."""
    y, x = point
    intersections = 0
    for index, (y1, x1) in enumerate(polygon):
        y2, x2 = polygon[(index + 1) % len(polygon)]
        if x1 != x2 and min(x1, x2) <= x < max(x1, x2):
            if (x - x1) * (y2 - y1) / (x2 - x1) + y1 > y:
                intersections += 1
    return intersections % 2 == 1


def evaluate_checkpoints(track, points, policy, metadata=None, geo_fence=None, run_area_models=None):
    """Return copies plus an audit of simulated transitions, not server verdicts.

    The native GPS filter is unavailable. Existing invalid sample types remain
    invalid; other generated samples are inputs to this explicitly local model.
    """
    result_track, result_points = copy.deepcopy(track), copy.deepcopy(points)
    supported = type(policy) is int and policy in (0, 1)
    mode = ("sequence" if type(policy) is int and policy == 1
            else "random" if type(policy) is int and policy == 0
            else "unsupported")
    report = {
        "version": 1, "mode": mode,
        "supported": supported,
        "native_validity_verified": False, "server_verified": False,
        "assumptions": ["native_filter_not_reproduced", "generated_sample_types_used_for_validity"],
        "radius_m": PASS_RADIUS_M, "events": [], "samples": [],
        "source_passed_positions": [p.get("position") for p in points if p.get("isPass") is True],
    }
    if not report["supported"]:
        report.update({"all_passed": None, "passed_count": sum(p.get("isPass") is True for p in points)})
        return result_track, result_points, report
    positions = [p.get("position") for p in result_points]
    if not 1 <= len(positions) <= 5:
        raise ValueError("Checkpoint evaluation requires 1 to 5 points")
    if policy == 1 and (any(type(p) is not int for p in positions)
                        or positions != list(range(len(positions)))):
        raise ValueError("Sequential checkpoint evaluation requires ordered positions 0..N-1")
    # Generated plans are new runs, so cached states cannot count as arrivals.
    for point in result_points:
        point["isPass"] = False
    report["state_origin"] = "new_run"
    polygons, fence_source = resolve_fences(metadata, geo_fence, run_area_models)
    report["fences"] = {"source": fence_source, "count": len(polygons)}
    if not polygons:
        report["assumptions"].append("no_configured_fences")
    targets = [checkpoint_coordinates(p)[1] for p in result_points]
    pending = list(range(len(result_points)))
    previous = None
    last_elapsed = None
    skipped = Counter()
    for index, sample in enumerate(result_track["locations"]):
        elapsed = sample.get("totalTime")
        entry = {"sample_index": index, "elapsed_seconds": elapsed,
                 "target_position": pending[0] if policy == 1 and pending else None,
                 "pending_positions": list(pending),
                 "original_type": sample.get("type")}
        report["samples"].append(entry)
        reason = None
        bd = coordinate_pair(sample.get("gLat"), sample.get("gLng"))
        if not isinstance(elapsed, (int, float)) or isinstance(elapsed, bool) or not math.isfinite(elapsed):
            reason = "invalid_sample_time"
        elif elapsed < 0 or (last_elapsed is not None and elapsed <= last_elapsed):
            raise ValueError("Checkpoint locations must have strictly increasing times")
        else:
            last_elapsed = elapsed
        if reason is None:
            if bd is None:
                reason = "invalid_coordinates"
            elif sample.get("type") == -1:
                reason = "invalid_location"
            else:
                pace = location_pace(previous, sample)
                previous = sample
                entry["pace_min_per_km"] = round(pace, 6)
                if sample.get("type") in (5, 6):
                    reason = "start_or_end_marker"
                elif sample.get("isPaused") is True or sample.get("paused") is True:
                    reason = "paused"
                elif sample.get("type") == 3:
                    reason = "paused_or_outside"
                elif sample.get("type") == 7:
                    reason = "excluded_pace_type"
                elif sample.get("type") not in (0, 1, 2, 8, 9):
                    reason = "unsupported_sample_type"
                elif not pending:
                    reason = "all_targets_passed"
                else:
                    current = tuple(round(value, 7) for value in bd09_to_gcj02(*bd))
                    recovery = sample.get("type") in (8, 9)
                    if not recovery and polygons and not any(_in_polygon(current, p) for p in polygons):
                        reason = "outside_fence"
                    elif pace < 2.0:
                        reason = "pace_below_two"
                    else:
                        # The official random plugin scans unpassed points and
                        # stops after the first hit.  A sample therefore can
                        # advance at most one point even when targets overlap.
                        candidate_distances = [
                            (target_index, distance_m(current, targets[target_index]))
                            for target_index in pending
                        ]
                        if policy == 1:
                            target_index, distance = candidate_distances[0]
                            matching = distance <= PASS_RADIUS_M
                        else:
                            target_index, distance = next(
                                ((target_index, distance)
                                 for target_index, distance in candidate_distances
                                 if distance <= PASS_RADIUS_M),
                                (None, min(distance for _, distance in candidate_distances)),
                            )
                            matching = target_index is not None
                        entry["distance_m"] = round(distance, 6)
                        if policy == 0:
                            entry["candidate_distances_m"] = {
                                str(index): round(value, 6)
                                for index, value in candidate_distances
                            }
                        if matching:
                            result_points[target_index]["isPass"] = True
                            if not recovery:
                                # RunRandomPImpl returns type=2 for the fixed
                                # assessment point and type=1 for ordinary
                                # random points; sequence mode uses type=2 for
                                # each reached checkpoint.
                                sample["type"] = (
                                    2 if policy == 1 or result_points[target_index].get("isFixed") == 1
                                    else 1)
                            event = {**entry, "point_id": result_points[target_index].get("id"),
                                 "position": target_index, "stored_type": sample["type"],
                                 "point_position": result_points[target_index].get("position"),
                                 "isFixed": result_points[target_index].get("isFixed", 0),
                                 "isPass": True}
                            report["events"].append(event)
                            pending.remove(target_index)
                            reason = "passed"
                        else:
                            reason = "outside_target_radius"
        entry["decision"] = reason
        if reason != "passed":
            skipped[reason] += 1
    passed_indices = [index for index, point in enumerate(result_points)
                      if point.get("isPass") is True]
    fixed_indices = [index for index in passed_indices
                     if result_points[index].get("isFixed") == 1]
    ordinary_indices = [index for index in passed_indices
                        if result_points[index].get("isFixed") != 1]
    report.update({
        "all_passed": not pending,
        "passed_count": len(passed_indices),
        "fixed_passed_count": len(fixed_indices),
        "ordinary_passed_count": len(ordinary_indices),
        "passed_positions": passed_indices,
        "pending_positions": pending,
        "fixed_positions": fixed_indices,
        "ordinary_positions": ordinary_indices,
        "skipped_counts": dict(skipped),
    })
    return result_track, result_points, report
