"""Protected Vision discovery and actual DPAPI synthetic keys; no real provider."""
import asyncio, copy, hashlib, json, os, subprocess, sys, tempfile, unittest, warnings
from pathlib import Path
from unittest.mock import patch
import httpx
from pydantic import ValidationError
from services.windows_native.contracts import WorkflowError, file_sha
from services.windows_native.vision_credentials import NativeVisionKeyVault, PrivateVisionKey, VisionKeyReceipt, PREFIX, ENTROPY
from services.windows_native.vision_registry import VisionProfile, VisionRegistry, NativeVisionFactory, load
from services.windows_native.tests import test_vision_frame_bridge as frames_fixture

KEY = 'sk-explicit-synthetic-vision-only-not-a-real-key'


def receipt(workspace='wsp_vision_fixture', alias='explicit-vision-key'):
    return {'reference': 'nviv_' + 'a' * 32, 'workspace_id': workspace, 'credential_alias': alias,
        'key_binding_sha256': 'b' * 64, 'cipher_sha256': 'c' * 64, 'bytes': 128}


def profile(value=None, **changes):
    return VisionProfile.model_validate({'profile_id': 'nvip_' + 'd' * 32, 'enabled': True,
        'key_receipt': receipt() if value is None else value, 'estimated_cost_vnd': '200',
        'input_vnd_per_million_tokens': '10000', 'cached_input_vnd_per_million_tokens': '1000',
        'output_vnd_per_million_tokens': '20000', **changes})


class RegistryFixture:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.folder = Path(self.temp.name).resolve()
        self.root = self.folder / 'state'; self.root.mkdir(); self.directory = self.folder / 'private'
        self.vault = NativeVisionKeyVault(self.directory, self.root, 'wsp_vision_fixture')
    def tearDown(self):
        assert self.folder.parent == Path(tempfile.gettempdir()).resolve() and self.folder == Path(self.temp.name).resolve()
        self.temp.cleanup()
    def private(self, **changes):
        return PrivateVisionKey.model_validate({'workspace_id': self.vault.workspace, 'credential_alias': 'explicit-vision-key', 'api_key': KEY, **changes})
    def save(self): return self.vault.save(self.private())
    def registry(self, p=None):
        path = self.folder / 'vision-public.json'
        path.write_text(json.dumps({'version': 1, 'workspace_id': self.vault.workspace,
            'profiles': [(profile() if p is None else p).model_dump(mode='json')]}), encoding='utf-8')
        return path


