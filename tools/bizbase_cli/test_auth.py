"""Exercise delegation-specific transport safeguards without live employee credentials."""

import io
import json
import os
import stat
import unittest
from contextlib import redirect_stderr
from email import policy
from email.parser import BytesParser
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from .auth import Client, ClientError, _RefuseRedirect, _multipart, origin


class DelegationTransportTest(unittest.TestCase):
    def test_credentials_stay_at_one_origin(self):
        self.assertEqual(origin("http://[::1]:8000/"), "http://[::1]:8000")
        self.assertEqual(origin("https://SITE.test:443/"), "https://site.test")
        for target in ("http://site.test", "https://name@site.test", "https://site.test/?key=fake", "https://site.test/foo", "https://site.test\\x"):
            with self.subTest(target=target), self.assertRaises(ClientError):
                origin(target)
        self.assertIsNone(_RefuseRedirect().redirect_request(None, None, 307, "", {}, "https://other.test/"))
        with TemporaryDirectory() as tmp, patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp}):
            client = Client("https://site.test")
            client._save("A" * 43)
            self.assertEqual(client._token(), "A" * 43)
            self.assertEqual(stat.S_IMODE(client.path.stat().st_mode), 0o600)
            with self.assertRaisesRegex(ClientError, "bizbase login"):
                Client("https://other.test")._token()

    def test_login_displays_only_public_challenge(self):
        with TemporaryDirectory() as tmp, patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp}):
            client = Client("http://127.0.0.1:8080")
            client._post = Mock(side_effect=[{}, {"token": "t" * 43}, {"user": "employee"}])
            output = io.StringIO()
            with patch("webbrowser.open"), redirect_stderr(output):
                self.assertEqual(client.login(), {"user": "employee"})
            challenge = client._post.call_args_list[0].args[1]["challenge"]
            verifier = client._post.call_args_list[1].args[1]["verifier"]
            self.assertIn(challenge[:8].upper(), output.getvalue())
            self.assertNotIn(verifier, output.getvalue())
            self.assertNotIn("t" * 43, output.getvalue())
            self.assertEqual(client._token(), "t" * 43)

    def test_http_exception_omits_sensitive_response(self):
        client = Client("https://site.test")
        error = HTTPError("https://site.test", 403, "sensitive message", {}, io.BytesIO(b"sensitive traceback"))
        client.opener.open = Mock(side_effect=error)
        with self.assertRaises(ClientError) as raised:
            client._post("api.whoami", token="token")
        self.assertEqual(raised.exception.status, 403)
        self.assertNotIn("sensitive", str(raised.exception))

    def test_multipart_binary_and_unicode_preserved(self):
        with TemporaryDirectory() as tmp:
            report = Path(tmp, "月报.zip")
            report.write_bytes(b"PK\x00\xff")
            data = io.BytesIO()
            headers = _multipart(data, {"title": "季度", "version": 3}, report)
            self.assertEqual(int(headers["Content-Length"]), len(data.getvalue()))
            msg = BytesParser(policy=policy.default).parsebytes(("Content-Type: " + headers["Content-Type"] + "\r\n\r\n").encode() + data.read())
            title, version, file = list(msg.iter_parts())
            self.assertEqual(title.get_payload(decode=True).decode(), "季度")
            self.assertEqual(json.loads(version.get_payload(decode=True)), 3)
            self.assertEqual(file.get_filename(), "月报.zip")
            self.assertEqual(file.get_payload(decode=True), b"PK\x00\xff")
