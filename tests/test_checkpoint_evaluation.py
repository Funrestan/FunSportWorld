"""Offline sequence replay and frozen upload consistency checks."""
import copy
import json
from unittest.mock import patch

from tests.support import IsolatedCase
from funsport.coordinates import gcj02_to_bd09
from funsport.track import wire
from funsport.track.checkpoints import evaluate_checkpoints, resolve_fences, _in_polygon


class CheckpointEvaluationTests(IsolatedCase):
    def points(self):
        return wire.five_point_payload([
            {"id": 11 + i, "position": i, "glat": 30.6, "glon": 104.1 + i * .001,
             "isPass": False, "state": 7, "isFixed": int(i == 0)} for i in range(5)
        ], 1000)

    def location(self, seconds, target, kind=0, offset=.00006):
        lat, lon = gcj02_to_bd09(30.6, 104.1 + target * .001 + offset)
        return {"totalTime": seconds, "gLat": lat, "gLng": lon, "type": kind,
                "speed": 999, "avgSpeed": 999}

    def track(self):
        return {"startTime": 1000, "locations": [self.location(0, 0, 5, 0),
                self.location(5, 0), self.location(60, 1), self.location(120, 2),
                self.location(180, 3), self.location(240, 4), self.location(300, 4, 6, .0001)]}

    def test_complete_sequence_updates_copies_and_records_actual_samples(self):
        track, points = self.track(), self.points()
        original = copy.deepcopy((track, points))
        final_track, final_points, report = evaluate_checkpoints(track, points, 1)
        self.assertEqual((track, points), original)
        self.assertTrue(all(p["isPass"] for p in final_points))
        self.assertEqual([p["type"] for p in final_track["locations"]], [5, 2, 2, 2, 2, 2, 6])
        self.assertEqual([e["elapsed_seconds"] for e in report["events"]], [5, 60, 120, 180, 240])
        self.assertEqual([e["position"] for e in report["events"]], list(range(5)))
        self.assertEqual([p["id"] for p in final_points], list(range(11, 16)))
        self.assertEqual([p["state"] for p in final_points], [7] * 5)
        self.assertTrue(report["all_passed"])
        self.assertFalse(report["native_validity_verified"])
        self.assertFalse(report["server_verified"])

    def test_earlier_visit_cannot_pass_a_future_target(self):
        track = self.track()
        track["locations"][2] = self.location(60, 2)
        track["locations"][3] = self.location(120, 1)
        _, points, report = evaluate_checkpoints(track, self.points(), 1)
        self.assertEqual([p["isPass"] for p in points], [True, True, False, False, False])
        self.assertEqual(report["pending_positions"], [2, 3, 4])

    def test_one_sample_can_only_advance_one_overlapping_target(self):
        points = self.points()
        for point in points:
            for key in ("lat", "lon", "glat", "glon"):
                point[key] = points[0][key]
        track = {"locations": self.track()["locations"][:2]}
        _, points, report = evaluate_checkpoints(track, points, 1)
        self.assertEqual([p["isPass"] for p in points], [True, False, False, False, False])
        self.assertEqual(len(report["events"]), 1)

    def test_start_and_finish_do_not_pass_targets(self):
        track = {"locations": [self.location(0, 0, 5, 0), self.location(5, 0, 6)]}
        _, points, report = evaluate_checkpoints(track, self.points(), 1)
        self.assertFalse(any(p["isPass"] for p in points))
        self.assertEqual(report["skipped_counts"]["start_or_end_marker"], 2)

    def test_stationary_sample_does_not_pass_target(self):
        track = {"locations": [self.location(0, 0, 5, 0), self.location(5, 0, 0, 0)]}
        _, points, report = evaluate_checkpoints(track, self.points(), 1)
        self.assertFalse(points[0]["isPass"])
        self.assertEqual(report["samples"][1]["decision"], "pace_below_two")

    def test_invalid_paused_and_excluded_types_cannot_pass(self):
        for kind in (-1, 3, 7, 99):
            with self.subTest(kind=kind):
                track = self.track()
                track["locations"][2]["type"] = kind
                _, points, _ = evaluate_checkpoints(track, self.points(), 1)
                self.assertFalse(points[1]["isPass"])
        track = self.track()
        track["locations"][2]["isPaused"] = True
        _, points, report = evaluate_checkpoints(track, self.points(), 1)
        self.assertFalse(points[1]["isPass"])
        self.assertEqual(report["samples"][2]["decision"], "paused")

    def test_raw_pace_threshold_includes_two(self):
        for pace, passed in ((1.99999, False), (2.0, True)):
            with self.subTest(pace=pace), patch("funsport.track.checkpoints.location_pace", return_value=pace):
                _, points, _ = evaluate_checkpoints(self.track(), self.points(), 1)
                self.assertEqual(points[0]["isPass"], passed)

    def test_radius_boundary_includes_25(self):
        track = {"locations": self.track()["locations"][:2]}
        for distance, passed in ((25.0, True), (25.00001, False)):
            with self.subTest(distance=distance), patch("funsport.track.checkpoints.distance_m", return_value=distance):
                _, points, _ = evaluate_checkpoints(track, self.points(), 1)
                self.assertEqual(points[0]["isPass"], passed)

    def fence(self, fence_id=7, offset=0):
        return {"id": fence_id, "points": [
            {"glat": lat, "glng": lon + offset}
            for lat, lon in [(30.59, 104.09), (30.61, 104.09), (30.61, 104.11), (30.59, 104.11)]]}

    def test_policy_fence_is_used_when_point_metadata_has_empty_fences(self):
        _, points, report = evaluate_checkpoints(self.track(), self.points(), 1,
            {"geoFencesJson": "[]"}, {"geoFences": [self.fence(offset=1)]})
        self.assertFalse(any(p["isPass"] for p in points))
        self.assertEqual(report["fences"], {"source": "policy", "count": 1})
        self.assertEqual(report["skipped_counts"]["outside_fence"], 5)

    def test_selected_area_uses_its_fence_union(self):
        fences = {"geoFences": [self.fence(7), self.fence(8, offset=1)]}
        areas = [{"id": 20, "fenceIds": [8]}]
        _, points, _ = evaluate_checkpoints(self.track(), self.points(), 1,
                                            {"runAreaId": 20}, fences, areas)
        self.assertFalse(any(p["isPass"] for p in points))
        _, points, _ = evaluate_checkpoints(self.track(), self.points(), 1,
                                            {"runAreaId": -1}, fences, areas)
        self.assertTrue(all(p["isPass"] for p in points))

    def test_recovery_pass_preserves_type_and_skips_ordinary_fence_gate(self):
        for kind in (8, 9):
            with self.subTest(kind=kind):
                track = {"locations": self.track()["locations"][:2]}
                track["locations"][1]["type"] = kind
                final, points, report = evaluate_checkpoints(track, self.points(), 1,
                    geo_fence={"geoFences": [self.fence(offset=1)]})
                self.assertTrue(points[0]["isPass"])
                self.assertEqual(final["locations"][1]["type"], kind)
                self.assertEqual(report["events"][0]["stored_type"], kind)

    def test_cached_pass_states_do_not_replace_new_run_arrivals(self):
        points = self.points()
        points[0]["isPass"] = True
        _, final, report = evaluate_checkpoints(self.track(), points, 1)
        self.assertTrue(all(p["isPass"] for p in final))
        self.assertEqual(report["source_passed_positions"], [0])
        self.assertEqual(len(report["events"]), 5)
        _, empty, report = evaluate_checkpoints({"locations": []}, points, 1)
        self.assertFalse(any(p["isPass"] for p in empty))
        self.assertFalse(report["all_passed"])
        self.assertTrue(points[0]["isPass"])

    def test_polygon_edges_match_official_half_open_algorithm(self):
        polygon = [(30, 104), (31, 104), (31, 105), (30, 105)]
        self.assertTrue(_in_polygon((30.5, 104.5), polygon))
        self.assertTrue(_in_polygon((30, 104.5), polygon))
        self.assertTrue(_in_polygon((30.5, 104), polygon))
        self.assertFalse(_in_polygon((31, 104.5), polygon))
        self.assertFalse(_in_polygon((30.5, 105), polygon))

    def test_non_sequence_modes_are_not_reinterpreted(self):
        for policy in (0, 2, None, True):
            with self.subTest(policy=policy):
                track, points = self.track(), self.points()
                final_track, final_points, report = evaluate_checkpoints(track, points, policy)
                self.assertEqual(final_track, track)
                self.assertEqual(final_points, points)
                self.assertFalse(report["supported"])
                self.assertIsNone(report["all_passed"])

    def test_bad_time_order_and_bad_fences_are_rejected(self):
        track = self.track()
        track["locations"][2]["totalTime"] = 5
        with self.assertRaisesRegex(ValueError, "increasing"):
            evaluate_checkpoints(track, self.points(), 1)
        for value in ("not-json", {"wrong": []}, [{"points": []}]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                resolve_fences({"geoFencesJson": value})
        with self.assertRaisesRegex(ValueError, "missing fence"):
            resolve_fences({"runAreaId": 1}, {"geoFences": [self.fence()]}, [{"id": 1, "fenceIds": [9]}])

    def test_missing_sample_fields_are_audited_and_never_pass(self):
        _, points, report = evaluate_checkpoints({"locations": [{"type": 0}]}, self.points(), 1)
        self.assertFalse(any(p["isPass"] for p in points))
        self.assertEqual(report["samples"][0]["decision"], "invalid_sample_time")

    def test_final_wrapper_serializes_evaluated_state(self):
        track, points, _ = evaluate_checkpoints(self.track(), self.points(), 1)
        wrapper = wire.five_point_wrapper(points, track["startTime"])
        self.assertEqual(json.loads(json.loads(wrapper)["fivePointJson"]), points)
