"""高德路线返回、闭合和缓存的隔离验证，不请求真实 Key 或服务。"""
import time
import copy
import json
from unittest.mock import MagicMock, patch
import requests

from tests.support import IsolatedCase
from tests.plan_fixture import sample_ring
from funsport import config
from funsport.run_diagnostics import RunDiagnosticArchive
from funsport.api import campus_loop as loop, flow
from funsport.coordinates import checkpoint_coordinates, gcj02_to_bd09


class CampusLoopTests(IsolatedCase):
    """覆盖路径质量、坐标来源、缓存失效及失败停止行为。"""

    def source(self):
        """返回有意制造双坐标冲突的源点及其规范化 BD 闭环。"""
        points = [{"glat": lat, "glon": lon, "lat": lat, "lon": lon} for lat, lon in sample_ring()[:-1]]
        ring = [checkpoint_coordinates(p)[0] for p in points]
        return points, ring + ring[:1]

    def payload(self, steps):
        """组合高德 v3/v5 共用的步行路径包装。"""
        return {"status": "1", "route": {"paths": [{"distance": "1000", "steps": steps}]}}

    def response(self, data):
        """创建带资源关闭语义的 HTTP 模拟响应。"""
        response = MagicMock()
        response.__enter__.return_value = response
        response.status_code = 200
        response.json.return_value = data
        return response

    def legs(self):
        """返回每段一条人工候选道路，保持现有缓存测试的固定几何。"""
        points = sample_ring()[:-1]
        return [[{"points": [origin, points[(index + 1) % len(points)]],
                  "distance": 1000, "source": "v5"}]
                for index, origin in enumerate(points)]

    def test_parse_steps_and_nested_gaps(self):
        """保留合法折线，嵌套步骤也逐段校验接缝。"""
        good = [{"polyline": "104.1,30.6;104.101,30.601"},
                {"steps": [{"polyline": "104.101,30.601;104.102,30.602"}]}]
        points, distance = loop._parse_amap(self.payload(good))
        self.assertEqual((points[0], points[-1], distance), ((30.6, 104.1), (30.602, 104.102), 1000))
        bad = [{"steps": [{"polyline": "104.1,30.6;104.101,30.601"},
                          {"polyline": "105.1,31.6;105.101,31.601"}]}]
        self.assertEqual(loop._parse_amap(self.payload(bad)), ([], 0))

    def test_bad_response_never_produces_partial_route(self):
        """坏坐标和错误结构不会留下可继续生成的半条路线。"""
        for payload in ({"status": "0"}, {"status": "1", "route": []},
                        self.payload([None]), self.payload([{"polyline": 2}]),
                        self.payload([{"polyline": "104,30;NaN,31"}]),
                        self.payload([{"polyline": "104,30;104,91"}])):
            with self.subTest(payload=payload):
                self.assertEqual(loop._parse_amap(payload), ([], 0))

    def test_v3_fallback_closes_both_responses(self):
        """v5 无数据时允许 v3，两个响应都关闭且请求经度在前。"""
        first = self.response({"status": "0"})
        second = self.response(self.payload([{"polyline": "104.1,30.6;104.101,30.601"}]))
        with patch.object(loop.requests, "get", side_effect=[first, second]) as get:
            points, _, version = loop._amap_walking((30.6, 104.1), (30.601, 104.101), "fixture-key")
        self.assertEqual((version, points[0]), ("v3", (30.6, 104.1)))
        self.assertEqual(get.call_args_list[0].kwargs["params"]["origin"], "104.1,30.6")
        self.assertEqual(get.call_args_list[0].kwargs["params"]["alternative_route"], 3)
        first.__exit__.assert_called_once()
        second.__exit__.assert_called_once()

    def test_amap_exchange_is_archived_without_key(self):
        first = self.response({"status": "0"})
        second = self.response(self.payload([{"polyline": "104.1,30.6;104.101,30.601"}]))
        archive = RunDiagnosticArchive("amap-test")
        with archive.active(), patch.object(loop.requests, "get", side_effect=[first, second]):
            loop._amap_walking((30.6, 104.1), (30.601, 104.101), "fixture-key")

        messages = json.loads((archive.directory / "communication.json").read_text(encoding="utf-8"))["messages"]
        self.assertEqual([message["phase"] for message in messages], ["amap-route", "amap-route"])
        self.assertNotIn("fixture-key", json.dumps(messages))
        self.assertEqual(messages[1]["request"]["params"]["origin"], "104.1,30.6")
        self.assertEqual(messages[1]["response"]["route"]["paths"][0]["distance"], "1000")

    def test_amap_failure_does_not_expose_key(self):
        """网络错误即使包含 Key，也只能向用户返回固定安全消息。"""
        with patch.object(loop.requests, "get", side_effect=requests.RequestException("secret=fixture-key")):
            with self.assertRaises(RuntimeError) as error:
                loop._amap_walking((30.6, 104.1), (30.7, 104.2), "fixture-key")
        self.assertNotIn("fixture-key", str(error.exception))

    def test_cache_and_native_gcj_inputs(self):
        """规划直接接收原生 GCJ，第二次命中已校验路线且不读取 Key。"""
        points, _ = self.source()
        with patch.object(loop, "get_amap_key", return_value="fixture"), patch.object(loop, "_fetch_route_legs", return_value=self.legs()) as build:
            ring = loop.get_campus_loop(points)
        self.assertEqual(build.call_args.args[0], sample_ring()[:-1])
        self.assertEqual(ring[0], ring[-1])
        with patch.object(loop, "get_amap_key", side_effect=AssertionError("cache should work")):
            self.assertEqual(loop.get_campus_loop(points), ring)
        self.assertTrue((self.data / "campus_loop_bd.json").exists())

    def test_bad_cache_requires_rebuild(self):
        """版本、来源、顺序、过期、未来时间和坏路径都会让缓存失效。"""
        points, _ = self.source()
        legs = self.legs()
        original = {"schema": loop.CACHE_SCHEMA, "provider": loop.CACHE_PROVIDER,
                    "fingerprint": loop._points_fingerprint(sample_ring()[:-1]), "ts": time.time() * 1000,
                    "legs": legs, "options_digest": loop._options_digest(legs)}
        corrupt = copy.deepcopy(legs)
        corrupt[0][0]["points"][0] = [float("nan"), 104]
        for change in ({"schema": 3}, {"provider": "fitted"}, {"ts": 1},
                       {"ts": time.time() * 1000 + 60000}, {"legs": [[30, 104]]},
                       {"fingerprint": loop._points_fingerprint(list(reversed(sample_ring()[:-1])))},
                       {"legs": corrupt}, {"options_digest": ""}, {"legs": list(reversed(legs))}):
            with self.subTest(change=change):
                config.save_json(self.data / "campus_loop_bd.json", {**original, **change})
                with patch.object(loop, "get_amap_key", return_value="fixture"), patch.object(loop, "_fetch_route_legs", return_value=legs) as build:
                    loop.get_campus_loop(points)
                build.assert_called_once()

    def test_invalid_points_rejected_before_key_or_network(self):
        """不跳过无坐标点位，也不请求非法经纬度。"""
        with patch.object(loop, "get_amap_key") as key, self.assertRaises(ValueError):
            loop.get_campus_loop([{}, {"lat": 30.6, "lon": 104.1}])
        key.assert_not_called()

    def test_single_polyline_teleport_rejected(self):
        """单条 polyline 内的跨城市跳点不能以端点正常为由被接受。"""
        data = self.payload([{"polyline": "104.1,30.6;110,30.6;104.101,30.601"}])
        self.assertEqual(loop._parse_amap(data), ([], 0))

    def test_json_decode_failure_closes_response(self):
        """响应正文不是 JSON 时关闭资源并尝试另一个高德版本。"""
        first = self.response(None)
        first.json.side_effect = ValueError("fixture decode failure")
        second = self.response(self.payload([{"polyline": "104.1,30.6;104.101,30.601"}]))
        with patch.object(loop.requests, "get", side_effect=[first, second]):
            self.assertEqual(loop._amap_walking((30.6, 104.1), (30.601, 104.101), "fixture")[2], "v3")
        first.__exit__.assert_called_once()

    def test_full_gcj_route_preview_and_wire_chain(self):
        """仅替换 HTTP，核对每段请求及返回路线的预览和上传坐标一致。"""
        from funsport import map_preview
        from funsport.track import wire
        gcj = sample_ring()
        points, _ = self.source()
        responses = [self.response(self.payload([{"polyline": "{},{};{},{}".format(a[1], a[0], b[1], b[0])}]))
                     for a, b in zip(gcj, gcj[1:])]
        with patch.object(loop, "get_amap_key", return_value="fixture"), \
                patch.object(loop.requests, "get", side_effect=responses) as get, \
                patch.object(loop.time, "sleep"):
            ring = loop.get_campus_loop(points)
        for call, a, b in zip(get.call_args_list, gcj, gcj[1:]):
            self.assertEqual(call.kwargs["params"]["origin"], "{},{}".format(a[1], a[0]))
            self.assertEqual(call.kwargs["params"]["destination"], "{},{}".format(b[1], b[0]))
        self.assertEqual(get.call_count, len(gcj) - 1)
        from tests.plan_fixture import sample_plan
        template = sample_plan().data()["track"]["locations"][0]
        track = {"locations": [{**template, "gLat": lat, "gLng": lon, "type": 3} for lat, lon in ring]}
        preview = map_preview.track_coordinates(track)
        for coordinate, point in zip(preview, track["locations"]):
            encoded = wire.conv_point(point, 1000)
            self.assertLess(loop.dist_m(coordinate, (encoded["gLat"], encoded["gLng"])), 0.02)
        for source in gcj:
            self.assertLess(min(loop.dist_m(source, vertex) for vertex in preview), 0.02)

    def test_missing_key_or_route_failure_never_builds_track(self):
        """缺 Key 或路线接口失败时直接停止，不降级为数学拟合轨迹。"""
        points, _ = self.source()
        with patch.object(loop, "get_amap_key", return_value=""), patch.object(flow.generator, "build") as build:
            with self.assertRaises(RuntimeError):
                flow._build_amap_track(points, 2000, 400, 160, 42, 1000)
            build.assert_not_called()
        with patch.object(loop, "get_campus_loop", side_effect=RuntimeError("failed")), patch.object(flow.generator, "build") as build:
            with self.assertRaises(RuntimeError):
                flow._build_amap_track(points, 2000, 400, 160, 42, 1000)
            build.assert_not_called()

    def test_segment_endpoints_and_closure(self):
        """环必须通过各请求端点并连续闭合，不补长直线修复断路。"""
        gcj = sample_ring()[:-1]
        bd = [gcj02_to_bd09(*p) for p in gcj]
        responses = [[([p, gcj[(i + 1) % len(gcj)]], 1000, "v5")] for i, p in enumerate(gcj)]
        with patch.object(loop, "_amap_walking", side_effect=responses), patch.object(loop.time, "sleep"):
            result = loop.build_loop(bd, "fixture", verbose=False, checkpoints_gcj=gcj)
        self.assertEqual(result[0], result[-1])
        responses[-1] = [([gcj[-1], (gcj[0][0] + 0.0003, gcj[0][1])], 1000, "v5")]
        with patch.object(loop, "_amap_walking", side_effect=responses), patch.object(loop.time, "sleep"):
            self.assertIsNone(loop.build_loop(bd, "fixture", verbose=False, checkpoints_gcj=gcj))
