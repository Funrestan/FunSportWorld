"""Completion inference and signed submission, with all network boundaries mocked."""
import json
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tests.support import IsolatedCase
from tests.plan_fixture import fake_client, sample_plan
from funsport.api import policy, submit
from funsport.completion import evaluate_completion


def passed_points():
    return [{"position": index, "isPass": True} for index in range(5)]


class CompletionTests(IsolatedCase):
    def evaluate(self, *, duration=600, distance=2000, points=None, rules=None):
        return evaluate_completion(
            {"totalTime": duration, "totalDistance": distance},
            passed_points() if points is None else points, 1, 1000, rules)

    def test_complete_requires_points_distance_and_selected_time(self):
        result = self.evaluate(duration=600, distance=1000, rules={"minRunTime": 600})
        self.assertTrue(result["complete"])
        self.assertEqual(result["unCompleteReason"], 0)
        self.assertTrue(all(rule["complete"] for rule in result["rules"].values()))

    def test_official_failure_priority_and_reason_codes(self):
        cases = [
            ({"duration": 30, "distance": 500, "points": [], "rules": {"minRunTime": 60}}, 2),
            ({"duration": 31, "distance": 500, "points": [], "rules": {"minRunTime": 60}}, 9),
            ({"duration": 31, "distance": 500, "rules": {"minRunTime": 60}}, 10),
            ({"duration": 60, "distance": 500, "rules": {"minRunTime": 60}}, 1),
        ]
        for kwargs, reason in cases:
            with self.subTest(reason=reason):
                result = self.evaluate(**kwargs)
                self.assertFalse(result["complete"])
                self.assertEqual(result["unCompleteReason"], reason)

    def test_all_points_must_have_boolean_pass_state(self):
        points = passed_points()
        points[3]["isPass"] = "false"
        result = self.evaluate(points=points)
        self.assertFalse(result["complete"])
        self.assertEqual(result["rules"]["sequentialCheckpoints"]["passed"], 4)

    def test_malformed_sequences_cannot_become_complete_subsets(self):
        cases = (
            [], [0, 1, 2, 999], [0, 0, 1], [0, 2], [1, 0], [1],
            [0, 1, 2, 3, 4, 5], [False, 1], [0.0, 1], ["0", 1],
        )
        for positions in cases:
            with self.subTest(positions=positions):
                points = [{"position": value, "isPass": True} for value in positions]
                result = self.evaluate(points=points)
                self.assertFalse(result["complete"])
                self.assertEqual(result["unCompleteReason"], 9)
                self.assertFalse(result["rules"]["sequentialCheckpoints"]["validSequence"])

    def test_unknown_policy_returns_unknown_instead_of_success(self):
        for mode in (7, True, 1.0, "1"):
            with self.subTest(policy=mode):
                result = evaluate_completion({}, [], mode, 1000)
                self.assertFalse(result["supported"])
                self.assertIsNone(result["complete"])
                self.assertIsNone(result["unCompleteReason"])

    def test_missing_minimum_time_and_unrecovered_rules_are_explicit(self):
        result = self.evaluate(rules={"speedTop": 3, "stepBottom": 120})
        self.assertEqual(result["rules"]["minimumRunTime"]["threshold"], 0)
        self.assertTrue(any("Missing minRunTime" in item for item in result["assumptions"]))
        self.assertNotIn("speedTop", result["rules"])

    def test_nonfinite_values_cannot_become_a_complete_result(self):
        with self.assertRaises(ValueError):
            self.evaluate(distance=float("nan"))


class PolicyRuleTests(IsolatedCase):
    def test_fetch_retains_full_policy_and_fence_data(self):
        raw = {
            "timestamp": 123, "policy": 1,
            "runRuleModel": {"minDistance": 2000, "minRunTime": 600, "stepBottom": 120},
            "geoFence": {"updateTime": 9, "geoFences": [{"id": 7}]},
            "runAreaModels": [{"id": 3, "fenceIds": [7]}],
        }
        client = Mock(session_data={"unid": "1"})
        client.call.return_value = {"data": raw}
        with patch.object(policy, "ok"):
            info = policy.fetch_policy(client)
        self.assertEqual(info.run_rules, raw["runRuleModel"])
        self.assertEqual(info.geo_fence, raw["geoFence"])
        self.assertEqual(info.run_area_models, raw["runAreaModels"])
        raw["runRuleModel"]["minRunTime"] = 999
        self.assertEqual(info.run_rules["minRunTime"], 600)

    def test_old_policy_constructor_keeps_optional_fields(self):
        info = policy.PolicyInfo(123, 1, 1000, [])
        self.assertEqual(info.run_rules, {})
        self.assertIsNone(info.geo_fence)
        self.assertIsNone(info.run_area_models)


