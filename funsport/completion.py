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
    """Evaluate RunSequencePImpl's finish decision on the final local snapshot.

    RunRandomPImpl.getUnCompleteReason supplies the inherited wire reason codes.
    Native GPS validation, telemetry and backend rules cannot be inferred here.
    """
    assumptions = [
        "Legacy client completion only; server pace, cadence and other rules remain authoritative.",
        "Checkpoint isPass values come from the local replay; native GPS validation is not reproduced.",
        "The recovered Constant.MinRunTime default is 30 seconds.",
    ]
    result = {
        "supported": type(policy) is int and policy == 1,
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
    selected_min_time = _number(run_rules.get("minRunTime", 0), "minRunTime")
    if "minRunTime" not in run_rules:
        assumptions.append("Missing minRunTime uses the legacy Presenter default of 0 seconds.")

    checkpoints = points if isinstance(points, list) else []
    valid_sequence = 1 <= len(checkpoints) <= 5 and all(
        isinstance(point, dict)
        and type(point.get("position")) is int
        and point["position"] == index
        and type(point.get("isPass")) is bool
        for index, point in enumerate(checkpoints))
    sequence_complete = valid_sequence and all(
        point["isPass"] for point in checkpoints)
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
            "passed": sum(isinstance(point, dict) and point.get("isPass") is True
                          for point in checkpoints),
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
    # Keep the official finish-dialog priority when several conditions fail.
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
