"""Check CLI writes against the service contract without using a real credential."""

import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from .main import main


class ShareCommands(unittest.TestCase):
    def invoke(self, args, **kwargs):
        self.client = Mock()
        self.client.call.return_value = {"share_id": "TestReport"}
        output = io.StringIO()
        with redirect_stdout(output), patch("sys.stdin", io.StringIO(kwargs.get("stdin", ""))):
            code = main(["--site", "http://localhost", "--json", "share", *args], lambda _: self.client)
        return code, json.loads(output.getvalue())

    def test_upload_draft_only(self):
        with TemporaryDirectory() as directory:
            report = Path(directory, "private report.html")
            report.write_text("Test")
            code, reply = self.invoke(["upload", str(report), "--title", "季度报告"])
        self.assertEqual(code, 0)
        self.assertTrue(reply["success"])
        method, payload = self.client.call.call_args.args
        self.assertEqual(method, "upload")
        self.assertEqual(set(payload), {"title", "request_id"})
        self.assertEqual(self.client.call.call_args.kwargs, {"file": report})

    def test_publish_specified_preserves_retry_key(self):
        key = "ad7c4903-465d-470c-806e-9cc0c1f977be"
        code, _ = self.invoke(["publish", "TestReport", "--version", "2", "--domain", "a.test", "--access", "specified",
                               "--role", "Sales User", "--user", "one@example.test", "--request-id", key])
        self.assertEqual(code, 0)
        self.client.call.assert_called_once_with("publish", {"share_id": "TestReport", "version": 2, "domain": "a.test",
            "access_mode": "Specified", "users": ["one@example.test"], "roles": ["Sales User"], "request_id": key})

    def test_switch_version_without_changing_access(self):
        code, _ = self.invoke(["publish", "TestReport", "--version", "1", "--domain", "a.test", "--keep-access"])
        self.assertEqual(code, 0)
        self.assertEqual(self.client.call.call_args.args[1]["access_mode"], "Keep")
        self.assertNotIn("password", self.client.call.call_args.args[1])

    def test_password_read_from_stdin(self):
        code, reply = self.invoke(["publish", "TestReport", "--version", "1", "--domain", "a.test", "--access", "password",
                                   "--password-stdin"], stdin="test-value\n")
        self.assertEqual(code, 0)
        self.assertNotIn("test-value", str(reply))
        self.assertEqual(self.client.call.call_args.args[1]["password"], "test-value")

    def test_rejects_publication_with_mismatched_audience(self):
        for flags in (["--access", "public", "--user", "one@example.test"], ["--access", "specified"]):
            code, error = self.invoke(["publish", "TestReport", "--version", "1", "--domain", "a.test", *flags])
            self.assertNotEqual(code, 0)
            self.assertIn("request_id", error)
            self.client.call.assert_not_called()
