"""官方备选道路、种子选路与候选缓存的隔离回归。"""
import copy
import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from tests.support import IsolatedCase
from tests.plan_fixture import fake_client, sample_ring
from funsport import config
from funsport.api import campus_loop as loop, flow
from funsport.run_plan import format_plan


class RoadOptionTests(IsolatedCase):
    """模拟地图返回不同道路，不凭坐标抖动宣称道路发生变化。"""

    def points(self):
        """提供固定顺序、固定身份和未通过状态的四个虚构点位。"""
        return [{"id": index + 31, "position": index, "isPass": False,
                 "glat": lat, "glon": lon, "pointName": "测试点" + str(index)}
                for index, (lat, lon) in enumerate(sample_ring()[:-1])]

    def legs(self, count=3, checkpoints=None):
        """每段提供几何不同的人工道路，代表高德返回的备选而非真实查询。"""
        checkpoints = checkpoints or sample_ring()[:-1]
        legs = []
        for index, origin in enumerate(checkpoints):
            destination = checkpoints[(index + 1) % len(checkpoints)]
            options = []
            for variant in range(count):
                mid = ((origin[0] + destination[0]) / 2 + variant * 0.0003,
                       (origin[1] + destination[1]) / 2)
                options.append({"points": [origin, mid, destination], "distance": 1000, "source": "v5"})
            legs.append(options)
        return legs

    def payload(self, options):
        """把人工候选转换成高德JSON返回格式。"""
        return {"status": "1", "route": {"paths": [
            {"distance": str(option["distance"]),
             "steps": [{"polyline": ";".join("{},{}".format(lon, lat) for lat, lon in option["points"])}]}
            for option in options]}}

    def response(self, payload):
        """创建会关闭资源的HTTP响应替身。"""
        response = MagicMock()
        response.__enter__.return_value = response
        response.json.return_value = payload
        return response

    def warm_cache(self, count=3):
        """只在隔离临时目录中建立候选缓存，不访问用户目录。"""
        with patch.object(loop, "get_amap_key", return_value="fixture"), \
                patch.object(loop, "_fetch_route_legs", return_value=self.legs(count)), \
                patch.object(loop.log, "disabled", True):
            return loop.get_campus_loop(self.points(), route_seed=0, with_metadata=True)

    def prepare_plan(self, seed):
        """保留真实选路和轨迹生成，仅替换运动服务读取边界。"""
        start = int((datetime.now() - timedelta(days=1)).timestamp() * 1000)
        policy = SimpleNamespace(timestamp=start, policy=1, min_distance=1000, valid_time=[])
        with patch.object(flow.api_policy, "fetch_policy", return_value=policy), \
                patch.object(flow.api_points, "fetch_points", return_value=(self.points(), {})), \
                patch.object(flow.api_submit, "submit_record") as submit, \
                patch.object(flow.api_obs, "upload_both_keys") as upload, \
                patch.object(loop, "get_amap_key", side_effect=AssertionError("应命中候选缓存")), \
                patch.object(flow.log, "disabled", True):
            plan = flow.prepare_run_plan(fake_client(), dist=2, pace=400, cadence=160,
                                         start_ms=start, seed=seed)
        submit.assert_not_called()
        upload.assert_not_called()
        return plan

    def test_single_request_returns_up_to_three_options(self):
        """一次v5请求启用alternative_route=3，读取三条而不发三次请求。"""
        response = self.response(self.payload(self.legs(4)[0]))
        with patch.object(loop.requests, "get", return_value=response) as get:
            options = loop._amap_walking(sample_ring()[0], sample_ring()[1], "fixture", all_routes=True)
        self.assertEqual(len(options), 3)
        get.assert_called_once()
        self.assertEqual(get.call_args.kwargs["params"]["alternative_route"], 3)
        response.__exit__.assert_called_once()

    def test_invalid_and_duplicate_options_do_not_count(self):
        """坏的首条和重复路线不掩盖有效备选，也不虚报道路数量。"""
        payload = self.payload(self.legs()[0])
        payload["route"]["paths"][0] = {"distance": "10", "steps": [{"polyline": "broken"}]}
        payload["route"]["paths"][2] = copy.deepcopy(payload["route"]["paths"][1])
        with patch.object(loop.requests, "get", return_value=self.response(payload)) as get:
            options = loop._amap_walking(sample_ring()[0], sample_ring()[1], "fixture", all_routes=True)
        self.assertEqual(len(options), 1)
        get.assert_called_once()

    def test_seed_changes_roads_without_network_or_cache_rewrite(self):
        """缓存完整候选后，种子0/1/2产生不同道路，而相同种子复现。"""
        first, selection = self.warm_cache()
        cache = self.data / "campus_loop_bd.json"
        before = cache.read_bytes()
        with patch.object(loop, "get_amap_key", side_effect=AssertionError("缓存不能读取Key")), \
                patch.object(loop.requests, "get", side_effect=AssertionError("换种子无需重新请求")), \
                patch.object(loop.log, "disabled", True):
            second, info2 = loop.get_campus_loop(self.points(), route_seed=1, with_metadata=True)
            third, info3 = loop.get_campus_loop(self.points(), route_seed=2, with_metadata=True)
            repeat, repeated_info = loop.get_campus_loop(self.points(), route_seed=1, with_metadata=True)
        self.assertEqual(len({selection["road_fingerprint"], info2["road_fingerprint"], info3["road_fingerprint"]}), 3)
        self.assertNotEqual(first, second)
        self.assertNotEqual(second, third)
        self.assertEqual((second, info2), (repeat, repeated_info))
        self.assertEqual(before, cache.read_bytes())
        self.assertEqual(info2["segment_candidates"], [3, 3, 3, 3])
        self.assertEqual(info2["candidate_combinations"], 81)
        self.assertEqual(second[0], second[-1])

    def test_single_road_is_reported_without_faking_variation(self):
        """每段只有一条时坦诚返回同一道路，不按种子画假岔路。"""
        first, info = self.warm_cache(count=1)
        with patch.object(loop.log, "disabled", True), patch.object(loop, "warn") as warning:
            second, second_info = loop.get_campus_loop(self.points(), route_seed=987, with_metadata=True)
        self.assertEqual((first, info), (second, second_info))
        self.assertEqual(info["candidate_combinations"], 1)
        warning.assert_called_once()
        self.assertIn("没有备选道路", warning.call_args.args[0])

    def test_broken_join_skips_combo_instead_of_drawing_connector(self):
        """候选端点相差超过3米时尝试另一组合，不新增跨接直线。"""
        legs = self.legs()
        lat, lon = legs[0][0]["points"][-1]
        legs[0][0]["points"][-1] = (lat + 0.0001, lon)
        bd = [loop.gcj02_to_bd09(*point) for point in sample_ring()[:-1]]
        with patch.object(loop.log, "disabled", True):
            ring, selection = loop._select_loop(legs, bd, 0)
        self.assertNotEqual(selection["selected_variant"], 1)
        self.assertEqual(ring[0], ring[-1])

    def test_all_broken_combos_preserve_previous_cache(self):
        """所有组合断线时生成失败，不覆盖之前有效的候选缓存。"""
        self.warm_cache()
        cache = self.data / "campus_loop_bd.json"
        before = cache.read_bytes()
        legs = self.legs(count=1)
        lat, lon = legs[0][0]["points"][-1]
        legs[0][0]["points"][-1] = (lat + 0.0001, lon)
        with patch.object(loop, "get_amap_key", return_value="fixture"), \
                patch.object(loop, "_fetch_route_legs", return_value=legs), \
                patch.object(loop.log, "disabled", True), self.assertRaises(RuntimeError):
            loop.get_campus_loop(self.points(), force_rebuild=True)
        self.assertEqual(before, cache.read_bytes())

    def test_old_single_loop_cache_requires_successful_refresh(self):
        """旧schema3不再锁定道路，更新失败时保留旧文件但不冒充新候选。"""
        cache = self.data / "campus_loop_bd.json"
        config.save_json(cache, {"schema": 3, "provider": loop.CACHE_PROVIDER, "points": sample_ring()})
        before = cache.read_bytes()
        with patch.object(loop, "get_amap_key", return_value="fixture"), \
                patch.object(loop, "_fetch_route_legs", return_value=None), \
                patch.object(loop.log, "disabled", True), self.assertRaises(RuntimeError):
            loop.get_campus_loop(self.points(), route_seed=42)
        self.assertEqual(before, cache.read_bytes())
        self.warm_cache()
        self.assertEqual(config.load_json(cache)["schema"], 4)

    def test_candidate_tampering_requires_refresh(self):
        """即使改的是本次未选中的候选，也必须通过全内容摘要校验。"""
        self.warm_cache()
        cache = self.data / "campus_loop_bd.json"
        stored = config.load_json(cache)
        stored["legs"][0][2]["points"][1][0] += 0.00001
        config.save_json(cache, stored)
        with patch.object(loop, "get_amap_key", return_value="fixture"), \
                patch.object(loop, "_fetch_route_legs", return_value=self.legs()) as fetch, \
                patch.object(loop.log, "disabled", True):
            loop.get_campus_loop(self.points())
        fetch.assert_called_once()

    def test_candidate_limits_and_coordinates_are_validated(self):
        """缓存中的空段、超量候选、布尔坐标和重复道路全部拒绝。"""
        cases = [[], self.legs(4)]
        bad_coordinate = self.legs()
        bad_coordinate[0][0]["points"][0] = (True, 104.1)
        cases.append(bad_coordinate)
        duplicate = self.legs()
        duplicate[0][1] = copy.deepcopy(duplicate[0][0])
        cases.append(duplicate)
        for candidates in cases:
            with self.subTest(legs=len(candidates)):
                self.assertIsNone(loop._validated_legs(candidates, sample_ring()[:-1]))

    def test_invalid_seed_does_not_request_or_replace_cache(self):
        """非整数道路种子在读取Key或请求之前被拒绝。"""
        for seed in (True, "1", None, 1.5):
            with self.subTest(seed=seed), patch.object(loop, "get_amap_key") as key, self.assertRaises(ValueError):
                loop.get_campus_loop(self.points(), route_seed=seed)
            key.assert_not_called()

    def test_plan_seeds_choose_different_roads_keep_checkpoint_order(self):
        """道路选择保持点位身份与顺序，评估后的状态与包装保持一致。"""
        self.warm_cache()
        first, second = self.prepare_plan(1), self.prepare_plan(2)
        one, two = first.data(), second.data()
        self.assertNotEqual(one["route"]["road_fingerprint"], two["route"]["road_fingerprint"])
        self.assertEqual([point["id"] for point in one["points"]], [31, 32, 33, 34])
        self.assertEqual([point["position"] for point in two["points"]], [0, 1, 2, 3])
        self.assertTrue(all(point["isPass"] is True for point in two["points"]))
        self.assertEqual([event["position"] for event in two["checkpoint_evaluation"]["events"]], [0, 1, 2, 3])
        self.assertEqual(json.loads(json.loads(two["five_point_json"])["fivePointJson"]), two["points"])
        first.validate(fake_client())
        second.validate(fake_client())
        self.assertIn("道路指纹", format_plan(second))
        self.assertIn("组合上限", format_plan(second))

    def test_auto_seed_is_fresh_even_when_clock_does_not_advance(self):
        """自动种子不再靠毫秒时间，不会因相同时间戳固定选路。"""
        self.warm_cache()
        with patch.object(flow.random, "SystemRandom") as random_source:
            random_source.return_value.randrange.side_effect = [1, 2]
            first, second = self.prepare_plan(0), self.prepare_plan(0)
        self.assertEqual((first.data()["seed"], second.data()["seed"]), (1, 2))
        self.assertNotEqual(first.data()["route"]["road_fingerprint"], second.data()["route"]["road_fingerprint"])

    def test_route_preview_uses_seed_but_remains_unsubmittable(self):
        """仅轨迹预览也可换道路，但没有学校策略时仍不能提交。"""
        self.warm_cache()
        context = {"uid": 1, "unid": "1", "anchor": [30.6, 104.1], "runAreaId": None}
        config.save_json(config.POINTS_CACHE, {"points": self.points(), "context": context, "metadata": {}, "ts": 1})
        with patch.object(flow.log, "disabled", True), \
                patch.object(loop, "get_amap_key", side_effect=AssertionError("缓存不能请求Key")):
            first = flow.prepare_route_preview(fake_client(), 2, 400, 160, seed=1)
            second = flow.prepare_route_preview(fake_client(), 2, 400, 160, seed=2)
        self.assertNotEqual(first.data()["route"]["road_fingerprint"], second.data()["route"]["road_fingerprint"])
        with self.assertRaises(ValueError):
            second.validate(fake_client())

    def test_first_response_and_cached_selection_match(self):
        """同一种子直接解析HTTP响应与随后读取候选缓存选出的道路一致。"""
        responses = [self.response(self.payload(options)) for options in self.legs()]
        with patch.object(loop, "get_amap_key", return_value="fixture"), \
                patch.object(loop.requests, "get", side_effect=responses) as get, \
                patch.object(loop.time, "sleep"), patch.object(loop.log, "disabled", True):
            first = loop.get_campus_loop(self.points(), route_seed=40, with_metadata=True)
        self.assertEqual(get.call_count, 4)
        with patch.object(loop, "get_amap_key", side_effect=AssertionError("缓存无需Key")), \
                patch.object(loop.requests, "get", side_effect=AssertionError("缓存不能发HTTP")), \
                patch.object(loop.log, "disabled", True):
            cached = loop.get_campus_loop(self.points(), route_seed=40, with_metadata=True)
        self.assertEqual(first, cached)

    def test_five_point_three_option_space_reaches_last_combo(self):
        """五点三候选的第243种组合仍能被准确选择，没有边界漏选。"""
        checkpoints = sample_ring()[:-1] + [(30.603, 104.097)]
        legs = self.legs(checkpoints=checkpoints)
        bd = [loop.gcj02_to_bd09(*point) for point in checkpoints]
        with patch.object(loop.log, "disabled", True):
            ring, selected = loop._select_loop(legs, bd, 242)
            expected = loop._assemble_loop(legs, [2] * 5)
        self.assertEqual(selected["candidate_combinations"], 243)
        self.assertEqual(selected["selected_variant"], 243)
        self.assertEqual(ring, expected)

    def test_incompatible_combo_search_is_bounded(self):
        """超过512种且全部不连通时有界失败，不无限枚举或补线。"""
        checkpoints = sample_ring()[:-1] + [(30.603, 104.097), (30.601, 104.098)]
        legs = self.legs(checkpoints=checkpoints)
        bd = [loop.gcj02_to_bd09(*point) for point in checkpoints]
        with patch.object(loop, "_assemble_loop", return_value=None) as assemble, self.assertRaises(RuntimeError):
            loop._select_loop(legs, bd, 42)
        self.assertEqual(assemble.call_count, loop.MAX_COMBINATION_TRIES)

    def test_exact_twenty_four_hour_cache_is_expired(self):
        """达到24小时边界即刷新，不因换种子或读取缓存延长有效期。"""
        self.warm_cache()
        cache = self.data / "campus_loop_bd.json"
        stored = config.load_json(cache)
        now = 2_000_000_000.0
        stored["ts"] = int(now * 1000) - loop.CACHE_TTL_MS
        config.save_json(cache, stored)
        with patch.object(loop.time, "time", return_value=now), \
                patch.object(loop, "get_amap_key", return_value="fixture"), \
                patch.object(loop, "_fetch_route_legs", return_value=self.legs()) as fetch, \
                patch.object(loop.log, "disabled", True):
            loop.get_campus_loop(self.points(), route_seed=1)
        fetch.assert_called_once()
