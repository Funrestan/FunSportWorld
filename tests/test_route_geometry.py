"""闭环覆盖、上传坐标及App历史连线规则的离线回归。"""
import base64
import gzip
import json
from unittest.mock import patch

from tests.support import IsolatedCase
from tests.plan_fixture import sample_ring
from funsport import map_preview
from funsport.api.flow import _ring_length
from funsport.coordinates import distance_m
from funsport.track import generator, wire
from funsport.track.geom import make_point_ring, ring_point_at, to_bd


class RouteGeometryTests(IsolatedCase):
    """使用人工闭环验证几何完整性，不调用地图或运动服务。"""

    def build(self, distance, seed=42):
        """沿固定闭环生成已知里程的有序测试轨迹。"""
        with patch.object(generator.log, "disabled", True):
            return generator.build(distance, round(distance / 2.5), seed, 1000,
                                   sample_ring(), ordered_path=True, cadence_target=160)

    def typed_track(self, types, headings=None):
        """创建便于人工核对抽样索引的少量轨迹点。"""
        headings = headings or [0.0] * len(types)
        return {"locations": [{"gLat": 30.6 + index * 0.001, "gLng": 104.1,
                               "type": point_type, "bdD": heading}
                              for index, (point_type, heading) in enumerate(zip(types, headings))]}

    def test_thirty_seeds_complete_requested_lap(self):
        """此前19次不足一圈的30个种子，现在均达到目标且不伪造业务事件。"""
        length = _ring_length(sample_ring())
        for seed in range(30):
            with self.subTest(seed=seed):
                track = self.build(length + 50, seed)
                self.assertGreaterEqual(track["totalDistance"], length)
                self.assertAlmostEqual(track["totalDistance"], length + 50, places=2)
                points = track["locations"]
                self.assertEqual(points[0]["type"], 5)
                self.assertEqual(points[-1]["type"], 6)
                self.assertTrue(all(point["type"] == 0 for point in points[1:-1]))

    def test_one_lap_returns_to_start_on_the_path(self):
        """目标为一整圈时真实上传采样首尾相接，不只在画布上补线。"""
        track = self.build(_ring_length(sample_ring()))
        geometry = map_preview.history_geometry(track)
        self.assertLess(distance_m(geometry["start"], geometry["end"]), 0.03)
        self.assertEqual(geometry["segments"][0][0], geometry["start"])
        self.assertEqual(geometry["segments"][-1][1], geometry["end"])

    def test_partial_extra_lap_does_not_teleport_to_start(self):
        """一圈加部分里程可覆盖闭环，但不强行把终点改回起点。"""
        length = _ring_length(sample_ring())
        track = self.build(length * 1.25)
        geometry = map_preview.history_geometry(track)
        self.assertGreater(distance_m(geometry["start"], geometry["end"]), 100)
        self.assertAlmostEqual(track["totalDistance"], length * 1.25, places=2)

    def test_start_time_distance_and_identifiers_are_consistent(self):
        """起点为t=0，后续时间与里程递增，终点数据和轨迹汇总相同。"""
        track = self.build(_ring_length(sample_ring()) + 50)
        points = track["locations"]
        self.assertEqual((points[0]["totalTime"], points[0]["totalDis"], points[0]["steps"]), (0, 0, 0))
        self.assertEqual((points[0]["gLat"], points[0]["gLng"]), sample_ring()[0])
        self.assertEqual(points[0]["gainTimeMs"], track["startTime"])
        self.assertEqual(points[-1]["totalTime"], track["totalTime"])
        self.assertAlmostEqual(points[-1]["totalDis"], track["totalDistance"], places=2)
        self.assertEqual(points[-1]["steps"], track["totalSteps"])
        self.assertEqual([point["id"] for point in points], list(range(1, len(points) + 1)))
        for previous, current in zip(points, points[1:]):
            self.assertLess(previous["totalTime"], current["totalTime"])
            self.assertLessEqual(previous["totalDis"], current["totalDis"])

    def test_infeasible_speed_does_not_make_terminal_jump(self):
        """无法在速度约束内覆盖里程时失败，不用最后一点瞬移凑距离。"""
        with patch.object(generator.log, "disabled", True), self.assertRaises(ValueError):
            generator.build(2000, 10, 42, 0, sample_ring(), ordered_path=True)

    def test_invalid_samples_are_skipped_not_line_breaks(self):
        """起终点之间的type=-1像App一样跳过，不导致整段线消失。"""
        track = self.typed_track([5, -1, 6])
        coords = map_preview.track_coordinates(track)
        geometry = map_preview.history_geometry(track)
        self.assertIsNone(coords[1])
        self.assertEqual(geometry["segments"], [(coords[0], coords[2], "#00c18b")])

    def test_same_type_and_heading_retains_every_other_point(self):
        """同类型且方向差不超过10度时，对照APK保留第0、2、4点。"""
        track = self.typed_track([0] * 5)
        coords = map_preview.track_coordinates(track)
        self.assertEqual(map_preview.history_geometry(track)["segments"],
                         [(coords[0], coords[2], "#00c18b"), (coords[2], coords[4], "#00c18b")])

    def test_type_and_heading_changes_preserve_points(self):
        """类型变化或方向差超过10度会保留点，边界10度本身不会触发。"""
        track = self.typed_track([0, 0, 0, 5, 6], [0, 10, 21, 21, 21])
        coords = map_preview.track_coordinates(track)
        geometry = map_preview.history_geometry(track)
        self.assertEqual([segment[1] for segment in geometry["segments"]], coords[2:])

    def test_app_colors_and_explicit_markers(self):
        """起终点来自type5/6，灰色和红色业务点不再全部画成蓝线。"""
        track = self.typed_track([0, 5, 3, 4, 7, 10, 6])
        coords = map_preview.track_coordinates(track)
        geometry = map_preview.history_geometry(track)
        self.assertEqual(geometry["start"], coords[1])
        self.assertEqual(geometry["end"], coords[-1])
        self.assertEqual([segment[2] for segment in geometry["segments"]],
                         ["#00c18b", "#b5b5b5", "#b5b5b5", "#ff0000", "#ff0000", "#00c18b"])

    def test_preview_coordinates_equal_decoded_obs(self):
        """预览逐点使用与实际OBS解压后完全相同的七位GCJ坐标。"""
        track = self.build(_ring_length(sample_ring()))
        obs = wire.build_obs_object(track, 123, "fixture", 1, [])
        run_wrapper = json.loads(gzip.decompress(base64.b64decode(obs["run_data"])))
        encoded_points = json.loads(run_wrapper["allLocJson"])
        self.assertEqual(map_preview.track_coordinates(track),
                         [(point["gLat"], point["gLng"]) for point in encoded_points])
        self.assertEqual([point["type"] for point in track["locations"]],
                         [point["type"] for point in encoded_points])

    def test_empty_track_has_no_invented_line_or_markers(self):
        """无有效点时没有轨迹或起终点，不补造位置。"""
        self.assertEqual(map_preview.history_geometry(self.typed_track([-1, -1])),
                         {"segments": [], "start": None, "end": None})

    def test_endpoint_matches_arc_progress_after_snapping(self):
        """逐点吸附完成后，终点仍由真实弧长重算，不被附近顶点覆盖。"""
        dense, arcs, center = make_point_ring(sample_ring(), ordered=True)
        for fraction in (0.003, 0.1, 0.25, 0.99):
            with self.subTest(fraction=fraction):
                distance = arcs[-1] * (1 + fraction)
                track = self.build(distance)
                end = track["locations"][-1]
                x, y = ring_point_at(dense, arcs, distance)
                expected = to_bd(x, y, *center)
                self.assertLess(distance_m((end["gLat"], end["gLng"]), expected), 0.03)

    def test_distance_windows_use_corrected_progress(self):
        """制造0.75m拟合残差，窗口里程仍跟随校正后的实际累计值。"""
        original_fit = generator.fit_speeds

        def undershoot(speeds, durations, target):
            """只在测试中制造允许范围内的拟合偏差，检验末段校正。"""
            original_fit(speeds, durations, target)
            factor = (target - 0.75) / sum(speed * duration for speed, duration in zip(speeds, durations))
            for index in range(len(speeds)):
                speeds[index] *= factor

        with patch.object(generator, "fit_speeds", side_effect=undershoot):
            track = self.build(_ring_length(sample_ring()) + 50)
        windows = track["speedPerTenSec"]
        self.assertAlmostEqual(sum(window["time"] for window in windows), track["totalTime"])
        self.assertLess(abs(sum(window["value"] for window in windows) - track["totalDistance"]),
                        0.005 * len(windows) + 0.01)

    def test_one_second_tail_is_not_dropped_or_extrapolated(self):
        """不足十秒的最后一秒保留真实里程和时长，不扩大成十秒。"""
        track = self.build(1002.5)
        self.assertEqual(track["totalTime"], 401)
        windows = track["speedPerTenSec"]
        self.assertEqual(len(windows), 41)
        self.assertEqual(windows[-1]["time"], 1)
        self.assertEqual(sum(window["time"] for window in windows), 401)
        self.assertLess(abs(sum(window["value"] for window in windows) - track["totalDistance"]), 0.22)
