"""The existing hashed human-token contract works in the pinned Native runtime."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from services.windows_native import ingestion  # Reuses the established pure-contract path.
from app.human_identity import HumanAuthRegistry, HumanAuthVerifier, InvalidHumanCredential


def fixture(role='viewer', *, workspace='wsp_native_fixture', enabled=True, issued=None, expires=None):
    now = datetime.now(timezone.utc)
    raw = 'vf1.explicit-fixture.' + 'x' * 48  # Explicit test token, never a configured credential.
    record = {'token_id': 'explicit-fixture', 'token_sha256': hashlib.sha256(raw.encode()).hexdigest(),
        'subject': 'usr:explicit-fixture', 'display_name': 'Explicit identity fixture',
        'platform_role': None, 'workspace_roles': {workspace: role},
        'issued_at': (issued or now - timedelta(minutes=1)).isoformat(),
        'expires_at': (expires or now + timedelta(hours=1)).isoformat(), 'enabled': enabled}
    return raw, {'version': 1, 'tokens': {'explicit-fixture': record}}


class NativeHumanIdentityTests(unittest.TestCase):
    def test_import_needs_no_api_framework_database_or_gpu_package(self):
        source_root = Path(__file__).resolve().parents[3]
        code = ('from services.windows_native import ingestion; import sys; '
            'from app.human_identity import HumanAuthVerifier; '
            "assert not any(name.startswith(('fastapi', 'sqlalchemy', 'torch', 'vieneu')) for name in sys.modules)")
        subprocess.run([sys.executable, '-c', code], cwd=source_root, check=True, capture_output=True, timeout=10)

    def test_existing_four_roles_bind_exact_workspace_and_honest_rank(self):
        for role in ('owner', 'editor', 'reviewer', 'viewer'):
            with self.subTest(role=role):
                raw, data = fixture(role)
                principal = HumanAuthVerifier(HumanAuthRegistry.model_validate(data), max_token_ttl_seconds=86400).verify('Bearer ' + raw)
                self.assertEqual(principal.role_for('wsp_native_fixture'), role)
                self.assertIsNone(principal.role_for('wsp_other_fixture'))
                self.assertTrue(principal.has_any_role('viewer'))
                self.assertEqual(principal.has_any_role('owner'), role == 'owner')
                self.assertNotIn(raw, repr(principal))

    def test_invalid_disabled_expired_future_and_service_tokens_reject(self):
        now = datetime.now(timezone.utc)
        for options in ({'enabled': False}, {'issued': now - timedelta(hours=2), 'expires': now - timedelta(hours=1)},
                        {'issued': now + timedelta(minutes=1), 'expires': now + timedelta(hours=1)}):
            raw, data = fixture(**options)
            verifier = HumanAuthVerifier(HumanAuthRegistry.model_validate(data), max_token_ttl_seconds=86400)
            with self.assertRaises(InvalidHumanCredential):
                verifier.verify('Bearer ' + raw)
        raw, data = fixture()
        verifier = HumanAuthVerifier(HumanAuthRegistry.model_validate(data), max_token_ttl_seconds=86400)
        for value in (None, raw, 'Bearer vf-service.fixture.' + 'x' * 48, 'Bearer vf1.missing-id.' + 'x' * 48,
                      'Bearer ' + raw + 'tampered', 'Bearer vf1.explicit-fixture.short'):
            with self.subTest(credential_shape='explicit malformed fixture'), self.assertRaises(InvalidHumanCredential):
                verifier.verify(value)

    def test_file_load_and_lifetime_schema_guards_remain_exact(self):
        raw, data = fixture()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'explicit-fixture-registry.json'
            path.write_text(json.dumps(data), encoding='utf-8')
            verifier = HumanAuthVerifier.from_file(path, max_token_ttl_seconds=86400)
            self.assertEqual(verifier.verify('Bearer ' + raw).token_id, 'explicit-fixture')
            with self.assertRaises(ValueError):
                HumanAuthVerifier.from_file(path, max_token_ttl_seconds=60)
            path.write_text('{"version":1,"tokens":{},"unexpected":true}', encoding='utf-8')
            with self.assertRaises(ValueError):
                HumanAuthVerifier.from_file(path, max_token_ttl_seconds=86400)

    def test_wildcard_and_platform_owner_follow_existing_contract(self):
        raw, data = fixture('editor', workspace='*')
        principal = HumanAuthVerifier(HumanAuthRegistry.model_validate(data), max_token_ttl_seconds=86400).verify('Bearer ' + raw)
        self.assertEqual(principal.role_for('wsp_native_fixture'), 'editor')
        data['tokens']['explicit-fixture']['platform_role'] = 'owner'
        principal = HumanAuthVerifier(HumanAuthRegistry.model_validate(data), max_token_ttl_seconds=86400).verify('Bearer ' + raw)
        self.assertEqual(principal.role_for('wsp_native_fixture'), 'owner')
