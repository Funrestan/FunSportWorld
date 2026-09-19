"""11016 上下文和无服务器本地预览的隔离测试。"""
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tests.support import IsolatedCase
from tests.plan_fixture import fake_client, sample_plan, sample_ring
from funsport import config
from funsport.api import client as client_api, flow, policy, submit
from funsport.api.errors import BusinessError
from funsport.run_plan import format_plan


class ServerTimeTests(IsolatedCase):
    """用假响应证明本地开关不吞掉服务器拒绝，不调用真实接口。"""

    def test_business_error_keeps_safe_context(self):
        """显示接口与失败阶段，但不暴露 URL 查询串中的令牌。"""
        problem = BusinessError(11016, "不在有效跑步时间内", policy.POLICY_PATH + "?token=private-query")
        self.assertEqual(problem.code, 11016)
        self.assertEqual(problem.path, policy.POLICY_PATH)
        self.assertNotIn("private-query", str(problem))
        self.assertIn("尚未生成或提交", str(problem))
        self.assertIn("本地时间检查", str(problem))

    def test_other_errors_do_not_get_time_diagnosis(self):
        """其他业务错误仍保留原含义，不误套时间限制说明。"""
        problem = BusinessError(10001, "其他错误", "/api/example")
        self.assertIn("其他错误", str(problem))
        self.assertNotIn("开放时段", str(problem))

    def test_client_raises_structured_policy_error(self):
        """通用客户端把假服务端 11016 转成带接口的结构化异常。"""
        client = client_api.ApiClient.__new__(client_api.ApiClient)
        client.identity = {}
        client.session_data = {"uid": 1, "token": "fixture-token"}
        client.env_session = None
        client.http = Mock()
        client.http.request.return_value = SimpleNamespace(status_code=200, content=b"fixture")
        envelope = SimpleNamespace(json="{}", ts_ms=1, key_data=(1, 2))
        with patch.object(client_api, "build_header_for", return_value=("header", [])), \
                patch.object(client_api, "build_envelope", return_value=envelope), \
                patch.object(client_api, "derive_paes_key", return_value=b"fixture"), \
                patch.object(client_api, "decrypt_response", return_value=SimpleNamespace(business={"error": 11016, "message": "不在有效跑步时间内"})), \
                patch.object(client_api.log, "disabled", True):
            with self.assertRaises(BusinessError) as raised:
                client.call("POST", policy.POLICY_PATH, '{"password":"private-body"}')
        self.assertEqual(raised.exception.path, policy.POLICY_PATH)
        self.assertNotIn("private-body", str(raised.exception))

    def test_outside_flag_does_not_swallow_policy_rejection(self):
        """策略阶段被拒绝后，开关即使开启，也不能继续获取点位或提交。"""
        problem = BusinessError(11016, "不在有效跑步时间内", policy.POLICY_PATH)
        with patch.object(flow.api_policy, "fetch_policy", side_effect=problem), \
                patch.object(flow.api_points, "fetch_points") as points, \
                patch.object(flow.api_submit, "submit_record") as record, \
                patch.object(flow.log, "disabled", True):
            with self.assertRaises(BusinessError):
                flow.prepare_run_plan(fake_client(), dist=1.6, pace=400, allow_outside_window=True)
            points.assert_not_called()
            record.assert_not_called()

    def test_submit_error_reports_submission_stage(self):
        """直接提交接口的 11016 也标明提交阶段，而非误称仍在生成预览。"""
        client = fake_client()
        client.token = lambda: "fixture-token"
        client.env_session = None
        client.http = Mock()
        client.http.post.return_value = SimpleNamespace(status_code=200, content=b"fixture")
        envelope = SimpleNamespace(json="{}", key_data=(1, 2))
        with patch.object(submit, "build_android_header", return_value=("header", [])), \
                patch.object(submit, "build_envelope", return_value=envelope), \
                patch.object(submit, "derive_paes_key", return_value=b"fixture"), \
                patch.object(submit, "decrypt_response", return_value=SimpleNamespace(business={"error": 11016, "message": "不在有效跑步时间内"})), \
                patch.object(submit.log, "disabled", True):
            with self.assertRaises(BusinessError) as raised:
                submit.submit_record(client, sample_plan().data()["track"], 1, 1, 1000)
        self.assertEqual(raised.exception.path, submit.RECORD_PATH)
        self.assertIn("提交跑步记录", str(raised.exception))
        self.assertNotIn("尚未生成", str(raised.exception))