class VisionRegistryTests(RegistryFixture, unittest.TestCase):
    def test_startup_discovery_and_absent_vault_never_create_decrypt_or_authorize(self):
        path = self.registry()
        with patch('services.windows_native.assemblyai_connection._dpapi', side_effect=AssertionError('NO STARTUP DECRYPT')):
            factory = next(iter(load(path, self.vault, operator_enabled=True).values()))
            public = factory.public(); states = self.vault.states()
        self.assertEqual(public['status'], 'NOT_CONFIGURED'); self.assertFalse(public['credential_present'])
        for name in ('credential_verified', 'startup_decryption', 'provider_authorized', 'automatic_dispatch', 'publishing_enabled', 'real_provider_tested'):
            self.assertIs(public[name], False)
        self.assertFalse(states['mounted']); self.assertFalse(self.directory.exists())
        self.assertNotIn(str(self.directory), json.dumps(public))

    def test_absolute_outside_source_state_and_directory_kind_required(self):
        invalid = [self.root / 'private', Path('relative-private'), Path(__file__).resolve().parents[3] / 'private-vision']
        for directory in invalid:
            with self.subTest(directory=directory), self.assertRaises(WorkflowError): NativeVisionKeyVault(directory, self.root, 'wsp_vision_fixture')
        file = self.folder / 'file'; file.write_bytes(b'OWNED PUBLIC FILE')
        with self.assertRaises(WorkflowError): NativeVisionKeyVault(file, self.root, 'wsp_vision_fixture')
        for workspace in ('', 'foreign/../workspace', True, 'x' * 81):
            with self.assertRaises(WorkflowError): NativeVisionKeyVault(self.directory, self.root, workspace)
        with self.assertRaises(WorkflowError): NativeVisionKeyVault(self.directory, 'relative-state', 'wsp_vision_fixture')

    def test_raw_disabled_receipt_markers_and_strict_bytes(self):
        for changes in ({'key_returned': 0}, {'provider_authorized': 0}, {'publishing_enabled': 0},
            {'bytes': True}, {'bytes': 65537}, {'reference': '../unsafe'}, {'workspace_id': 'foreign'}):
            with self.subTest(changes=changes), self.assertRaises(WorkflowError): self.vault.receipt({**receipt(), **changes})

    def test_private_key_printable_bounded_and_unchecked_model_no_serializer_secret_warning(self):
        for key in ('short', KEY + '\n', KEY + ' ', 'việtnam-key', 'x' * 4097):
            with self.assertRaises(ValidationError): self.private(api_key=key)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            with self.assertRaises(WorkflowError): self.vault.save(self.private().model_copy(update={'api_key': [KEY]}))
        self.assertEqual(caught, []); self.assertNotIn(KEY, repr(self.private())); self.assertFalse(self.directory.exists())

    def test_vnd_requires_finite_explicit_bounded_decimal_without_bool_float_coercion(self):
        for value in (True, False, 1.5, 'not-a-price', 'NaN', 'Infinity', '-1', '1000000000001', '0.0000001'):
            with self.subTest(value=value), self.assertRaises(ValidationError): profile(estimated_cost_vnd=value)
        self.assertEqual(str(profile(estimated_cost_vnd='0.000001').estimated_cost_vnd), '0.000001')

    def test_registry_unique_profiles_alias_workspace_schema_and_duplicate_json(self):
        p = profile().model_dump(mode='json'); data = {'version': 1, 'workspace_id': self.vault.workspace, 'profiles': [p]}
        for changes in ({'version': True}, {'version': 2}, {'profiles': [p, p]}, {'profiles': [p] * 9}, {'workspace_id': 'foreign'}):
            with self.assertRaises(ValidationError): VisionRegistry.model_validate({**data, **changes})
        path = self.registry(); path.write_bytes(b'{"version":1,"version":1,"workspace_id":"wsp_vision_fixture","profiles":[]}')
        with self.assertRaisesRegex(WorkflowError, 'REGISTRY_INVALID'): load(path, self.vault)
        for raw in (b'', b' ' * 262145, b'[]', b'null'):
            path.write_bytes(raw)
            with self.assertRaisesRegex(WorkflowError, 'REGISTRY_INVALID'): load(path, self.vault)

    def test_raw_operator_and_explicit_exact_mock_only_transport(self):
        for value in (0, 1, 'true', None):
            with self.assertRaises(WorkflowError): NativeVisionFactory(profile(), self.vault, operator_enabled=value)
            with self.assertRaises(WorkflowError): load(self.registry(), self.vault, operator_enabled=value)
        for transport in (httpx.AsyncHTTPTransport(), object()):
            with self.assertRaises(WorkflowError): NativeVisionFactory(profile(), self.vault, transport=transport)

    def test_frozen_public_profile_operator_mock_vault_and_checksum_cannot_change(self):
        mutations = [lambda f: setattr(f, 'operator_enabled', 1), lambda f: setattr(f, 'mock', 0),
            lambda f: setattr(f, 'transport', httpx.MockTransport(lambda _: httpx.Response(200))),
            lambda f: setattr(f, 'sha256', 'e' * 64), lambda f: setattr(f, 'workspace', 'foreign'),
            lambda f: setattr(f.profile, 'enabled', False), lambda f: setattr(f.profile, 'estimated_cost_vnd', '500')]
        for mutate in mutations:
            factory = NativeVisionFactory(profile(), self.vault, operator_enabled=True); mutate(factory)
            with self.assertRaisesRegex(WorkflowError, 'FACTORY_CONFIGURATION_CHANGED'): factory.public()
        self.vault.workspace = 'foreign'
        with self.assertRaises(WorkflowError): self.vault.states()

    def test_registry_drift_or_hardlink_refuses_without_private_read(self):
        path = self.registry(); factory = next(iter(load(path, self.vault).values()))
        path.write_text(path.read_text() + '\n')
        with self.assertRaisesRegex(WorkflowError, 'FACTORY_CONFIGURATION_CHANGED'): factory.public()
        os.link(path, self.folder / 'owned-public-hardlink')
        with self.assertRaises(WorkflowError): load(path, self.vault)

    def test_unchecked_profile_reparsed_and_deep_copied(self):
        p = profile(); factory = NativeVisionFactory(p, self.vault); p.enabled = False
        self.assertTrue(factory.public()['profile']['enabled'])
        with self.assertRaisesRegex(WorkflowError, 'FACTORY_CONFIGURATION_CHANGED'):
            NativeVisionFactory(profile().model_copy(update={'enabled': 1}), self.vault)

    def test_import_has_no_api_framework_database_or_gpu_dependency(self):
        code = 'from services.windows_native.vision_registry import load; import sys; assert not any(n.startswith(("fastapi","sqlalchemy","torch","vieneu")) for n in sys.modules)'
        subprocess.run([sys.executable, '-c', code], check=True, capture_output=True, timeout=30)


