"""顺序点位兼容修复：虚构点位、隔离配置和禁止真实HTTP。"""
import base64
import copy
import gzip
import json
from contextlib import ExitStack
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from tests.support import IsolatedCase
from tests.plan_fixture import fake_client, sample_plan, sample_ring
from funsport.api import flow
from funsport.run_plan import RunPlan, format_plan, prepare_checkpoint_order
from funsport.track import wire


class CheckpointOrderTests(IsolatedCase):
    """验证编号来自规划顺序，且不能改通过状态或悄悄修已冻结方案。"""

    def points(self):
        """创建四个带稳定身份和不同通过状态的虚构点位。"""
        return [{"id": 31 + index, "lat": lat, "lon": lon,
                 "pointName": "测试点" + str(index), "isPass": index == 1,
                 "state": index, "isFixed": index % 2}
                for index, (lat, lon) in enumerate(sample_ring()[:-1])]

    def ring_for_points(self, points, route_seed=0, with_metadata=False):
        """按传入顺序组成离线折线，并兼容带选路信息的新返回格式。"""
        ring = [(point["lat"], point["lon"]) for point in points]
        ring += [ring[0]]
        return (ring, {}) if with_metadata else ring

    def prepare(self, points, policy=1):
        """模拟策略和路线边界，执行真实的规划与序列化函数。"""
        start = int((datetime.now() - timedelta(days=1)).timestamp() * 1000)
        rule = SimpleNamespace(timestamp=start, policy=policy, min_distance=1000, valid_time=[])
        with patch.object(flow.api_policy, "fetch_policy", return_value=rule), \
                patch.object(flow.api_points, "fetch_points", return_value=(points, {"runAreaId": 7})), \
                patch.object(flow.api_loop, "get_campus_loop", side_effect=self.ring_for_points) as route, \
                patch.object(flow.api_submit, "submit_record") as submit, \
                patch.object(flow.api_obs, "upload_both_keys") as upload, \
                patch.object(flow.log, "disabled", True):
            plan = flow.prepare_run_plan(fake_client(), dist=2, pace=400, cadence=160,
                                         start_ms=start, seed=42)
        submit.assert_not_called()
        upload.assert_not_called()
        return plan, route

    def submission_mocks(self, stack):
        """替换所有提交网络边界，保留HTTP参数和OBS内容供检查。"""
        submit = stack.enter_context(patch.object(flow.api_submit, "submit_record", return_value={"rrid": 123, "uuid": "fixture"}))
        upload = stack.enter_context(patch.object(flow.api_obs, "upload_both_keys", return_value=2))
        stack.enter_context(patch.object(flow.api_records, "fetch_one_record", return_value={"complete": False}))
        stack.enter_context(patch.object(flow.time, "sleep"))
        stack.enter_context(patch.object(flow.log, "disabled", True))
        return submit, upload

    def assert_rejected_before_submit(self, data):
        """错误方案必须在网络请求和单次提交门闩之前被拒绝。"""
        plan = RunPlan.create(fake_client(), data)
        with ExitStack() as stack:
            submit, upload = self.submission_mocks(stack)
            with self.assertRaises(ValueError):
                flow.submit_run_plan(fake_client(), plan, allow_outside_window=True)
            submit.assert_not_called()
            upload.assert_not_called()
        self.assertFalse(plan.attempted)

    def test_missing_sequence_follows_route_without_mutating_source(self):
        """只在复制的规划点位上补零起始编号，身份和通过状态原样保留。"""
        raw = self.points()
        before = copy.deepcopy(raw)
        points, report = prepare_checkpoint_order(raw, 1)
        self.assertEqual(raw, before)
        self.assertEqual([point["position"] for point in points], [0, 1, 2, 3])
        for index, point in enumerate(points):
            self.assertEqual({key: value for key, value in point.items() if key != "position"}, raw[index])
        self.assertEqual(report, {"source": "route_order", "assigned": 4})

    def test_all_sentinels_and_nulls_are_missing_sequence(self):
        """整组只有缺省、null或整数999时，采用同一个规划顺序。"""
        raw = self.points()
        raw[0]["position"], raw[1]["position"], raw[2]["position"] = 999, None, 999
        points, _ = prepare_checkpoint_order(raw, 1)
        self.assertEqual([point["position"] for point in points], [0, 1, 2, 3])

    def test_complete_source_order_is_sorted_not_renumbered(self):
        """保留已有编号的点位身份，按源编号重排实际途经列表。"""
        raw = self.points()
        for point, position in zip(raw, [2, 0, 3, 1]):
            point["position"] = position
        before = copy.deepcopy(raw)
        points, report = prepare_checkpoint_order(raw, 1)
        self.assertEqual([point["id"] for point in points], [32, 34, 31, 33])
        self.assertEqual(points, sorted(before, key=lambda point: point["position"]))
        self.assertEqual(raw, before)
        self.assertEqual(report, {"source": "source", "assigned": 0})

    def test_nonsequential_policies_preserve_input(self):
        """policy为0、2、3和旧版-1时不编号、不排序、不改字段。"""
        raw = self.points()
        raw[0]["position"], raw[1]["position"] = 999, 2
        for policy in (0, 2, 3, -1):
            with self.subTest(policy=policy):
                points, report = prepare_checkpoint_order(raw, policy)
                self.assertEqual(points, raw)
                self.assertIsNot(points[0], raw[0])
                self.assertEqual(report["source"], "unchanged")

    def test_partial_sequence_is_not_guessed(self):
        """已有编号和缺失编号混杂时失败，不覆盖有意义的源顺序。"""
        for value in (None, 999):
            raw = self.points()
            for point in raw:
                point["position"] = value
            raw[0]["position"] = 0
            before = copy.deepcopy(raw)
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "部分缺失"):
                prepare_checkpoint_order(raw, 1)
            self.assertEqual(raw, before)

    def test_malformed_sequences_are_rejected(self):
        """拒绝重复、跳号、一基编号、负数及伪装整数的布尔或文本。"""
        for positions in ([0, 0, 2, 3], [0, 1, 3, 4], [1, 2, 3, 4],
                          [-1, 0, 1, 2], [False, 1, 2, 3], [0.0, 1, 2, 3],
                          ["0", 1, 2, 3], ["999"] * 4):
            raw = self.points()
            for point, position in zip(raw, positions):
                point["position"] = position
            with self.subTest(positions=positions), self.assertRaises(ValueError):
                prepare_checkpoint_order(raw, 1)

    def test_point_count_matches_app_icon_bounds(self):
        """五个编号可用，空列表和六个点不会造成App数组越界。"""
        points, _ = prepare_checkpoint_order(self.points() + [dict(self.points()[0])], 1)
        self.assertEqual([point["position"] for point in points], [0, 1, 2, 3, 4])
        for raw in ([], self.points() + self.points()[:2]):
            with self.subTest(count=len(raw)), self.assertRaises(ValueError):
                prepare_checkpoint_order(raw, 1)

    def test_unknown_policy_is_not_treated_as_sequence(self):
        """不把True、浮点数或字符串1当成已确认的整数策略。"""
        for policy in (None, True, 1.0, "1"):
            with self.subTest(policy=policy), self.assertRaises(ValueError):
                prepare_checkpoint_order(self.points(), policy)

    def test_generation_assigns_same_order_to_route_preview_and_wrapper(self):
        """真实准备流程把相同编号交给路线规划、预览及HTTP包装。"""
        raw = self.points()
        before = copy.deepcopy(raw)
        plan, route = self.prepare(raw)
        data = plan.data()
        self.assertEqual(raw, before)
        self.assertEqual(data["policy"], 1)
        self.assertEqual(route.call_args.args[0], data["points"])
        self.assertEqual(route.call_args.kwargs["route_seed"], 42)
        self.assertEqual([point["position"] for point in data["points"]], [0, 1, 2, 3])
        wrapper = json.loads(data["five_point_json"])
        self.assertEqual(json.loads(wrapper["fivePointJson"]), data["points"])
        self.assertEqual(wrapper["runAreaId"], 7)
        self.assertIn("按本次高德途经顺序补齐0至3", format_plan(plan))
        self.assertIn("跑步策略：1", format_plan(plan))
        plan.validate(fake_client())

    def test_generation_routes_by_existing_order(self):
        """源顺序打乱时，传给高德的列表也同步排序，不只修改上传JSON。"""
        raw = self.points()
        for point, position in zip(raw, [2, 0, 3, 1]):
            point["position"] = position
        plan, route = self.prepare(raw)
        self.assertEqual([point["id"] for point in route.call_args.args[0]], [32, 34, 31, 33])
        self.assertEqual(route.call_args.args[0], plan.data()["points"])
        self.assertIn("沿用源顺序", format_plan(plan))

    def test_generation_for_other_policy_keeps_999(self):
        """完整准备流程在其他策略下维持原行为，不扩大修复范围。"""
        plan, _ = self.prepare(self.points(), policy=2)
        self.assertEqual(plan.data()["policy"], 2)
        self.assertEqual([point["position"] for point in plan.data()["points"]], [999] * 4)
        self.assertIn("当前非顺序模式", format_plan(plan))
        plan.validate(fake_client())

    def test_invalid_order_stops_before_route_request(self):
        """有歧义的顺序在高德路线请求之前停止，也不调用提交。"""
        raw = self.points()
        raw[0]["position"] = 0
        rule = SimpleNamespace(timestamp=1, policy=1, min_distance=1000, valid_time=[])
        with patch.object(flow.api_policy, "fetch_policy", return_value=rule), \
                patch.object(flow.api_points, "fetch_points", return_value=(raw, {})), \
                patch.object(flow.api_loop, "get_campus_loop") as route, \
                patch.object(flow.api_submit, "submit_record") as submit, \
                patch.object(flow.log, "disabled", True):
            with self.assertRaisesRegex(ValueError, "部分缺失"):
                flow.prepare_run_plan(fake_client(), dist=2, pace=400)
        route.assert_not_called()
        submit.assert_not_called()

    def test_submission_keeps_repaired_wrapper_and_pass_states(self):
        """从缺省顺序生成后，HTTP和解压OBS均保持编号与原通过状态。"""
        raw = self.points()
        plan, _ = self.prepare(raw)
        data = plan.data()
        with ExitStack() as stack:
            submit, upload = self.submission_mocks(stack)
            stack.enter_context(patch.object(flow.api_loop, "get_campus_loop", side_effect=AssertionError("不能重新规划")))
            flow.submit_run_plan(fake_client(), plan)
        http_points = json.loads(json.loads(submit.call_args.kwargs["five_point_json"])["fivePointJson"])
        obs = json.loads(upload.call_args.args[2])
        obs_wrapper = json.loads(gzip.decompress(base64.b64decode(obs["fixed_point_json"])))
        self.assertEqual(http_points, data["points"])
        self.assertEqual(json.loads(obs_wrapper["fivePointJson"]), http_points)
        self.assertEqual([point["isPass"] for point in http_points], [point["isPass"] for point in raw])
        self.assertEqual(submit.call_args.kwargs["policy"], 1)

    def test_old_999_plan_requires_new_preview(self):
        """已冻结的旧999方案不能在提交时静默修复，时间外开关也不豁免。"""
        data = sample_plan().data()
        for point in data["points"]:
            point["position"] = 999
        data["five_point_json"] = wire.five_point_wrapper(data["points"], data["track"]["startTime"])
        before = copy.deepcopy(data)
        self.assert_rejected_before_submit(data)
        self.assertEqual(data, before)

    def test_unsorted_frozen_plan_requires_new_preview(self):
        """即使编号存在，冻结列表与规划顺序不一致也必须重新预览。"""
        data = sample_plan().data()
        data["points"].reverse()
        data["five_point_json"] = wire.five_point_wrapper(data["points"], data["track"]["startTime"])
        self.assert_rejected_before_submit(data)

    def test_wrapper_mismatch_is_rejected(self):
        """HTTP包装中的顺序、通过状态或身份不能偏离已预览点位。"""
        for field, value in (("position", 999), ("isPass", True), ("id", 9999)):
            data = sample_plan().data()
            wrapper = json.loads(data["five_point_json"])
            serialized = json.loads(wrapper["fivePointJson"])
            serialized[0][field] = value
            wrapper["fivePointJson"] = json.dumps(serialized)
            data["five_point_json"] = json.dumps(wrapper)
            with self.subTest(field=field):
                self.assert_rejected_before_submit(data)

    def test_malformed_wrapper_is_rejected(self):
        """损坏JSON、裸数组或不支持的压缩标记不能通过提交前检查。"""
        for value in ("not-json", "[]", "{}", json.dumps({"useZip": True, "fivePointJson": "[]"}),
                      json.dumps({"useZip": False, "fivePointJson": []})):
            data = sample_plan().data()
            data["five_point_json"] = value
            with self.subTest(wrapper=value):
                self.assert_rejected_before_submit(data)

    def test_other_policies_also_validate_preview_wrapper(self):
        """非顺序策略仍检查预览与包装一致，但不改变999或源顺序。"""
        for policy in (0, 2, 3, -1):
            data = sample_plan().data()
            data["policy"] = policy
            for point in data["points"]:
                point["position"] = 999
            data["five_point_json"] = wire.five_point_wrapper(data["points"], data["track"]["startTime"])
            RunPlan.create(fake_client(), data).validate(fake_client())
            wrapper = json.loads(data["five_point_json"])
            serialized = json.loads(wrapper["fivePointJson"])
            serialized[0]["id"] = 9999
            wrapper["fivePointJson"] = json.dumps(serialized)
            data["five_point_json"] = json.dumps(wrapper)
            with self.subTest(policy=policy):
                self.assert_rejected_before_submit(data)
