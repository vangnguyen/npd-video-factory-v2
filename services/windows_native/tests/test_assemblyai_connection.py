"""Local credential security and connection boundaries; never real ASR evidence."""
import http.client
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

from services.windows_native import assemblyai_connection as connection
from services.windows_native.contracts import WorkflowError
from services.windows_native.pipeline import Config
from services.windows_native.server import LocalServer

KEY = "FIXTURE_ASSEMBLYAI_NOT_A_REAL_KEY_123"
CHECKS = {"verification_http_calls": 1, "transcription_calls": 0, "audio_uploaded": False}


class ConnectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = Config(data_root=self.root / "data", assemblyai_secret_file=self.root / "secrets/assemblyai.dpapi")
        self.config.data_root.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def test_real_windows_dpapi_roundtrip_protected_acl_and_restart_status(self):
        with patch.object(connection, "verify_credential", return_value=CHECKS) as verify:
            result = connection.connect(self.config, KEY)
            verify.assert_called_once_with(KEY)
        path = self.config.assemblyai_secret_file
        self.assertNotIn(KEY.encode(), path.read_bytes())
        self.assertTrue(path.read_bytes().startswith(connection.PREFIX))
        self.assertEqual(connection.load_credential(self.config), KEY)
        self.assertTrue(result["connected"])
        self.assertEqual(result["transcription_calls"], 0)
        (self.root / "config.json").write_text(json.dumps(self.config.dump()))
        fresh = Config.load(self.root / "config.json")
        self.assertTrue(connection.status(fresh)["connected"])
        receipt = (self.config.data_root / "assemblyai-connection.json").read_text()
        self.assertNotIn(KEY, receipt)
        task_acl_script = "& { param($taskPath) $taskAcl=[System.IO.File]::GetAccessControl($taskPath); $taskUser=[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value; $taskSids=@($taskAcl.Access | ForEach-Object {$_.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value}); if (-not $taskAcl.AreAccessRulesProtected -or $taskSids.Count -ne 2 -or $taskSids -notcontains $taskUser -or $taskSids -notcontains 'S-1-5-18') { throw 'ACL mismatch' }; 'ACL_PASS' } '" + str(path).replace("'", "''") + "'"
        checked = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", task_acl_script], capture_output=True, text=True, timeout=20)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertIn("ACL_PASS", checked.stdout)

    def test_no_plaintext_fallback_no_overwrite_and_cipher_tamper_invalidates_status(self):
        with patch.object(connection, "verify_credential", return_value=CHECKS):
            connection.connect(self.config, KEY)
        before = self.config.assemblyai_secret_file.read_bytes()
        with patch.object(connection, "verify_credential") as verify:
            with self.assertRaisesRegex(WorkflowError, "ALREADY_SAVED"):
                connection.connect(self.config, KEY + "DIFFERENT")
            verify.assert_not_called()
        self.assertEqual(self.config.assemblyai_secret_file.read_bytes(), before)
        self.config.assemblyai_secret_file.write_bytes(b"ASSEMBLYAI_API_KEY=" + KEY.encode())
        self.assertFalse(connection.status(self.config)["connected"])
        with self.assertRaisesRegex(WorkflowError, "CREDENTIAL_UNAVAILABLE"):
            connection.load_credential(self.config)

    def test_invalid_key_or_secret_path_makes_no_request(self):
        with patch.object(connection, "verify_credential") as verify:
            for key in (None, "short", KEY + "\r\nInjected: yes", 123):
                with self.assertRaises(WorkflowError): connection.connect(self.config, key)
            self.config.assemblyai_secret_file = self.config.data_root / "key.dpapi"
            with self.assertRaisesRegex(WorkflowError, "OUTSIDE_REPO"):
                connection.connect(self.config, KEY)
            verify.assert_not_called()

    def test_verification_is_one_read_only_stream_and_never_decodes_account_data(self):
        with patch("httpx2.Client") as client:
            response = client.return_value.__enter__.return_value.stream.return_value.__enter__.return_value
            response.status_code = 200
            self.assertEqual(connection.verify_credential(KEY), CHECKS)
            client.assert_called_once()
            self.assertFalse(client.call_args.kwargs["trust_env"])
            self.assertFalse(client.call_args.kwargs["follow_redirects"])
            client.return_value.__enter__.return_value.stream.assert_called_once_with("GET", connection.VERIFY_URL, headers={"authorization": KEY})
            response.json.assert_not_called(); response.read.assert_not_called()

    def test_failed_saved_key_recheck_revokes_connected_status_without_changing_cipher(self):
        with patch.object(connection, "verify_credential", return_value=CHECKS):
            connection.connect(self.config, KEY)
        cipher = self.config.assemblyai_secret_file.read_bytes()
        with patch.object(connection, "verify_credential", side_effect=WorkflowError("ASSEMBLYAI_AUTHENTICATION_FAILED", 400)):
            with self.assertRaisesRegex(WorkflowError, "AUTHENTICATION_FAILED"):
                connection.connect(self.config)
        self.assertFalse(connection.status(self.config)["connected"])
        self.assertTrue(connection.status(self.config)["credential_saved"])
        self.assertEqual(self.config.assemblyai_secret_file.read_bytes(), cipher)

    def test_auth_network_and_rate_limit_errors_are_redacted_and_not_saved(self):
        for http_status, code in ((401, "AUTHENTICATION_FAILED"), (403, "AUTHENTICATION_FAILED"), (429, "RATE_LIMITED"), (500, "CHECK_FAILED"), (302, "CHECK_FAILED")):
            with patch("httpx2.Client") as client:
                client.return_value.__enter__.return_value.stream.return_value.__enter__.return_value.status_code = http_status
                with self.assertRaisesRegex(WorkflowError, code): connection.connect(self.config, KEY)
            self.assertFalse(self.config.assemblyai_secret_file.exists())
        with patch("httpx2.Client", side_effect=RuntimeError(KEY)):
            with self.assertRaises(WorkflowError) as raised: connection.connect(self.config, KEY)
        self.assertNotIn(KEY, str(raised.exception))
        self.assertFalse((self.config.data_root / "assemblyai-connection.json").exists())


class ConnectionHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = Config(data_root=self.root / "data", assemblyai_secret_file=self.root / "secrets/assemblyai.dpapi")
        self.server = LocalServer(0, self.config, start_worker=False)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        self.temp.cleanup()

    def request(self, method, body=None, headers=None, path="/api/connections/assemblyai"):
        client = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=20)
        options = {"Content-Type": "application/json", "Cookie": "vf_native_session=" + self.server.session,
                   "X-VF-CSRF": self.server.csrf, **(headers or {})}
        client.request(method, path, json.dumps(body) if body is not None else None, options)
        response = client.getresponse(); raw = response.read(); status = response.status; client.close()
        return status, raw

    def test_secret_endpoint_is_session_origin_csrf_protected_and_size_bounded(self):
        with patch.object(connection, "verify_credential") as verify:
            for headers, expected in (({"Cookie": ""}, 401), ({"X-VF-CSRF": "wrong"}, 403),
                                      ({"Origin": "https://evil.test"}, 403), ({"Sec-Fetch-Site": "cross-site"}, 403)):
                self.assertEqual(self.request("POST", {"key": KEY}, headers)[0], expected)
            self.assertEqual(self.request("GET", headers={"Cookie": ""})[0], 401)
            self.assertEqual(self.request("POST", {"key": "x" * 2050})[0], 400)
            self.assertEqual(self.request("POST", {"key": KEY, "extra": True})[0], 400)
            self.assertEqual(self.request("POST", {"key": None})[0], 400)
            verify.assert_not_called()

    def test_connect_get_and_saved_key_recheck_never_return_secret_or_edit_project(self):
        p = self.server.store.create("Preserved", "Owner prompt")
        before = self.server.store.get(p["id"])
        with patch.object(connection, "verify_credential", return_value=CHECKS) as verify:
            code, raw = self.request("POST", {"key": KEY})
            self.assertEqual(code, 200); self.assertTrue(json.loads(raw)["connected"])
            self.assertNotIn(KEY.encode(), raw)
            code, raw = self.request("GET")
            self.assertEqual(code, 200); self.assertTrue(json.loads(raw)["connected"])
            self.assertNotIn(KEY.encode(), raw)
            self.assertEqual(self.request("POST", {"verify_saved": True})[0], 200)
            self.assertEqual(verify.call_count, 2)
        self.assertEqual(self.server.store.get(p["id"]), before)
        self.assertEqual(self.request("GET", path="/settings/assemblyai")[0], 200)
        self.assertEqual(self.request("GET", path="/../secrets/assemblyai.dpapi")[0], 404)

    def test_busy_job_prevents_credential_change(self):
        p = self.server.store.create("Busy", "Prompt")
        self.server.store.enqueue(p["id"], p["revision"], "content", "fixture-key-busy-123")
        with patch.object(connection, "verify_credential") as verify:
            self.assertEqual(self.request("POST", {"key": KEY})[0], 409)
            verify.assert_not_called()