@unittest.skipUnless(os.name == 'nt', 'Actual Windows DPAPI required')
class VisionKeyDPAPITests(RegistryFixture, unittest.TestCase):
    def test_actual_dpapi_current_user_system_acl_before_bytes_and_public_receipt_no_secret(self):
        from services.windows_native.assemblyai_connection import _restrict_file
        def restrict(path):
            self.assertEqual(path.stat().st_size, 0); return _restrict_file(path)
        with patch('services.windows_native.assemblyai_connection._restrict_file', side_effect=restrict) as restricted:
            r = self.save()
        self.assertEqual(restricted.call_count, 1); raw = self.vault.path(r['reference']).read_bytes()
        self.assertTrue(raw.startswith(PREFIX)); self.assertNotIn(KEY.encode(), raw)
        self.assertNotIn(KEY, json.dumps(r)); self.assertEqual(self.vault.key(r), KEY)
        with patch('services.windows_native.assemblyai_connection._dpapi', side_effect=AssertionError('NO DISCOVERY DECRYPT')):
            self.assertTrue(self.vault.present(r)); self.assertTrue(self.vault.states()['mounted'])

    def test_new_immutable_generation_preserves_original_and_hash_binding(self):
        r = self.save(); raw = self.vault.path(r['reference']).read_bytes(); new = self.save()
        self.assertNotEqual(r['reference'], new['reference']); self.assertEqual(r['key_binding_sha256'], new['key_binding_sha256'])
        self.assertEqual(self.vault.path(r['reference']).read_bytes(), raw); self.assertEqual(self.vault.key(new), KEY)

    def test_atomic_destination_collision_does_not_replace_original(self):
        r = self.save(); raw = self.vault.path(r['reference']).read_bytes()
        from types import SimpleNamespace
        with patch('services.windows_native.vision_credentials.uuid.uuid4', return_value=SimpleNamespace(hex=r['reference'][5:])):
            with self.assertRaisesRegex(WorkflowError, 'ALREADY_SAVED'): self.save()
        self.assertEqual(self.vault.path(r['reference']).read_bytes(), raw)
        self.assertEqual(list(self.directory.glob('*.part')), [])

    def test_cipher_hash_size_prefix_and_hardlink_refuse_before_decrypt(self):
        r = self.save(); path = self.vault.path(r['reference']); raw = path.read_bytes()
        with patch('services.windows_native.assemblyai_connection._dpapi', side_effect=AssertionError('NO TAMPER DECRYPT')):
            for bad in (raw[:-1], b'WRONG PREFIX' + raw, raw[:-1] + bytes([raw[-1] ^ 1])):
                path.write_bytes(bad)
                with self.assertRaises(WorkflowError): self.vault.key(r)
            path.write_bytes(raw); linked = self.folder / 'owned-key-hardlink'; os.link(path, linked)
            with self.assertRaises(WorkflowError): self.vault.key(r)
            linked.unlink()
        self.assertEqual(self.vault.key(r), KEY)

    def test_resealed_outer_inner_extra_duplicate_and_domain_cannot_pass_binding(self):
        from services.windows_native.assemblyai_connection import _dpapi
        r = self.save(); path = self.vault.path(r['reference']); raw = path.read_bytes()
        value = json.loads(_dpapi(raw[len(PREFIX):], decrypt=True, entropy=ENTROPY + self.vault.workspace.encode()))
        for mutate in (lambda v: v.update(reference='nviv_' + 'f' * 32), lambda v: v['value'].update(api_key=KEY + '-changed'),
            lambda v: v['value'].update(workspace_id='foreign'), lambda v: v.update(extra=True)):
            changed = copy.deepcopy(value); mutate(changed)
            path.write_bytes(PREFIX + _dpapi(json.dumps(changed).encode(), entropy=ENTROPY + self.vault.workspace.encode()))
            bad = {**r, 'cipher_sha256': file_sha(path), 'bytes': path.stat().st_size}
            with self.assertRaisesRegex(WorkflowError, 'PRIVATE_KEY_UNAVAILABLE'): self.vault.key(bad)
        for text, entropy in ((json.dumps(value).replace('{', '{"schema_version":"duplicate",', 1), ENTROPY + self.vault.workspace.encode()),
            (json.dumps(value), b'FOREIGN DEDICATED ENTROPY')):
            path.write_bytes(PREFIX + _dpapi(text.encode(), entropy=entropy))
            with self.assertRaisesRegex(WorkflowError, 'PRIVATE_KEY_UNAVAILABLE'):
                self.vault.key({**r, 'cipher_sha256': file_sha(path), 'bytes': path.stat().st_size})

    def test_receipt_workspace_alias_key_digest_and_reference_cannot_rebind(self):
        r = self.save()
        for change in ({'workspace_id': 'foreign'}, {'credential_alias': 'foreign-key'}, {'key_binding_sha256': 'e' * 64},
            {'reference': 'nviv_' + 'f' * 32}):
            with self.assertRaises(WorkflowError): self.vault.key({**r, **change})
        self.assertEqual(self.vault.key(r), KEY)

    def test_positive_live_envelope_and_separate_operator_required_without_decrypt(self):
        r = self.save(); p = profile(r); path = self.registry(p)
        with patch('services.windows_native.assemblyai_connection._dpapi', side_effect=AssertionError('NO CONFIG DECRYPT')):
            self.assertEqual(next(iter(load(path, self.vault).values())).public()['status'], 'NOT_CONFIGURED')
            self.assertEqual(next(iter(load(path, self.vault, operator_enabled=True).values())).public()['status'], 'CONFIGURED')
            for field in ('estimated_cost_vnd', 'input_vnd_per_million_tokens', 'output_vnd_per_million_tokens'):
                f = NativeVisionFactory(profile(r, **{field: '0'}), self.vault, operator_enabled=True)
                self.assertEqual(f.public()['status'], 'NOT_CONFIGURED')
            self.assertEqual(NativeVisionFactory(profile(r, enabled=False), self.vault, operator_enabled=True).public()['status'], 'NOT_CONFIGURED')


