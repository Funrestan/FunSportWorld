"""Offline checks for the Android location pace convention."""
import copy
import math
import unittest
from unittest.mock import patch

from funsport.coordinates import gcj02_to_bd09, distance_m
from funsport.track import generator, pace, wire
from tests.plan_fixture import sample_ring


class LocationPaceTests(unittest.TestCase):
    def point(self, seconds, longitude=104.1, point_type=0):
        latitude, longitude = gcj02_to_bd09(30.6, longitude)
        return {"gLat": latitude, "gLng": longitude, "gainTimeMs": seconds * 1000,
                "totalTime": seconds, "type": point_type,
                "speed": 99.0, "avgSpeed": 99.0, "bdG": -1, "bdS": 2.3}

    def test_centimetre_ceiling_and_threshold_keep_raw_precision(self):
        self.assertEqual(pace.pace_from_distance(10.001, 6000), 6000 / (10.01 * 60))
        self.assertEqual(pace.pace_from_distance(10, 1200), 2)
        self.assertLess(pace.pace_from_distance(10, 1199.9), 2)
        self.assertGreater(pace.pace_from_distance(10, 1200.1), 2)

    def test_stationary_invalid_time_and_excessive_pace_are_zero(self):
        for distance, elapsed in ((0, 5000), (-1, 5000), (10, 0), (10, -1),
                                  (1, 600001), (math.inf, 1000), (10, math.nan)):
            with self.subTest(distance=distance, elapsed=elapsed):
                self.assertEqual(pace.pace_from_distance(distance, elapsed), 0)
        self.assertEqual(pace.pace_from_distance(1, 600000), 10000)

    def test_gain_time_matches_wire_precision_and_has_timer_fallback(self):
        previous, current = self.point(0), self.point(5, 104.1001)
        distance = distance_m((30.6, 104.1), (30.6, 104.1001))
        self.assertAlmostEqual(pace.location_pace(previous, current),
                               pace.pace_from_distance(distance, 5000))
        previous["gainTime"] = "2026-09-24 07:00:00"
        current["gainTime"] = "2026-09-24 07:00:10"
        self.assertAlmostEqual(pace.location_pace(previous, current),
                               pace.pace_from_distance(distance, 10000))
        current["gainTime"] = previous["gainTime"]
        self.assertAlmostEqual(pace.location_pace(previous, current),
                               pace.pace_from_distance(distance, 5000))
        current["gainTime"] = "2026-09-24 06:59:59"
        self.assertEqual(pace.location_pace(previous, current), 0)

    def test_missing_or_malformed_fields_do_not_create_motion(self):
        previous, current = self.point(0), self.point(5, 104.1001)
        self.assertEqual(pace.location_pace(None, current), 0)
        self.assertEqual(pace.location_pace({}, current), 0)
        current.update(gainTimeMs=None, totalTime="invalid")
        self.assertEqual(pace.location_pace(previous, current), 0)

    def test_invalid_samples_do_not_move_valid_anchor_or_mutate_metadata(self):
        previous = self.point(0, point_type=5)
        invalid = self.point(2, 105, -1)
        current = self.point(5, 104.1001, 8)
        endpoint = self.point(10, 104.1002, 6)
        locations = [previous, invalid, current, endpoint]
        originals = copy.deepcopy(locations)
        expected = pace.location_pace(previous, current)
        pace.apply_location_paces(locations)
        self.assertEqual((previous["speed"], previous["avgSpeed"]), (0, 0))
        self.assertEqual((invalid["speed"], invalid["avgSpeed"]), (0, 0))
        self.assertAlmostEqual(current["speed"], expected, delta=0.0051)
        self.assertAlmostEqual(current["avgSpeed"], 50 / (expected * 3), delta=0.0051)
        self.assertGreater(endpoint["speed"], 0)
        for before, after in zip(originals, locations):
            self.assertEqual({k: v for k, v in before.items() if k not in ("speed", "avgSpeed")},
                             {k: v for k, v in after.items() if k not in ("speed", "avgSpeed")})

    def test_storage_uses_official_rounding_and_unrounded_reciprocal(self):
        locations = [self.point(0, point_type=5), self.point(5, 104.1001)]
        with patch.object(pace, "location_pace", return_value=3.3349):
            pace.apply_location_paces(locations)
        self.assertEqual(locations[1]["speed"], 3.34)
        self.assertEqual(locations[1]["avgSpeed"], 5.0)

    def test_generator_recomputes_after_geometry_and_marker_changes(self):
        with patch.object(generator.log, "disabled", True):
            track = generator.build(2000, 800, 42, 1000, sample_ring(), ordered_path=True)
            repeated = generator.build(2000, 800, 42, 1000, sample_ring(), ordered_path=True)
        self.assertEqual(track, repeated)
        locations = track["locations"]
        self.assertEqual((locations[0]["type"], locations[-1]["type"]), (5, 6))
        for previous, current in zip(locations, locations[1:]):
            raw_pace = pace.location_pace(previous, current)
            self.assertGreater(current["speed"], 0)
            self.assertAlmostEqual(current["speed"], raw_pace, delta=0.0051)
            self.assertAlmostEqual(current["avgSpeed"], 50 / (raw_pace * 3), delta=0.0051)
            encoded = wire.conv_point(current, track["startTime"])
            self.assertEqual((encoded["speed"], encoded["avgSpeed"]),
                             (current["speed"], current["avgSpeed"]))


if __name__ == "__main__":
    unittest.main()