class LocalPreviewTests(IsolatedCase):
    """验证过期缓存只用于不可提交的几何测试，不伪造学校策略。"""

    def cache_points(self):
        """保存一个匹配示例账号、但故意过期的缓存。"""
        context = {"uid": 1, "unid": "1", "anchor": [30.6, 104.1], "runAreaId": None}
        config.save_json(config.POINTS_CACHE, {"points": sample_plan().data()["points"],
                                               "context": context, "metadata": {}, "ts": 1000})

    def test_route_preview_calls_no_sports_operation(self):
        """轨迹预览使用高德路线，但不调用运动策略、点位、提交或 OBS。"""
        self.cache_points()
        with ExitStack() as stack:
            boundaries = [stack.enter_context(patch.object(module, name, side_effect=AssertionError("禁止网络边界")))
                          for module, name in ((flow.api_policy, "fetch_policy"), (flow.api_points, "fetch_points"),
                                               (flow.api_submit, "submit_record"),
                                               (flow.api_obs, "upload_both_keys"))]
            stack.enter_context(patch.object(flow.log, "disabled", True))
            amap = stack.enter_context(patch.object(flow.api_loop, "get_campus_loop", return_value=(sample_ring(), {})))
            build = stack.enter_context(patch.object(flow.generator, "build", wraps=flow.generator.build))
            plan = flow.prepare_route_preview(fake_client(), 1.6, 400, 160, before=60, seed=42)
            for boundary in boundaries:
                boundary.assert_not_called()
            amap.assert_called_once()
            self.assertEqual(build.call_args.args[4], sample_ring())
            self.assertTrue(build.call_args.kwargs["ordered_path"])
        self.assertTrue(plan.data()["preview_only"])
        self.assertIsNone(plan.data()["policy"])
        self.assertIn("不可提交", format_plan(plan))
        self.assertIn("缓存点位时间", format_plan(plan))

    def test_local_preview_cannot_submit_even_with_override(self):
        """即使调用后端并显式跳过时间检查，本地测试轨迹也不能提交。"""
        self.cache_points()
        with patch.object(flow.log, "disabled", True), \
                patch.object(flow.api_loop, "get_campus_loop", return_value=(sample_ring(), {})):
            plan = flow.prepare_route_preview(fake_client(), 1.6, 400, 160, before=60, seed=42)
        with patch.object(flow.api_submit, "submit_record") as record:
            for outside in (False, True):
                with self.subTest(outside=outside), self.assertRaises(ValueError):
                    flow.submit_run_plan(fake_client(), plan, outside)
            record.assert_not_called()
        self.assertFalse(plan.attempted)

    def test_local_preview_requires_matching_cache(self):
        """不使用空缓存、别的账号缓存或无法证明归属的旧格式缓存。"""
        with self.assertRaises(ValueError):
            flow.prepare_route_preview(fake_client(), 1.6, 400, 160)
        self.cache_points()
        cached = config.load_points_cache(with_metadata=True)
        cached["context"]["uid"] = 999
        config.save_json(config.POINTS_CACHE, cached)
        with self.assertRaises(ValueError):
            flow.prepare_route_preview(fake_client(), 1.6, 400, 160)
        cached.pop("context")
        config.save_json(config.POINTS_CACHE, cached)
        with self.assertRaises(ValueError):
            flow.prepare_route_preview(fake_client(), 1.6, 400, 160)
