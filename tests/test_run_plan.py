"""方案冻结、单次提交、时间窗口和点位序列化的回归测试。"""
import base64
import gzip
import json
import time
from contextlib import ExitStack
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from tests.support import IsolatedCase
from tests.plan_fixture import fake_client, sample_plan, sample_ring
from funsport.api import flow
from funsport.run_plan import RunPlan, format_plan
from funsport.track import wire


class PlanTests(IsolatedCase):
    """不发请求，直接核对预览与传入提交函数的数据一致性。"""

    def submission_mocks(self, stack):
        """模拟提交、OBS 与详情边界，保留中间序列化逻辑。"""
        submit = stack.enter_context(patch.object(flow.api_submit, "submit_record", return_value={"rrid": 123, "uuid": "fixture"}))
        upload = stack.enter_context(patch.object(flow.api_obs, "upload_both_keys", return_value=2))
        stack.enter_context(patch.object(flow.api_records, "fetch_one_record", return_value={"complete": False}))
        stack.enter_context(patch.object(flow.time, "sleep"))
        stack.enter_context(patch.object(flow.log, "disabled", True))
        return submit, upload

    def test_exact_track_and_wrapper_submitted(self):
        """提交轨迹等于快照，HTTP 和 OBS 的打卡包装内容完全一致。"""
        plan = sample_plan()
        snapshot = plan.data()
        with ExitStack() as stack:
            submit, upload = self.submission_mocks(stack)
            stack.enter_context(patch.object(flow.generator, "build", side_effect=AssertionError("提交不能重新生成")))
            result = flow.submit_run_plan(fake_client(), plan)
        self.assertEqual(submit.call_args.args[1], snapshot["track"])
        self.assertEqual(submit.call_args.kwargs["five_point_json"], snapshot["five_point_json"])
        obs = json.loads(upload.call_args.args[2])
        point_wrapper = json.loads(gzip.decompress(base64.b64decode(obs["fixed_point_json"])))
        self.assertEqual(point_wrapper, json.loads(snapshot["five_point_json"]))
        self.assertEqual(result["plan_id"], plan.plan_id)

    def test_preview_copy_cannot_mutate_submission(self):
        """修改读出的字典不会改变内部快照或方案 ID。"""
        plan = sample_plan()
        before = plan.plan_id
        data = plan.data()
        data["track"]["locations"][0]["gLat"] = 99
        self.assertNotEqual(plan.data()["track"]["locations"][0]["gLat"], 99)
        self.assertEqual(plan.plan_id, before)

    def test_generation_never_submits(self):
        """准备阶段只读取和生成，即使处于有效时间外也可以查看。"""
        source = sample_plan(outside=True).data()
        policy = SimpleNamespace(timestamp=1, policy=1, min_distance=1000, valid_time=source["valid_time"])
        with patch.object(flow.api_policy, "fetch_policy", return_value=policy), \
                patch.object(flow.api_points, "fetch_points", return_value=(source["points"], {"runAreaId": 8})) as points, \
                patch.object(flow.api_loop, "get_campus_loop", return_value=(sample_ring(), {})), \
                patch.object(flow.generator, "build", return_value=source["track"]) as build, \
                patch.object(flow.api_submit, "submit_record") as submit, \
                patch.object(flow.api_obs, "upload_both_keys") as upload, \
                patch.object(flow.log, "disabled", True):
            plan = flow.prepare_run_plan(fake_client(), dist=1.6, pace=400, start_ms=source["track"]["startTime"])
        self.assertFalse(plan.data()["window_ok"])
        self.assertEqual(json.loads(plan.data()["five_point_json"])["runAreaId"], 8)
        self.assertFalse(points.call_args.kwargs["allow_stale"])
        self.assertEqual(build.call_args.args[4], sample_ring())
        self.assertTrue(build.call_args.kwargs["ordered_path"])
        submit.assert_not_called()
        upload.assert_not_called()

    def test_outside_requires_explicit_override(self):
        """窗口外默认不发请求，明确开启后可进入测试提交。"""
        plan = sample_plan(outside=True)
        with ExitStack() as stack:
            submit, _ = self.submission_mocks(stack)
            with self.assertRaises(ValueError):
                flow.submit_run_plan(fake_client(), plan)
            submit.assert_not_called()
            self.assertFalse(plan.attempted)
            flow.submit_run_plan(fake_client(), plan, True)
            submit.assert_called_once()

    def test_unknown_network_result_cannot_retry_same_plan(self):
        """请求超时后的方案也锁定，防止实际已提交但再次写入。"""
        plan = sample_plan()
        with patch.object(flow.api_submit, "submit_record", side_effect=TimeoutError("simulated")) as submit:
            with self.assertRaises(TimeoutError):
                flow.submit_run_plan(fake_client(), plan)
            with self.assertRaises(ValueError):
                flow.submit_run_plan(fake_client(), plan)
            submit.assert_called_once()

    def test_local_completion_failure_does_not_claim_or_submit_plan(self):
        for unsupported in (False, True):
            data = sample_plan().data()
            if unsupported:
                data["policy"] = 2
            else:
                data["completion"] = {"complete": True, "unCompleteReason": 0}
            plan = RunPlan.create(fake_client(), data)
            with self.subTest(unsupported=unsupported), patch.object(flow.api_submit, "submit_record") as submit:
                with self.assertRaises(ValueError):
                    flow.submit_run_plan(fake_client(), plan)
                self.assertFalse(plan.attempted)
                submit.assert_not_called()

    def test_owner_expiry_and_future_checks(self):
        """不接受别的账号、过期方案，也不把时间外开关当成未来记录开关。"""
        plan = sample_plan()
        other = fake_client()
        other.session_data["unid"] = "other-school"
        with self.assertRaises(ValueError):
            plan.validate(other)
        expired = RunPlan(plan.json_text, plan.owner, time.time() - 601)
        with self.assertRaises(ValueError):
            expired.validate(fake_client())
        data = plan.data()
        data["track"]["startTime"] = int(time.time() * 1000)
        future = RunPlan.create(fake_client(), data)
        with patch.object(flow.api_submit, "submit_record") as submit:
            with self.assertRaises(ValueError):
                flow.submit_run_plan(fake_client(), future, True)
            submit.assert_not_called()

    def test_full_interval_and_overnight_windows(self):
        """跨午夜必须包含整个区间；支持合法的跨午夜开放时段。"""
        start = int(datetime(2026, 9, 17, 23, 55).timestamp() * 1000)
        self.assertFalse(flow._check_time_window(start, 900, [{"start": "06:00", "end": "23:59"}])[0])
        self.assertTrue(flow._check_time_window(start, 900, [{"start": "22:00", "end": "01:00"}])[0])

    def test_final_generated_duration_controls_window(self):
        """原参数在窗口内但实际轨迹超时，应按最终轨迹显示窗口外。"""
        source = sample_plan().data()
        start = int(datetime(2026, 9, 17, 6, 0).timestamp() * 1000)
        source["track"]["startTime"] = start
        source["track"]["totalTime"] = 800
        policy = SimpleNamespace(timestamp=1, policy=1, min_distance=1000,
                                 valid_time=[{"start": "06:00", "end": "06:10"}])
        with patch.object(flow.api_policy, "fetch_policy", return_value=policy), \
                patch.object(flow.api_points, "fetch_points", return_value=(source["points"], {})), \
                patch.object(flow.api_loop, "get_campus_loop", return_value=(sample_ring(), {})), \
                patch.object(flow.generator, "build", return_value=source["track"]), \
                patch.object(flow.log, "disabled", True):
            plan = flow.prepare_run_plan(fake_client(), dist=1, pace=400, start_ms=start)
        self.assertFalse(plan.data()["window_ok"])

    def test_wire_preserves_metadata_without_faking_pass(self):
        """保留服务器点位信息，不把所有点统一标记为通过。"""
        raw = [{"id": 91, "position": 2, "state": 3, "isPass": False, "lat": 30.6, "lon": 104.1}]
        wrapper = json.loads(wire.five_point_wrapper(raw, 1000, {"runAreaId": 77, "geoFencesJson": "[]", "freedomShowFence": True}))
        point = json.loads(wrapper["fivePointJson"])[0]
        self.assertEqual((point["id"], point["position"], point["state"], point["isPass"]), (91, 2, 3, False))
        self.assertGreater(point["glat"], 1)
        self.assertEqual(wrapper["runAreaId"], 77)
        self.assertTrue(wrapper["freedomShowFence"])
        self.assertNotIn("官方已通过", format_plan(sample_plan()))

    def test_invalid_coordinates_are_rejected(self):
        """只有占位、布尔或非有限坐标时不能悄悄生成在零点的方案。"""
        for point in ({}, {"lat": 0, "lon": 0}, {"lat": float("nan"), "lon": 104}, {"lat": True, "lon": 104}):
            with self.subTest(point=point), self.assertRaises(ValueError):
                wire.five_point_payload([point], 1000)

    def test_partial_gcj_sentinel_falls_back(self):
        """单个高德坐标为默认值时，预览也像参考 App 一样回退百度坐标。"""
        point = wire.five_point_payload([{"lat": 30.6, "lon": 104.1, "glat": -1, "glon": 104.1}], 1000)[0]
        self.assertGreater(point["glat"], 1)
