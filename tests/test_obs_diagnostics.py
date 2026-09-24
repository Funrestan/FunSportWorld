"""OBS archive entries retain provider failures without signed URL credentials."""
import json
from unittest.mock import patch

import requests

from tests.support import IsolatedCase
from funsport.api import obs
from funsport.run_diagnostics import RunDiagnosticArchive


class ObsDiagnosticTests(IsolatedCase):
    def test_put_http_failure_records_response_body_and_hides_signed_query(self):
        response = requests.Response()
        response.status_code = 403
        response._content = b"<Error>Denied token=reply-secret</Error>"
        response.url = "https://storage.example/object?X-Amz-Signature=url-secret"
        archive = RunDiagnosticArchive("obs-test")
        payload = b'{"locations":[{"lat":30.6,"lng":104.1}]}'

        with archive.active(), patch.object(obs.requests, "put", return_value=response):
            with self.assertRaises(requests.HTTPError):
                obs.put_object(response.url, payload)

        messages = json.loads((archive.directory / "communication.json").read_text(encoding="utf-8"))["messages"]
        self.assertEqual(len(messages), 1)
        message = messages[0]
        self.assertEqual(message["status"], 403)
        self.assertEqual(message["error"], "HTTP 403")
        self.assertIn("Denied", message["response"]["body"])
        self.assertIn("[redacted]", message["response"]["body"])
        self.assertEqual(message["request"]["locations"][0]["lat"], 30.6)
        serialized = json.dumps(message)
        self.assertNotIn("url-secret", serialized)
        self.assertNotIn("reply-secret", serialized)
        self.assertNotIn("X-Amz-Signature", serialized)
