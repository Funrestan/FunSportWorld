"""Infer legacy client completion without claiming server-side validation."""
import math


MIN_RECORD_SECONDS = 30


def _number(value, field):
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a nonnegative number")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a nonnegative number") from exc
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{field} must be a nonnegative number")
    return result


def evaluate_completion(track, points, policy, min_distance, run_rules=None):
    """Evaluate the recovered client-side finish decision on a frozen snapshot.

    ``policy=1`` is the sequential presenter.  ``policy=0`` is the random
    presenter: any two ordinary points plus every fixed point are required.
    Native GPS validation, telemetry and backend rules remain authoritative.
    """
    assumptions = [
        "Legacy client completion only; server pace, cadence and other rules remain authoritative.",
        "Checkpoint isPass values come from the local replay; native GPS validation is not reproduced.",
        "The recovered Constant.MinRunTime default is 30 seconds.",
    ]
    result = {
        "supported": type(policy) is int and policy in (0, 1),
        "policy": policy,
        "complete": None,
        "unCompleteReason": None,
        "rules": {},
        "assumptions": assumptions,
    }
    if not result["supported"]:
        assumptions.append("Completion logic for this policy has not been implemented.")
        return result

    run_rules = run_rules or {}
    total_time = _number(track["totalTime"], "totalTime")
    total_distance = _number(track["totalDistance"], "totalDistance")
    target_distance = _number(min_distance, "min_distance")
    default_min_time = MIN_RECORD_SECONDS if policy == 0 else 0
    selected_min_time = _number(run_rules.get("minRunTime", default_min_time), "minRunTime")
    if "minRunTime" not in run_rules:
        assumptions.append("Missing minRunTime uses the recovered Presenter default of {} seconds.".format(
            default_min_time))

    checkpoints = points if isinstance(points, list) else []
    valid_points = 1 <= len(checkpoints) <= 5 and all(
        isinstance(point, dict) and type(point.get("isPass")) is bool
        for point in checkpoints)
    valid_sequence = valid_points and all(
        type(point.get("position")) is int
        and point["position"] == index
        for index, point in enumerate(checkpoints))
    sequence_complete = valid_sequence and all(point["isPass"] for point in checkpoints)
    fixed_points = [point for point in checkpoints if point.get("isFixed") == 1]
    ordinary_points = [point for point in checkpoints if point.get("isFixed") != 1]
    # The recovered presenter sets mAssesPass as soon as one isFixed point
    # passes; it does not require every fixed point when a response contains
    # more than one assessment marker.
    fixed_passed = valid_points and any(point["isPass"] for point in fixed_points)
    ordinary_passed = sum(point["isPass"] for point in ordinary_points) if valid_points else 0
    enough_time = total_time > MIN_RECORD_SECONDS
    enough_selected_time = total_time >= selected_min_time
    enough_distance = total_distance >= target_distance
    result["rules"] = {
        "minimumRecordTime": {
            "complete": enough_time, "actual": total_time,
            "threshold": MIN_RECORD_SECONDS, "comparison": ">",
        },
        "sequentialCheckpoints": {
            "complete": sequence_complete, "count": len(checkpoints),
            "validSequence": valid_sequence,
            "passed": sum(point.get("isPass") is True for point in checkpoints
                           if isinstance(point, dict)),
        },
        "minimumRunTime": {
            "complete": enough_selected_time, "actual": total_time,
            "threshold": selected_min_time, "comparison": ">=",
        },
        "minimumDistance": {
            "complete": enough_distance, "actual": total_distance,
            "threshold": target_distance, "comparison": ">=",
        },
    }
    if policy == 0:
        # RunRandomPImpl does not use position ordering.  Its presenter keeps
        # separate flags for the fixed assessment point and two ordinary hits.
        random_complete = fixed_passed and ordinary_passed >= 2
        result["rules"]["randomCheckpoints"] = {
            "complete": random_complete,
            "count": len(checkpoints),
            "validPoints": valid_points,
            "fixedCount": len(fixed_points),
            "fixedPassed": fixed_passed,
            "ordinaryCount": len(ordinary_points),
            "ordinaryPassed": ordinary_passed,
            "ordinaryRequired": 2,
        }
        # Keep RunRandomPImpl.getTipMsg's failure priority and reason codes.
        if not enough_time or not fixed_passed:
            reason = 2
        elif ordinary_passed < 2:
            reason = 3
        elif not enough_selected_time:
            reason = 10
        elif not enough_distance:
            reason = 1
        else:
            reason = 0
    else:
        # Keep the official sequential finish-dialog priority when several
        # conditions fail.
        if not enough_time:
            reason = 2
        elif not sequence_complete:
            reason = 9
        elif not enough_selected_time:
            reason = 10
        elif not enough_distance:
            reason = 1
        else:
            reason = 0
    result.update(complete=reason == 0, unCompleteReason=reason)
    return result
