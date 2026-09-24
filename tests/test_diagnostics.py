"""覆盖打卡点包装、压缩、损坏数据和隐私边界。"""
import base64
import copy
import gzip
import json
from unittest.mock import patch

from tests.support import IsolatedCase
from funsport.diagnostics import analyze_checkpoints, analyze_run_checkpoints, decode_value, format_report, inspect_file
from funsport.track.wire import five_point_wrapper


class DiagnosticTests(IsolatedCase):
    """所有样本均为离线测试数据。"""

    def test_coordinate_conflict_is_reported_without_locations(self):
        """双坐标冲突只展示米数和数量，不输出源位置或点名。"""
        data = {"fivePointJson": [{"glat": 30.6, "glon": 104.1, "lat": 30.6, "lon": 104.1,
                                    "pointName": "private-point"}]}
        report = analyze_checkpoints(data)
        self.assertEqual(report["sources"][0]["coordinate_conflicts"], 1)
        text = format_report(report)
        self.assertIn("双坐标不一致", text)
        self.assertNotIn("private-point", text)
        self.assertNotIn("104.1", text)

    def test_render_context_is_evidence_not_mode_override(self):
        """只记录原始数字模式字段，不推测或修改服务端运动类型。"""
        raw = {"sportType": 1, "policy": 2, "fivePointJson": []}
        report = analyze_checkpoints(raw)
        self.assertEqual(report["render_contexts"], [{"path": "$", "sportType": 1, "policy": 2}])
        self.assertIn("sportType=1 / policy=2", format_report(report))
        self.assertEqual(analyze_checkpoints({"sportType": "token-secret", "policy": True})["render_contexts"], [])

    def test_conflicting_complete_is_unknown(self):
        """不同包装层的达标状态冲突时不能以后一个 True 覆盖 False。"""
        report = analyze_checkpoints({"complete": False, "record": {"complete": True}})
        self.assertIsNone(report["complete"])
        self.assertIn("冲突", format_report(report))

    def test_current_wire_wrapper(self):
        """检查现有工具的双层 JSON，而不是误把包装对象当列表。"""
        sample = [{"lat": 30.6, "lon": 104.1, "pointName": "测试点"}]
        report = analyze_checkpoints({"fivePointJson": five_point_wrapper(sample, 1000)})
        self.assertEqual(report["status"], "present")
        self.assertEqual(report["sources"][0]["gcj_valid"], 1)
        self.assertEqual(report["sources"][0]["bd_valid"], 1)

    def test_compressed_obs(self):
        """验证 OBS 的 Base64、Gzip、JSON 三层解码。"""
        wrapper = {"fivePointJson": json.dumps([{"glat": 30.6, "glon": 104.1, "isPass": True}])}
        encoded = base64.b64encode(gzip.compress(json.dumps(wrapper).encode())).decode()
        report = analyze_checkpoints({"fixed_point_json": encoded})
        self.assertEqual(report["sources"][0]["passed"], 1)
        self.assertEqual(report["sources"][0]["gcj_valid"], 1)

    def test_complete_is_not_checkpoints(self):
        """服务端 complete=true 不能被诊断为存在打卡点。"""
        report = analyze_checkpoints({"complete": True, "allLocJson": "[]"})
        self.assertTrue(report["complete"])
        self.assertEqual(report["status"], "missing")

    def test_server_rule_overrides_no_checkpoint_conclusions(self):
        """整体达标仍可能未通过顺序点位规则，原始两个状态都保留。"""
        report = analyze_checkpoints({"complete": True, "reasonList": [
            {"type": 9, "complete": False, "completeStatus": 0, "reason": "private-text"},
            {"type": 1, "complete": True, "completeStatus": 1},
        ]})
        self.assertTrue(report["complete"])
        self.assertIs(report["checkpoint_rule_complete"], False)
        self.assertEqual(len(report["rules"]), 2)
        text = format_report(report)
        self.assertIn("按顺序通过所有点位：未通过", text)
        self.assertIn("距离：通过", text)
        self.assertNotIn("private-text", text)

    def test_rule_complete_requires_unambiguous_boolean(self):
        """规则的数字状态或字符串不能替代明确的布尔值。"""
        report = analyze_checkpoints({"reasonList": [{"type": 9, "complete": "true", "completeStatus": 1}]})
        self.assertIsNone(report["checkpoint_rule_complete"])
        conflict = analyze_checkpoints({"reasonList": [{"type": 9, "complete": True}],
                                        "record": {"reasonList": [{"type": 9, "complete": False}]}})
        self.assertIsNone(conflict["checkpoint_rule_complete"])
        self.assertIn("顺序点位规则状态缺失或冲突", format_report(conflict))

    def test_combined_local_evidence_does_not_verify_remote_obs(self):
        """详情省略点位时，本地快照可核对，但不能据此确认远端内容。"""
        points = [{"position": index, "isPass": False} for index in range(5)]
        wrapper = {"fivePointJson": json.dumps(points)}
        obs = {"fixed_point_json": base64.b64encode(gzip.compress(json.dumps(wrapper).encode())).decode()}
        detail = {"complete": True, "fivePointJson": "", "reasonList": [{"type": 9, "complete": False}]}
        original = copy.deepcopy((detail, wrapper, obs))
        report = analyze_run_checkpoints(detail, wrapper, obs)
        self.assertEqual(report["status"], "empty")
        self.assertEqual(report["local_obs"]["sources"][0]["passed"], 0)
        self.assertEqual([pair["status"] for pair in report["point_state_comparisons"]],
                         ["match", "unknown", "unknown"])
        self.assertIs(report["remote_obs_verified"], False)
        self.assertIs(report["checkpoint_rule_complete"], False)
        self.assertEqual((detail, wrapper, obs), original)
        self.assertIn("未下载验证远端对象", format_report(report))

    def test_point_state_comparison_finds_changed_order_and_state(self):
        """点位通过数量相同也不能掩盖顺序或逐点状态差异。"""
        points = [{"position": 0, "isPass": True}, {"position": 1, "isPass": False}]
        for changed in (list(reversed(points)), [{"position": 0, "isPass": False}, {"position": 1, "isPass": True}]):
            with self.subTest(changed=changed):
                report = analyze_run_checkpoints({"fivePointJson": points}, points,
                                                 {"fixed_point_json": {"fivePointJson": changed}})
                self.assertEqual([pair["status"] for pair in report["point_state_comparisons"]],
                                 ["mismatch", "match", "mismatch"])

    def test_ambiguous_or_missing_points_cannot_compare(self):
        """缺状态、重复序号、占位点、空点位或损坏项都不作为匹配证明。"""
        for points in ([], [{"position": 0}], [{"position": 999, "isPass": True}],
                       [{"position": 0, "isPass": True}] * 2, ["invalid"],
                       [{"position": True, "isPass": True}]):
            with self.subTest(points=points):
                report = analyze_run_checkpoints({}, points, {"fixed_point_json": {"fivePointJson": points}})
                self.assertEqual(report["point_state_comparisons"][0]["status"], "unknown")
        self.assertTrue(all(pair["status"] == "unknown"
                            for pair in analyze_run_checkpoints({})["point_state_comparisons"]))

    def test_empty_and_corrupt_are_distinct(self):
        """区分缺字段、空列表和无法解析的字段。"""
        for payload, status in (({}, "missing"), ({"fivePointJson": "[]"}, "empty"),
                                ({"fivePointJson": "broken"}, "invalid")):
            with self.subTest(status=status):
                self.assertEqual(analyze_checkpoints(payload)["status"], status)

    def test_invalid_coordinates(self):
        """拒绝空值、无穷值、越界和字符串布尔值作为有效坐标或通过状态。"""
        report = analyze_checkpoints({"fivePointJson": [{"glat": float("nan"), "glon": 104,
                                                        "lat": 91, "lon": 181, "isPass": "true"}]})
        source = report["sources"][0]
        self.assertEqual((source["gcj_valid"], source["bd_valid"], source["passed"]), (0, 0, 0))

    def test_read_only_and_private(self):
        """诊断不修改输入，也不输出令牌、姓名或原始点名。"""
        payload = {"token": "do-not-print", "name": "PRIVATE", "fivePointJson": []}
        original = copy.deepcopy(payload)
        report = format_report(analyze_checkpoints(payload))
        self.assertEqual(payload, original)
        self.assertNotIn("do-not-print", report)
        self.assertNotIn("PRIVATE", report)

    def test_compressed_size_limit(self):
        """限制解压体积，避免小压缩文件消耗大量内存。"""
        data = base64.b64encode(gzip.compress(b"x" * 5000)).decode()
        with patch("funsport.diagnostics.MAX_BYTES", 100):
            with self.assertRaises(ValueError):
                decode_value(data)

    def test_nested_limit(self):
        """过深包装返回明确解析警告。"""
        payload = {"fivePointJson": []}
        for _ in range(12):
            payload = {"data": payload}
        self.assertEqual(analyze_checkpoints(payload)["status"], "invalid")

    def test_utf8_bom_file(self):
        """用户选择的 UTF-8 BOM 文件可以离线诊断。"""
        filename = self.data / "example.json"
        filename.write_text('{"fivePointJson": []}', encoding="utf-8-sig")
        self.assertEqual(inspect_file(filename)["status"], "empty")

    def test_file_limit(self):
        """超过文件大小限制时停止解析。"""
        filename = self.data / "example.json"
        filename.write_text(" " * 101, encoding="utf-8")
        with patch("funsport.diagnostics.MAX_BYTES", 100):
            with self.assertRaises(ValueError):
                inspect_file(filename)
