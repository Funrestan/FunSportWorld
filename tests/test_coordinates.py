"""坐标一致性测试；正反算法残差不等于真实地图定位精度。"""
import copy

from tests.support import IsolatedCase
from funsport import coordinates as geo, map_preview
from funsport.track import wire


class CoordinateTests(IsolatedCase):
    """使用公开地理范围内的人工坐标核对转换和来源选择。"""

    def test_round_trip_grid(self):
        """多纬度多经度的正反转换数值残差小于一厘米。"""
        for lat in (20.1, 30.6, 39.9, 48.2):
            for lon in (87.6, 104.1, 116.4, 123.5):
                with self.subTest(lat=lat, lon=lon):
                    result = geo.bd09_to_gcj02(*geo.gcj02_to_bd09(lat, lon))
                    self.assertLess(geo.distance_m((lat, lon), result), 0.01)

    def test_native_gcj_wins_over_conflicting_bd(self):
        """两套源坐标冲突时统一到原生高德位置，并保留差异统计。"""
        raw = {"glat": 30.6, "glon": 104.1, "lat": 30.6, "lon": 104.1,
               "id": 33, "isPass": False, "position": 4}
        before = copy.deepcopy(raw)
        report = geo.coordinate_report([raw])
        point = wire.five_point_payload([raw], 1000)[0]
        self.assertEqual(raw, before)
        self.assertEqual(report["conflicts"], 1)
        self.assertGreater(report["max_delta_m"], 500)
        self.assertEqual((point["glat"], point["glon"]), (30.6, 104.1))
        self.assertLess(geo.distance_m(geo.bd09_to_gcj02(point["lat"], point["lon"]), (30.6, 104.1)), 0.02)
        self.assertEqual((point["id"], point["position"], point["isPass"]), (33, 4, False))

    def test_bd_only_preserves_source_and_is_idempotent(self):
        """百度源点只转换一次，重复序列化不持续漂移。"""
        raw = {"lat": 30.6, "lon": 104.1}
        once = wire.five_point_payload([raw], 1000)[0]
        repeated = once
        for _ in range(20):
            repeated = wire.five_point_payload([repeated], 1000)[0]
        self.assertLess(geo.distance_m((raw["lat"], raw["lon"]), (repeated["lat"], repeated["lon"])), 0.03)
        self.assertEqual((once["glat"], once["glon"]), (repeated["glat"], repeated["glon"]))

    def test_partial_sentinels_rejected(self):
        """空轴、布尔、非数字和非有限坐标不能进入规划。"""
        for value in (0, -1, True, None, "bad", float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                geo.checkpoint_coordinates({"lat": value, "lon": 104.1})

    def test_preview_uses_same_conversion_as_wire(self):
        """同一轨迹点的上传与地图预览坐标在七位小数内一致。"""
        from tests.plan_fixture import sample_plan
        track = sample_plan().data()["track"]
        preview = map_preview.track_coordinates(track)
        for index, point in enumerate(track["locations"]):
            if point["type"] != -1:
                encoded = wire.conv_point(point, track["startTime"])
                self.assertLess(geo.distance_m(preview[index], (encoded["gLat"], encoded["gLng"])), 0.02)