class SubmitCompletionTests(IsolatedCase):
    def submit_body(self, *, completion=None, five_point_json="", run_rules=None):
        client = fake_client()
        client.token = lambda: "fixture-token"
        client.env_session = None
        client.http = Mock()
        client.http.post.return_value = SimpleNamespace(status_code=200, content=b"fixture")
        envelope = SimpleNamespace(json="{}", key_data=(1, 2))
        archive = Mock()
        with ExitStack() as stack:
            stack.enter_context(patch.object(submit, "build_android_header", return_value=("header", [])))
            stack.enter_context(patch.object(submit, "build_envelope", return_value=envelope))
            stack.enter_context(patch.object(submit, "derive_paes_key", return_value=b"fixture"))
            stack.enter_context(patch.object(submit, "decrypt_response", return_value=SimpleNamespace(
                business={"error": 10000, "rrid": 123})))
            stack.enter_context(patch.object(submit.log, "disabled", True))
            sign = stack.enter_context(patch.object(submit, "signature", return_value="signed"))
            submit.submit_record(client, sample_plan().data()["track"], 1, 1, 1000,
                                 completion=completion, five_point_json=five_point_json,
                                 run_rules=run_rules, diagnostics=archive)
        snapshots = {call.args[0]: call.args[1] for call in archive.capture.call_args_list}
        self.assertEqual(sign.call_args.args[0], snapshots["submit_body.json"])
        return snapshots["submit_body.json"], snapshots["completion.json"]

    def test_missing_points_is_signed_as_incomplete(self):
        body, result = self.submit_body()
        self.assertFalse(body["complete"])
        self.assertEqual(body["unCompleteReason"], 9)
        self.assertEqual(body["complete"], result["complete"])

    def test_direct_submit_evaluates_the_serialized_points(self):
        wrapper = json.dumps({"fivePointJson": json.dumps(passed_points())})
        body, result = self.submit_body(five_point_json=wrapper, run_rules={"minRunTime": 9999})
        self.assertFalse(body["complete"])
        self.assertEqual(body["unCompleteReason"], 10)
        self.assertTrue(result["rules"]["sequentialCheckpoints"]["complete"])

    def test_explicit_completion_is_preserved_in_signed_payload(self):
        wrapper = json.dumps({"fivePointJson": json.dumps(passed_points())})
        result = evaluate_completion(
            sample_plan().data()["track"], passed_points(), 1, 1000)
        body, captured = self.submit_body(completion=result, five_point_json=wrapper)
        self.assertTrue(body["complete"])
        self.assertEqual(body["unCompleteReason"], 0)
        self.assertEqual(captured, result)

    def test_unknown_or_inconsistent_completion_stops_before_network(self):
        client = fake_client()
        client.http = Mock()
        for completion in (
            {"supported": False, "complete": None, "unCompleteReason": None},
            {"supported": True, "complete": True, "unCompleteReason": 9},
        ):
            with self.subTest(completion=completion), self.assertRaises(ValueError):
                submit.submit_record(client, sample_plan().data()["track"], 1, 1, 1000,
                                     completion=completion)
        client.http.post.assert_not_called()

    def test_explicit_complete_cannot_override_missing_points_or_unknown_policy(self):
        client = fake_client()
        client.http = Mock()
        track = sample_plan().data()["track"]
        completed = evaluate_completion(track, passed_points(), 1, 1000)
        for mode in (1, 2, True, 1.0):
            with self.subTest(policy=mode), self.assertRaises(ValueError):
                submit.submit_record(client, track, 1, mode, 1000, completion=completed)
        client.http.post.assert_not_called()

    def test_stale_diagnostics_are_not_archived_as_current(self):
        client = fake_client()
        client.http = Mock()
        track = sample_plan().data()["track"]
        completed = evaluate_completion(track, passed_points(), 1, 1000)
        changed_track = dict(track, totalTime=track["totalTime"] + 1)
        wrapper = json.dumps({"fivePointJson": json.dumps(passed_points())})
        with self.assertRaisesRegex(ValueError, "rules disagrees"):
            submit.submit_record(client, changed_track, 1, 1, 1000,
                                 five_point_json=wrapper, completion=completed)
        client.http.post.assert_not_called()