class VisionRegistryFrameTests(unittest.TestCase):
    setUp = frames_fixture.NativeVisionFrameBridgeTests.setUp
    tearDown = frames_fixture.NativeVisionFrameBridgeTests.tearDown
    payload = frames_fixture.NativeVisionFrameBridgeTests.payload
    source = frames_fixture.NativeVisionFrameBridgeTests.source
    bridge = frames_fixture.NativeVisionFrameBridgeTests.bridge

    def factory(self, transport):
        vault = NativeVisionKeyVault(Path(self.temp.name) / 'private-vision', self.root, 'wsp_vision_fixture')
        r = vault.save(PrivateVisionKey(workspace_id=vault.workspace, credential_alias='explicit-vision-key', api_key=KEY))
        return NativeVisionFactory(profile(r), vault, operator_enabled=True, transport=transport)

    def test_exact_factory_protected_key_and_native_png_enter_shared_mock_adapter_without_runtime_mutation(self):
        bridge = self.bridge(); before = self.store.get(self.project['id']); calls = []; observations = []
        def handler(request):
            self.assertEqual(request.headers['Authorization'], 'Bearer ' + KEY); calls.append(request.method)
            return httpx.Response(200, json=frames_fixture.response_payload(1))
        factory = self.factory(httpx.MockTransport(handler))
        with patch('services.windows_native.assemblyai_connection._dpapi', side_effect=AssertionError('NO CONSTRUCTOR DECRYPT')):
            provider = factory.provider(bridge, response_observer=observations.append); self.assertEqual(factory.public()['status'], 'CONFIGURED')
        self.assertEqual(calls, [])
        from services.windows_native.media_frame_analysis import checked_path
        result = asyncio.run(provider.analyze(checked_path(self.config, bridge.source['asset']), metadata=bridge.input_metadata(),
            scenes=[], asset_id=bridge.source['asset']['id'], checksum_sha256=bridge.source['asset']['sha256'], sample_interval_seconds=1))
        self.assertEqual(calls, ['POST']); self.assertTrue(result.provenance['mock_tested'])
        self.assertEqual(len(observations), 1); self.assertEqual(observations[0].response_sha256, result.provenance['response_sha256'])
        self.assertFalse(result.provenance['real_provider_tested']); self.assertEqual(result.frames[0].evidence_frame_reference, bridge.binding()['source_frame_evidence'][0]['reference'])
        self.assertEqual(self.store.get(self.project['id']), before)
        row, _ = self.service.create(self.project['id'], self.payload(provider_mode='official', fixture_acknowledged=False), actor='fixture-owner')
        self.assertEqual(row['status'], 'not_configured'); self.assertIsNone(row['result'])

    def test_factory_source_root_and_extractor_shape_refuse_without_wire(self):
        factory = self.factory(httpx.MockTransport(lambda _: self.fail('NO WIRE')))
        with self.assertRaisesRegex(WorkflowError, 'PROVIDER_INPUT_INVALID'): factory.provider(object())
        bridge = self.bridge(); bridge.root = self.root / 'foreign'
        with self.assertRaises(WorkflowError): factory.provider(bridge)

    def test_late_factory_drift_before_key_or_wire_and_live_zero_budget_before_frames(self):
        factory = self.factory(httpx.MockTransport(lambda _: self.fail('NO WIRE'))); bridge = self.bridge(); provider = factory.provider(bridge)
        factory.operator_enabled = False
        from services.windows_native.media_frame_analysis import checked_path
        with patch('services.windows_native.assemblyai_connection._dpapi', side_effect=AssertionError('NO LATE KEY DECRYPT')):
            with self.assertRaises(WorkflowError):
                asyncio.run(provider.analyze(checked_path(self.config, bridge.source['asset']), metadata=bridge.input_metadata(),
                    scenes=[], asset_id=bridge.source['asset']['id'], checksum_sha256=bridge.source['asset']['sha256'], sample_interval_seconds=1))
            zero = NativeVisionFactory(profile(factory.profile.key_receipt.model_dump(mode='json'), estimated_cost_vnd='0'), factory.vault, operator_enabled=True)
            with patch.object(bridge, 'binding', side_effect=AssertionError('NO ZERO BUDGET FRAMES')):
                with self.assertRaisesRegex(WorkflowError, 'NOT_CONFIGURED'): zero.provider(bridge)
