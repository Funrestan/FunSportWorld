"""提交数据快照：把一次提交真正上传的完整 payload 落盘。

统一交给 funsport.payload_archive 存到 .funsport/payloads/ 下。
"""
from .. import payload_archive


def build_summary(track, result, extra=None):
    total_time = track.get("totalTime", 0) or 0
    total_dis = track.get("totalDistance", 0.0) or 0.0
    total_steps = track.get("totalSteps", 0) or 0
    pace = (total_time / (total_dis / 1000.0)) if total_dis > 0 else 0
    summary = {
        "totalDistance": round(total_dis, 3),
        "totalTime": total_time,
        "totalSteps": total_steps,
        "avgStepFreq": int(result.get("avg_step_freq", 0) or 0),
        "paceSecPerKm": round(pace, 1),
        "avgPower": int(result.get("avg_power", 0) or 0),
        "calorie": int(result.get("calorie", 0) or 0),
        "windowCount": len(track.get("speedPerTenSec") or []),
        "sampleCount": len(track.get("locations") or []),
        "checkpointCount": len(result.get("points") or []),
        "sharpCount": 0,
        "slowCount": 0,
        "slowTotalTime": 0.0,
    }
    if extra:
        summary.update(extra)
    return summary


def dump(rrid, submit_body, obs_run_data, summary):
    payload = {
        "summary": summary,
        "submitBody": submit_body,
        "obsRunData": obs_run_data,
    }
    try:
        return payload_archive.save(rrid, payload)
    except Exception:
        return None
