"""Opt-in local archive for checkpoint and upload diagnostics."""
import json
import logging

from tests.support import IsolatedCase
from funsport.run_diagnostics import RunDiagnosticArchive


class RunDiagnosticTests(IsolatedCase):
    def test_archive_saves_checkpoint_message_and_redacted_upload_data(self):
        points = [{"id": 7, "position": 0, "isPass": False}]
        raw_message = json.dumps({
            "useZip": False,
            "fivePointJson": json.dumps(points, separators=(",", ":")),
        }, separators=(",", ":"))
        archive = RunDiagnosticArchive("plan-123")
        archive.capture_plan({
            "policy": 1,
            "track": {"locations": [{"lat": 30.6, "lng": 104.1}]},
            "points": points,
            "route": {"provider": "fixture"},
            "checkpoint_distances": [1.2],
            "checkpoint_order": {"source": "fixture"},
            "five_point_json": raw_message,
        }, "plan-123")
        archive.capture("submit_body.json", {
            "signature": "signature-secret",
            "originalSign": "original-sign-secret",
            "accessToken": "access-token-secret",
            "deviceId": "device-secret",
            "amapKey": "amap-key-secret",
            "phoneNumber": 13800138000,
            "uid": 123,
            "fivePointJson": raw_message,
        })
        archive.record_message("api", "POST", "/api/test", request={"key": "amap-secret"},
                               response={"signedUrl": "https://example.invalid/object?token=secret"},
                               status=200)
        archive.record_message("obs-upload", "PUT", "bucket/object",
                               error="request failed for url: /bucket/object?X-Amz-Signature=relative-secret")

        logger = logging.getLogger("funsport")
        handler = archive.attach(logger)
        try:
            logger.info("unrelated token=other-secret")
            with archive.active():
                logger.info("test token=local-secret")
        finally:
            logger.removeHandler(handler)

        self.assertEqual(archive.directory.parent, self.data / "data" / "run-diagnostics")
        message = json.loads((archive.directory / "checkpoint_message.json").read_text(encoding="utf-8"))
        self.assertEqual(message["points"], points)
        body_text = (archive.directory / "submit_body.json").read_text(encoding="utf-8")
        self.assertNotIn("signature-secret", body_text)
        self.assertNotIn("original-sign-secret", body_text)
        self.assertNotIn("access-token-secret", body_text)
        self.assertNotIn("device-secret", body_text)
        self.assertNotIn("amap-key-secret", body_text)
        self.assertNotIn("13800138000", body_text)
        journal_text = (archive.directory / "communication.json").read_text(encoding="utf-8")
        self.assertNotIn("amap-secret", journal_text)
        self.assertNotIn("token=secret", journal_text)
        self.assertNotIn("relative-secret", journal_text)
        run_log = (archive.directory / "run.log").read_text(encoding="utf-8")
        self.assertIn("token=[redacted]", run_log)
        self.assertNotIn("other-secret", run_log)

        reopened = RunDiagnosticArchive.open_existing(archive.directory)
        reopened.record_message("app-api", "GET", "/api/next", response={"error": 10000})
        messages = json.loads((archive.directory / "communication.json").read_text(encoding="utf-8"))["messages"]
        self.assertEqual(len(messages), 3)

    def test_reopen_rejects_missing_archive_directory(self):
        missing = self.data / "data" / "run-diagnostics" / "missing"
        with self.assertRaises(ValueError):
            RunDiagnosticArchive.open_existing(missing)

    def test_reopen_rejects_invalid_journal_without_overwriting_it(self):
        archive = RunDiagnosticArchive("corrupt-test")
        journal = archive.directory / "communication.json"
        journal.write_text("not json\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            RunDiagnosticArchive.open_existing(archive.directory)
        self.assertEqual(journal.read_text(encoding="utf-8"), "not json\n")
