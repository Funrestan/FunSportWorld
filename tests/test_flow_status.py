"""完全模拟网络，检查提交结果的三种状态不会混在一起。"""
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tests.support import IsolatedCase
from tests.plan_fixture import sample_ring
from funsport.api import flow, records


class FlowTests(IsolatedCase):
    """只验证编排返回值，不生成真实运动或发送网络请求。"""

    def run_fake_flow(self, detail, obs_count=2):
        """替换每个外部边界，保留实际编排和诊断代码。"""
        client = Mock(session_data={"weight": 68, "unid": "1"}, identity={"device_id": "test"})
        client.uid.return_value = 1
        track = {"startTime": 1000, "totalDistance": 1000, "totalTime": 400, "totalSteps": 1066,
                 "locations": [{"gLat": 30.6, "gLng": 104.1, "type": 3}]}
        policy = SimpleNamespace(min_distance=1000, timestamp=1000, policy=1, valid_time=[])
        with ExitStack() as stack:
            stack.enter_context(patch.object(flow.api_policy, "fetch_policy", return_value=policy))
            stack.enter_context(patch.object(flow.api_points, "fetch_points", return_value=([{"lat": 30.6, "lon": 104.1}], {})))
            stack.enter_context(patch.object(flow.generator, "build", return_value=track))
            stack.enter_context(patch.object(flow.api_loop, "get_campus_loop", return_value=(sample_ring(), {})))
            stack.enter_context(patch.object(flow.api_submit, "submit_record", return_value={"rrid": 123, "uuid": "example"}))
            stack.enter_context(patch.object(flow.wire, "build_obs_object", return_value={}))
            stack.enter_context(patch.object(flow.api_obs, "upload_both_keys", return_value=obs_count))
            stack.enter_context(patch.object(flow.time, "sleep"))
            stack.enter_context(patch.object(flow, "_resolve_start_ms", return_value=1000))
            fetch = stack.enter_context(patch.object(flow.api_records, "fetch_one_record"))
            if isinstance(detail, Exception):
                fetch.side_effect = detail
            else:
                fetch.return_value = detail
            stack.enter_context(patch.object(flow.log, "handlers", []))
            return flow.run_full_flow(client, dist=1, pace=400)

    def test_returned_record_is_not_passed_record(self):
        """记录能读到但 complete=false 时，不能被报告为跑步达标。"""
        result = self.run_fake_flow({"complete": False, "totalDis": 1000, "totalTime": 400})
        self.assertTrue(result["detail_ok"])
        self.assertFalse(result["checkpoint_report"]["complete"])
        self.assertEqual(result["checkpoint_report"]["status"], "missing")

    def test_partial_obs_remains_partial(self):
        """即使详情能读取，也保留 OBS 部分上传的状态。"""
        result = self.run_fake_flow({"complete": True, "fivePointJson": []}, obs_count=1)
        self.assertEqual(result["obs_ok"], 1)
        self.assertEqual(result["checkpoint_report"]["status"], "empty")

    def test_detail_failure_keeps_submission_id(self):
        """详情失败仍返回已提交的记录 ID，避免引导用户重复提交。"""
        result = self.run_fake_flow(RuntimeError("offline"))
        self.assertEqual(result["rrid"], 123)
        self.assertFalse(result["detail_ok"])
        self.assertIsNone(result["checkpoint_report"])

    def test_detail_rejects_list(self):
        """非对象详情不能算读取验证成功。"""
        client = Mock()
        with patch.object(records, "parse_data_field", return_value=[{}]):
            with self.assertRaises(RuntimeError):
                records.fetch_one_record(client, 123)

    def test_records_preserve_unknown_complete(self):
        """服务端没给 complete 时，列表保留未知而不是强行判否。"""
        client = Mock()
        with patch.object(records, "parse_data_field", return_value=[{"rrid": 123}]):
            result = records.fetch_records(client)
        self.assertIsNone(result[0]["complete"])
