"""The scoped communication archive records app API payloads without auth data."""
import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests

from tests.support import IsolatedCase
from funsport.api.client import ApiClient
from funsport.run_diagnostics import RunDiagnosticArchive


class ApiClientDiagnosticTests(IsolatedCase):
    def test_call_records_plain_request_and_decrypted_business_response(self):
        client = ApiClient({"device_id": "fixture-device"}, {"uid": 42, "token": "auth-secret"})
        client.http.request = Mock(return_value=SimpleNamespace(status_code=200, content=b"ciphertext"))
        archive = RunDiagnosticArchive("api-test")
        header = SimpleNamespace(json="header-envelope", ts_ms=100, key_data=("h1", "h2"))
        body = SimpleNamespace(json="body-envelope", key_data=("b1", "b2"))
        with archive.active(), \
                patch("funsport.api.client.build_header_for", return_value=("header", [])), \
                patch("funsport.api.client.build_envelope", side_effect=[header, body]), \
                patch("funsport.api.client.derive_paes_key", return_value=b"key"), \
                patch("funsport.api.client.decrypt_response", return_value=SimpleNamespace(
                    business={"error": 10000, "data": {"received": True}, "token": "reply-secret"})):
            result = client.call("POST", "/api/fixture", '{"point":1}')

        self.assertEqual(result["error"], 10000)
        messages = json.loads((archive.directory / "communication.json").read_text(encoding="utf-8"))["messages"]
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["request"], {"point": 1})
        self.assertEqual(messages[0]["response"]["business"]["data"], {"received": True})
        serialized = json.dumps(messages)
        self.assertNotIn("auth-secret", serialized)
        self.assertNotIn("reply-secret", serialized)

    def test_transport_failure_is_recorded_with_redacted_error(self):
        client = ApiClient({"device_id": "fixture-device"}, {"uid": 42, "token": "auth-secret"})
        client.http.request = Mock(side_effect=requests.ConnectionError("token=reply-secret"))
        archive = RunDiagnosticArchive("api-error-test")
        header = SimpleNamespace(json="header-envelope", ts_ms=100, key_data=("h1", "h2"))
        body = SimpleNamespace(json="body-envelope", key_data=("b1", "b2"))
        with archive.active(), \
                patch("funsport.api.client.build_header_for", return_value=("header", [])), \
                patch("funsport.api.client.build_envelope", side_effect=[header, body]):
            with self.assertRaises(requests.ConnectionError):
                client.call("POST", "/api/fixture", '{"point":1}')

        messages = json.loads((archive.directory / "communication.json").read_text(encoding="utf-8"))["messages"]
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["request"], {"point": 1})
        self.assertIn("token=[redacted]", messages[0]["error"])
        self.assertNotIn("reply-secret", json.dumps(messages))
