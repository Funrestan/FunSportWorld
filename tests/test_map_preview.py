"""地图投影、底图解码和失败路径测试，不使用真实地图 Key。"""
import io
from unittest.mock import Mock, patch

from PIL import Image
import requests

from tests.support import IsolatedCase
from funsport import map_preview


class MapTests(IsolatedCase):
    """验证底图和路径共享相同坐标与像素变换。"""

    def test_projection_round_trip(self):
        """像素投影及其逆变换保持坐标。"""
        lat, lon = 30.601, 104.101
        restored = map_preview.unproject(*map_preview.project(lat, lon, 16), 16)
        self.assertAlmostEqual(lat, restored[0], places=7)
        self.assertAlmostEqual(lon, restored[1], places=7)

    def test_fit_keeps_all_points_visible(self):
        """适配后所有样本点落入指定画布内部。"""
        coords = [(30.6, 104.1), (30.61, 104.12), (30.595, 104.105)]
        center, zoom = map_preview.fit_view(coords, 600, 300)
        for point in coords:
            x, y = map_preview.screen_position(point, center, zoom, 600, 300)
            self.assertTrue(0 <= x <= 600 and 0 <= y <= 300)
        self.assertEqual(map_preview.screen_position(center, center, zoom, 600, 300), (300, 150))

    def test_track_conversion_and_invalid_gaps(self):
        """轨迹转换到高德坐标，定位无效点保留断线标志。"""
        track = {"locations": [{"gLat": 30.6, "gLng": 104.1, "type": 3},
                                {"gLat": 30.6, "gLng": 104.1, "type": -1}]}
        coords = map_preview.track_coordinates(track)
        self.assertNotEqual(coords[0], (30.6, 104.1))
        self.assertIsNone(coords[1])

    def response(self, content):
        """构造支持流式读取和上下文管理的离线 HTTP 响应。"""
        response = Mock(status_code=200)
        response.iter_content.return_value = [content]
        context = Mock()
        context.__enter__ = Mock(return_value=response)
        context.__exit__ = Mock(return_value=False)
        return context

    def test_background_requests_only_center(self):
        """底图请求不包含轨迹、点位数组和运动账号信息。"""
        stream = io.BytesIO()
        Image.new("RGB", (600, 300), "white").save(stream, format="PNG")
        with patch.object(map_preview, "get_amap_key", return_value="test-key"), \
                patch.object(map_preview.requests, "get", return_value=self.response(stream.getvalue())) as get:
            image = map_preview.fetch_background((30.6, 104.1), 16, 600, 300)
        self.assertEqual(image.size, (600, 300))
        self.assertEqual(set(get.call_args.kwargs["params"]), {"key", "location", "zoom", "size", "scale"})
        self.assertNotIn("paths", get.call_args.kwargs["params"])

    def test_no_key_does_not_request(self):
        """没有配置 Key 时只返回可操作提示，不发送无效请求。"""
        with patch.object(map_preview, "get_amap_key", return_value=""), patch.object(map_preview.requests, "get") as get:
            with self.assertRaises(ValueError):
                map_preview.fetch_background((30.6, 104.1), 16, 600, 300)
            get.assert_not_called()

    def test_error_does_not_expose_key(self):
        """网络异常中即使带 Key，也只向上返回固定安全提示。"""
        with patch.object(map_preview, "get_amap_key", return_value="secret-test-key"), \
                patch.object(map_preview.requests, "get", side_effect=requests.RequestException("key=secret-test-key")):
            with self.assertRaises(ValueError) as raised:
                map_preview.fetch_background((30.6, 104.1), 16, 600, 300)
        self.assertNotIn("secret-test-key", str(raised.exception))

    def test_json_error_and_wrong_size(self):
        """JSON 错误响应和尺寸错误都不能被当成底图叠加。"""
        stream = io.BytesIO()
        Image.new("RGB", (1, 1)).save(stream, format="PNG")
        for content in (b'{"info":"INVALID_USER_KEY"}', stream.getvalue()):
            with self.subTest(size=len(content)), patch.object(map_preview, "get_amap_key", return_value="test"), \
                    patch.object(map_preview.requests, "get", return_value=self.response(content)):
                with self.assertRaises(ValueError):
                    map_preview.fetch_background((30.6, 104.1), 16, 600, 300)
