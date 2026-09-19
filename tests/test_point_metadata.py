"""点位包装元数据及账号缓存隔离测试。"""
import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tests.support import IsolatedCase
from tests.plan_fixture import fake_client
from funsport import config
from funsport.api import points


class PointTests(IsolatedCase):
    """用假点位接口验证不会跨账号或使用过期数据准备新方案。"""

    def client(self):
        """提供可记录调用次数的离线点位客户端。"""
        client = fake_client()
        client.env_session = None
        client.call = Mock(return_value={"error": 10000, "data": {
            "pointsResModels": [{"id": 17, "lat": 30.6, "lon": 104.1}],
            "runAreaId": 7, "geoFencesJson": "[]", "freedomShowFence": True}})
        return client

    def test_metadata_survives_network_and_cache(self):
        """接口和缓存两条路径都保留跑区和围栏信息。"""
        client = self.client()
        with patch.object(points, "build_envelope", return_value=SimpleNamespace(json="fixture")):
            first = points.fetch_points(client, with_metadata=True)
            second = points.fetch_points(client, with_metadata=True)
        self.assertEqual(first, second)
        self.assertEqual(first[1]["runAreaId"], 7)
        self.assertTrue(first[1]["freedomShowFence"])
        client.call.assert_called_once()

    def test_point_request_does_not_force_sport_type(self):
        """点位请求按参考客户端不带 sportType，不能强行请求自由跑类型。"""
        client = self.client()
        with patch.object(points, "build_envelope", return_value=SimpleNamespace(json="fixture")):
            points.fetch_points(client)
        body = json.loads(client.call.call_args.args[2])
        self.assertNotIn("sportType", body)
        self.assertEqual(set(body), {"longitude", "latitude", "sign", "uuid", "selectedUnid", "runec"})

    def test_old_request_cache_is_not_reused_or_fallback(self):
        """旧请求版本缓存不进入在线方案，请求失败也不能回退该缓存。"""
        client = self.client()
        with patch.object(points, "build_envelope", return_value=SimpleNamespace(json="fixture")):
            points.fetch_points(client)
            cached = config.load_points_cache(with_metadata=True)
            cached["metadata"].pop("point_request_schema")
            config.save_json(config.POINTS_CACHE, cached)
            client.call.side_effect = RuntimeError("fixture-error")
            with self.assertRaises(RuntimeError):
                points.fetch_points(client)
        self.assertEqual(client.call.call_count, 2)

    def test_account_change_does_not_reuse_cached_points(self):
        """账号或学校变化时旧缓存不参与新的点位请求。"""
        client = self.client()
        with patch.object(points, "build_envelope", return_value=SimpleNamespace(json="fixture")):
            points.fetch_points(client)
            client.session_data["unid"] = "different"
            points.fetch_points(client)
        self.assertEqual(client.call.call_count, 2)

    def test_fresh_failure_does_not_fall_back(self):
        """准备新方案时请求失败必须报错，不能静默使用缓存替代。"""
        client = self.client()
        with patch.object(points, "build_envelope", return_value=SimpleNamespace(json="fixture")):
            points.fetch_points(client)
            client.call.side_effect = RuntimeError("offline")
            with self.assertRaises(RuntimeError):
                points.fetch_points(client, fresh=True)
        self.assertTrue(config.POINTS_CACHE.exists())

    def test_preview_uses_fresh_cache_but_rejects_stale_fallback(self):
        """反复预览可复用有效缓存，缓存过期后网络失败不能降级。"""
        client = self.client()
        with patch.object(points, "build_envelope", return_value=SimpleNamespace(json="fixture")):
            points.fetch_points(client, allow_stale=False)
            points.fetch_points(client, allow_stale=False)
            client.call.assert_called_once()
            cached = config.load_points_cache(with_metadata=True)
            cached["ts"] = 0
            config.save_json(config.POINTS_CACHE, cached)
            client.call.side_effect = RuntimeError("offline")
            with self.assertRaises(RuntimeError):
                points.fetch_points(client, allow_stale=False)
