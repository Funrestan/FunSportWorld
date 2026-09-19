"""不联网的完整方案样本，供提交一致性和 GUI 验收共用。"""
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from funsport.api.flow import _check_time_window
from funsport.run_plan import RunPlan, checkpoint_distances
from funsport.track import generator, wire


def sample_ring():
    """返回人工闭合折线，仅用作测试替身，不是实时高德返回数据。"""
    return [(30.6, 104.1), (30.602, 104.104), (30.605, 104.103), (30.604, 104.098), (30.6, 104.1)]


def fake_client():
    """返回没有网络能力的示例账号客户端。"""
    return SimpleNamespace(uid=lambda: 1, session_data={"weight": 68, "unid": "1"},
                           identity={"device_id": "test-device", "anchor_lat": 30.6, "anchor_lon": 104.1})


def sample_plan(outside=False):
    """沿人工折线创建完整轨迹，仅在内存中组合方案快照。"""
    start = int((datetime.now() - timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0).timestamp() * 1000)
    raw = [{"id": 11 + index, "position": index, "pointName": "测试点 " + chr(65 + index), "lat": lat, "lon": lon}
           for index, (lat, lon) in enumerate(sample_ring()[:-1])]
    points = wire.five_point_payload(raw, start)
    with patch.object(generator.log, "disabled", True):
        track = generator.build(2000, 800, 42, start, sample_ring(), ordered_path=True, cadence_target=160)
    windows = [{"start": "00:00:00", "end": "00:01:00"}] if outside else []
    valid, reason = _check_time_window(start, track["totalTime"], windows)
    data = {"track": track, "points": points, "five_point_json": wire.five_point_wrapper(points, start, {"runAreaId": 7}),
            "policy_ts": start, "policy": 1, "min_distance": 1000, "valid_time": windows,
            "window_ok": valid, "window_reason": reason, "weight": 68, "face_check": 1,
            "seed": 42, "use_map": True, "allow_outside_window": False,
            "route": {"provider": "synthetic_test_fixture", "vertex_count": 5},
            "checkpoint_distances": checkpoint_distances(track, points)}
    return RunPlan.create(fake_client(), data)
