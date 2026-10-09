"""Actual CPU pixels/DPAPI/SQLite and explicit mocks; never real Vision spend."""
import asyncio, copy, json, subprocess, sys, unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
import httpx
from pydantic import ValidationError
from app.human_identity import HumanAuthRegistry, HumanAuthVerifier
from services.windows_native.tests import test_vision_frame_bridge as frame_fixture
from services.windows_native.tests.test_vision_registry import profile
from services.windows_native.tests.test_human_identity import fixture as human_fixture
from services.windows_native.vision_credentials import NativeVisionKeyVault, PrivateVisionKey
from services.windows_native.vision_registry import NativeVisionFactory
from services.windows_native.vision_frame_bridge import NativeEvidenceFrameExtractor
from services.windows_native.official_vision import NativeOfficialVision, TABLES
from services.windows_native.official_vision_models import Analyze, Action
from services.windows_native.contracts import WorkflowError, digest
from services.windows_native.store import Store
from services.windows_native.vision import NativeVision
from services.windows_native.backup import database_status


class OfficialVisionFixture:
    setUpFrames = frame_fixture.NativeVisionFrameBridgeTests.setUp
    tearDown = frame_fixture.NativeVisionFrameBridgeTests.tearDown
    payload = frame_fixture.NativeVisionFrameBridgeTests.payload
    source = frame_fixture.NativeVisionFrameBridgeTests.source
    bridge = frame_fixture.NativeVisionFrameBridgeTests.bridge

    def setUp(self):
        self.setUpFrames(); self.workspace = self.service.workspace; self.clock = [datetime.now(timezone.utc)]; self.calls = []; self.mode = None
        (self.root / '.vf-auth-workspace.json').write_text(json.dumps({'schema':'vf-native-workspace-binding-v1','workspace_id':self.workspace}))
        raw, data = human_fixture('owner',workspace=self.workspace); self.raw = raw
        self.verifier = HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400)
        self.principal = self.verifier.verify('Bearer '+raw)
        self.vault = NativeVisionKeyVault(Path(self.temp.name)/'vision-private',self.root,self.workspace)
        r = self.vault.save(PrivateVisionKey(workspace_id=self.workspace,credential_alias='explicit-vision-key',api_key='sk-explicit-synthetic-native-runtime-only'))
        self.transport = httpx.MockTransport(self.response); self.factory = NativeVisionFactory(profile(r),self.vault,operator_enabled=True,transport=self.transport)
        self.official = self.runtime(enabled=True)
        self.official.costs.set_budget(self.project['id'],self.project['revision'],'1000'); self.project = self.store.get(self.project['id'])

    def runtime(self, enabled=False, factories=None, store=None):
        vision = self.service if store is None else NativeVision(store,self.config,workspace_id=self.workspace)
        return NativeOfficialVision(vision,factories={self.factory.profile.profile_id:self.factory} if factories is None else factories,
            enabled=enabled,identity_provider=lambda:self.verifier,clock=lambda:self.clock[0])

    def request(self, **changes):
        return Analyze.model_validate({'revision':self.project['revision'],'profile_id':self.factory.profile.profile_id,
            'expected_configuration_sha256':self.factory.sha256,'observation_id':self.frames['observations'][0]['observation_id'],
            'acknowledged_external_image_analysis':True,'acknowledged_protocol_mock':True,'max_operation_cost_vnd':'500',
            'request_key':'explicit-native-vision-runtime-key',**changes})

    def create(self, **changes): return self.official.create(self.project['id'],self.request(**changes),principal=self.principal)[0]
    def process(self, row): return self.official.process(self.project['id'],row['vision_id'],Action(expected_snapshot_sha256=row['snapshot_sha256']))
    def change_owner(self, **changes):
        data = self.verifier.registry.model_dump(mode='json'); data['tokens'][self.principal.token_id].update(changes)
        self.verifier = HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400)
    def revoke(self): self.change_owner(enabled=False)
    def response(self, request):
        self.calls.append((request.method,str(request.url))); body = frame_fixture.response_payload(1)
        if self.mode == 'revoke': self.revoke()
        if self.mode == 'edit': self.store.save(self.project['id'],self.project['revision'],prompt='Explicit late project edit')
        if self.mode == 'config': self.factory.operator_enabled = False
        if self.mode == 'expired': self.clock[0] += timedelta(seconds=601)
        if self.mode == 'timeout': raise httpx.ReadTimeout('sk-private-runtime-timeout-message',request=request)
        if self.mode == 'invalid': body['output'][0]['content'][0]['text'] = 'EXPLICIT INVALID MOCK STRUCTURE'
        if self.mode == 'missing-usage': body.pop('usage')
        if self.mode == 'recover': self.official.recover()
        if self.mode == 'cancel': self.official.cancel(self.project['id'],self.pending['vision_id'],Action(expected_snapshot_sha256=self.pending['snapshot_sha256']),principal=self.principal)
        if self.mode == 'rate-limit': return httpx.Response(429,json={'error':{'code':'rate_limit'}})
        return httpx.Response(200,json=body)


class NativeOfficialVisionTests(OfficialVisionFixture,unittest.TestCase):
    def test_finite_current_owner_one_use_mock_result_cost_bound_source_and_old_session_shapes(self):
        before = self.store.get(self.project['id']); row = self.create(); self.assertEqual(row['status'],'approved'); self.assertEqual(self.calls,[])
        self.assertEqual(database_status(self.store.db)['active_operations'],0)
        done = self.process(row); self.assertEqual(done['status'],'succeeded'); self.assertEqual(len(self.calls),1)
        result = done['result']; self.assertTrue(result['mock']); self.assertFalse(result['semantic_inference_performed'])
        self.assertFalse(result['automatic_planning_eligible']); self.assertFalse(result['continuous_tracking_performed']); self.assertEqual(result['subject_tracks'],[])
        self.assertEqual(len(result['reframe_plans']),4); self.assertTrue(all(p['needs_attention'] and p['fallback']=='center_crop' for p in result['reframe_plans']))
        self.assertEqual(self.store.get(self.project['id']),before); self.assertEqual(self.process(row),done); self.assertEqual(len(self.calls),1)
        record = self.official.costs.summary(self.project['id'])['records'][0]
        self.assertEqual(record['status'],'response_received'); self.assertEqual(record['estimated_cost'],'500'); self.assertIsNone(record['actual_cost'])
        self.assertFalse(record['paid']); self.assertFalse(record['external_call']); self.assertEqual(record['receipt']['provider_response_sha256'],done['response']['response_sha256'])
        legacy,_ = self.service.create(self.project['id'],self.payload(provider_mode='official',fixture_acknowledged=False),actor='explicit-owner')
        self.assertEqual(legacy['status'],'not_configured'); self.assertIsNone(legacy['result'])

    def test_default_operator_off_never_dispatches_creates_cost_or_decrypts_on_status(self):
        disabled = self.runtime()
        with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('NO STARTUP DECRYPT')):
            self.assertFalse(disabled.states()['enabled']); row,_ = disabled.create(self.project['id'],self.request(),principal=self.principal)
        self.assertEqual(row['status'],'not_configured'); self.assertEqual(disabled.process(self.project['id'],row['vision_id'],Action(expected_snapshot_sha256=row['snapshot_sha256'])),row)
        self.assertEqual(self.calls,[]); self.assertEqual(disabled.costs.summary(self.project['id'])['records'],[])

    def test_exact_idempotency_replay_after_edit_is_historical_and_conflict_cannot_dispatch(self):
        row = self.create(); original_request = self.request(); self.store.save(self.project['id'],self.project['revision'],prompt='Later edit')
        replay,exact = self.official.create(self.project['id'],original_request,principal=self.principal); self.assertTrue(exact); self.assertEqual(replay,row)
        with self.assertRaisesRegex(WorkflowError,'IDEMPOTENCY_CONFLICT'):
            self.official.create(self.project['id'],original_request.model_copy(update={'revision':original_request.revision+1}),principal=self.principal)
        self.assertEqual(self.process(row)['status'],'failed'); self.assertEqual(self.calls,[])

    def test_two_concurrent_claims_send_once_and_keep_one_response(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            rows = list(pool.map(lambda _:self.official.create(self.project['id'],self.request(),principal=self.principal),range(2)))
        self.assertEqual(sum(not replay for _,replay in rows),1); row = rows[0][0]
        with ThreadPoolExecutor(max_workers=2) as pool: list(pool.map(lambda _:self.process(row),range(2)))
        self.assertEqual(len(self.calls),1); self.assertEqual(self.official.get(self.project['id'],row['vision_id'])['status'],'succeeded')

    def test_viewer_editor_reviewer_forged_stale_disabled_or_expired_owner_refuses(self):
        for role in ('viewer','editor','reviewer'):
            raw,data = human_fixture(role,workspace=self.workspace); verifier = HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400)
            with self.assertRaisesRegex(WorkflowError,'CURRENT_OWNER_REQUIRED'):
                self.official.create(self.project['id'],self.request(),principal=verifier.verify('Bearer '+raw))
        self.revoke()
        with self.assertRaisesRegex(WorkflowError,'CURRENT_OWNER_REQUIRED'): self.create()
        self.assertEqual(self.calls,[])

    def test_consent_bound_to_original_owner_revision_window_and_current_workspace(self):
        row = self.create(); self.change_owner(display_name='Changed identity revision')
        self.assertEqual(self.process(row)['status'],'failed'); self.assertEqual(self.calls,[])
        (self.root / '.vf-auth-workspace.json').write_text(json.dumps({'schema':'vf-native-workspace-binding-v1','workspace_id':'foreign'}))
        with self.assertRaises(WorkflowError): self.official.states()

    def test_expiry_before_claim_never_decrypts_or_dispatches_and_restart_does_not_renew(self):
        row = self.create(); deadline = row['snapshot']['deadline']; self.clock[0] += timedelta(seconds=601)
        with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('NO EXPIRED DECRYPT')):
            done = self.process(row)
        self.assertEqual(done['status'],'failed'); self.assertEqual(done['snapshot']['deadline'],deadline); self.assertEqual(self.calls,[])
        reopened = self.runtime(store=Store(self.root)); self.assertEqual(reopened.get(self.project['id'],row['vision_id']),done)

    def test_raw_acknowledgements_cost_time_ids_extra_fields_and_unchecked_models_reparse(self):
        for change in ({'revision':True},{'acknowledged_external_image_analysis':1},{'acknowledged_protocol_mock':1},
            {'valid_for_seconds':901},{'valid_for_seconds':True},{'max_operation_cost_vnd':True},{'max_operation_cost_vnd':1.5},
            {'max_operation_cost_vnd':'NaN'},{'max_operation_cost_vnd':'0'},{'endpoint':'https://untrusted.invalid'},{'api_key':'NO CLIENT SECRET'}):
            with self.assertRaises(ValidationError): self.request(**change)
        with self.assertRaises(WorkflowError): self.official.create(self.project['id'],self.request().model_copy(update={'revision':True}),principal=self.principal)
        with self.assertRaises(WorkflowError): self.create(max_operation_cost_vnd='300')
        self.assertEqual(self.calls,[])

    def test_project_budget_and_existing_paid_unknown_reservations_block_before_provider(self):
        self.official.costs.begin(project_id=self.project['id'],provider='explicit-contract',model='mock',operation='existing-reservation',request_sha256='a'*64,estimated_cost='600',paid=True,external_call=False)
        row = self.create(); self.assertEqual(row['status'],'needs_approval'); self.assertTrue(row['needs_approval'])
        self.assertEqual(self.process(row)['status'],'needs_approval'); self.assertEqual(self.calls,[])

    def test_later_parallel_cost_exposure_blocks_before_private_resolution(self):
        row = self.create()
        self.official.costs.begin(project_id=self.project['id'],provider='explicit-contract',model='mock',operation='late-reservation',request_sha256='a'*64,estimated_cost='600',paid=True,external_call=False)
        with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('NO OVERBUDGET DECRYPT')):
            done = self.process(row)
        self.assertEqual(done['status'],'needs_approval'); self.assertEqual(self.calls,[])

    def test_revocation_after_private_resolution_or_frame_decoding_never_reaches_wire(self):
        row = self.create(); original = self.vault.key
        def resolve(receipt):
            value = original(receipt); self.revoke(); return value
        with patch.object(self.vault,'key',side_effect=resolve): done = self.process(row)
        self.assertNotEqual(done['status'],'succeeded'); self.assertEqual(self.calls,[])
        self.change_owner(enabled=True)
        row = self.create(request_key='explicit-native-second-admission-key'); original_extract = NativeEvidenceFrameExtractor.extract
        async def extract(bridge,*args,**kwargs):
            value = await original_extract(bridge,*args,**kwargs); self.revoke(); return value
        with patch.object(NativeEvidenceFrameExtractor,'extract',extract): done = self.process(row)
        self.assertEqual(done['status'],'failed'); self.assertEqual(done['failure_code'],'OPENAI_VISION_DISPATCH_ADMISSION_FAILED'); self.assertEqual(self.calls,[])

    def test_known_response_usage_survives_late_owner_project_expiry_config_semantic_and_missing_usage_failures(self):
        for index, mode in enumerate(('revoke','edit','expired','config','invalid','missing-usage')):
            with self.subTest(mode=mode):
                # Restore only mutable test authority/config, never old consent or source revision.
                self.change_owner(enabled=True); self.factory.operator_enabled = True
                self.clock[0] = datetime.now(timezone.utc); self.project = self.store.get(self.project['id']); self.mode = mode
                row = self.create(request_key='explicit-late-response-key-'+str(index)); done = self.process(row)
                self.assertEqual(done['status'],'review_required'); self.assertIsNone(done['result']); self.assertIsNotNone(done['response'])
                self.assertEqual(done['response']['calculated_usage_cost_vnd'] is None,mode=='missing-usage')
                record = next(v for v in self.official.costs.summary(self.project['id'])['records'] if v['id']==done['cost_operation_id'])
                self.assertEqual(record['status'],'response_received'); self.assertIsNone(record['actual_cost'])
        self.assertEqual(len(self.calls),6)

    def test_unknown_timeout_or_rate_limit_never_retry_and_no_private_error_reflection(self):
        for index, mode in enumerate(('timeout','rate-limit')):
            self.mode = mode; row = self.create(request_key='explicit-uncertain-native-key-'+str(index)); done = self.process(row)
            self.assertIn(done['status'],('outcome_unknown','review_required')); self.assertFalse(done['automatic_retry'])
            self.assertEqual(self.process(row),done); self.assertNotIn('sk-private-runtime',json.dumps(done))
        self.assertEqual(len(self.calls),2)

    def test_cancel_during_wire_retains_known_response_but_never_result_or_second_call(self):
        self.mode = 'cancel'; self.pending = self.create(); done = self.process(self.pending)
        self.assertEqual(done['status'],'cancelled'); self.assertIsNotNone(done['response']); self.assertIsNone(done['result'])
        self.assertEqual(self.process(self.pending),done); self.assertEqual(len(self.calls),1)

    def test_interruption_during_wire_keeps_late_response_and_immutable_unknown_cost_no_replay(self):
        self.mode = 'recover'; row = self.create(); done = self.process(row)
        self.assertEqual(done['status'],'outcome_unknown'); self.assertIsNotNone(done['response']); self.assertIsNone(done['result'])
        record = self.official.costs.summary(self.project['id'])['records'][0]; self.assertEqual(record['status'],'outcome_unknown')
        self.assertEqual(self.process(row),done); self.assertEqual(len(self.calls),1)

    def test_backup_refuses_claimed_work_and_recovery_does_not_decrypt_or_call(self):
        row = self.create()
        with self.store.transaction() as con:
            con.execute("UPDATE native_official_vision_intents SET status='claimed',claim_id='nvoc_explicit_interrupt',cost_operation_id='absent-before-cost' WHERE vision_id=?",(row['vision_id'],))
        self.assertEqual(database_status(self.store.db)['active_operations'],1)
        with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('NO RECOVERY DECRYPT')):
            self.assertEqual(self.official.recover(),1)
        self.assertEqual(database_status(self.store.db)['active_operations'],0); self.assertEqual(self.calls,[])
        self.assertEqual(self.process(row)['status'],'outcome_unknown')

    def test_history_without_current_credentials_and_rehashed_mock_semantic_claim_rejected(self):
        row = self.create(); done = self.process(row); reopened = self.runtime(factories={},store=Store(self.root))
        with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('NO HISTORY DECRYPT')):
            self.assertEqual(reopened.get(self.project['id'],row['vision_id']),done)
        result = copy.deepcopy(done['result']); result['mock'] = False; result['semantic_inference_performed'] = True
        with self.store.transaction() as con:
            con.execute('UPDATE native_official_vision_intents SET result_json=?,result_sha256=? WHERE vision_id=?',(json.dumps(result),digest(result),row['vision_id']))
        with self.assertRaisesRegex(WorkflowError,'EVIDENCE_INVALID'): reopened.get(self.project['id'],row['vision_id'])

    def test_foreign_project_workspace_source_frame_corruption_and_profile_ack_fail_closed(self):
        other = self.store.create('Foreign project','','media'); row = self.create()
        with self.assertRaisesRegex(WorkflowError,'NOT_FOUND'): self.official.get(other['id'],row['vision_id'])
        with self.assertRaises(WorkflowError): self.create(acknowledged_protocol_mock=False,request_key='explicit-wrong-mock-binding-key')
        from services.windows_native.media_frame_analysis import frame_path
        frame_path(self.root,self.frames['observations'][0]['frames'][0]).write_bytes(b'EXPLICIT CORRUPT FRAME')
        self.assertEqual(self.process(row)['status'],'failed'); self.assertEqual(self.calls,[])

    def test_runtime_configuration_mutation_raw_enabled_and_import_no_gpu_or_api_framework(self):
        with self.assertRaises(WorkflowError): self.runtime(enabled=1)
        self.official.enabled = 1
        with self.assertRaises(WorkflowError): self.official.states()
        code = 'from services.windows_native.official_vision import NativeOfficialVision; import sys; assert not any(n.startswith(("fastapi","sqlalchemy","torch","vieneu")) for n in sys.modules)'
        subprocess.run([sys.executable,'-c',code],check=True,capture_output=True,timeout=30)

    def test_rehashed_cost_flags_receipt_and_request_binding_cannot_promote_mock_history(self):
        row = self.create(); done = self.process(row)
        with self.store.transaction() as con:
            original = dict(con.execute('SELECT * FROM native_cost_operations WHERE id=?',(done['cost_operation_id'],)).fetchone())
        for column, value in (('paid',1),('external_call',1),('estimated_cost','501'),('request_sha256','f'*64)):
            with self.store.transaction() as con: con.execute('UPDATE native_cost_operations SET '+column+'=? WHERE id=?',(value,done['cost_operation_id']))
            with self.assertRaisesRegex(WorkflowError,'EVIDENCE_INVALID'): self.official.get(self.project['id'],row['vision_id'])
            with self.store.transaction() as con: con.execute('UPDATE native_cost_operations SET '+column+'=? WHERE id=?',(original[column],done['cost_operation_id']))
        self.assertEqual(self.official.get(self.project['id'],row['vision_id']),done)

    def test_rehashed_result_crop_duplicate_invoice_calculated_cost_or_capability_flags_refuse(self):
        row = self.create(); done = self.process(row); original = done['result']
        for mutate in (lambda v:v.update(billing_invoice_verified=0),lambda v:v.update(calculated_usage_cost_vnd='0.000000'),
            lambda v:v.update(reframe_plans=[v['reframe_plans'][0]]*4),lambda v:v['adapter_provenance'].update(external_call=False)):
            result = copy.deepcopy(original); mutate(result)
            with self.store.transaction() as con: con.execute('UPDATE native_official_vision_intents SET result_json=?,result_sha256=? WHERE vision_id=?',(json.dumps(result),digest(result),row['vision_id']))
            with self.assertRaisesRegex(WorkflowError,'EVIDENCE_INVALID'): self.official.get(self.project['id'],row['vision_id'])

    def test_wrong_rights_publishing_claim_and_fixture_ack_cannot_be_rehashed_into_history(self):
        row = self.create(); snapshot = copy.deepcopy(row['snapshot']); snapshot['rights']['publishing_authorized'] = True
        with self.store.transaction() as con: con.execute('UPDATE native_official_vision_intents SET snapshot_json=?,snapshot_sha256=? WHERE vision_id=?',(json.dumps(snapshot),digest(snapshot),row['vision_id']))
        with self.assertRaisesRegex(WorkflowError,'EVIDENCE_INVALID'): self.official.get(self.project['id'],row['vision_id'])

    def test_actual_rights_boundary_unknown_restricted_and_fixture_never_enters_nonmock_analysis(self):
        project = self.store.get(self.project['id'])
        with self.assertRaisesRegex(WorkflowError,'RIGHTS_REVIEW_REQUIRED'): self.official.source(project,self.request(),False)
        asset = next(a for a in project['document']['assets'] if a['id']==self.source()['asset']['id'])
        asset['rights_status'] = 'restricted'
        with self.assertRaisesRegex(WorkflowError,'RIGHTS_BLOCKED'): self.official.source(project,self.request(),True)
        asset['rights_status'] = 'owned'; asset['explicit_fixture'] = True
        with self.assertRaisesRegex(WorkflowError,'RIGHTS_BLOCKED'): self.official.source(project,self.request(),False)

    def test_owner_lifetime_and_exact_snapshot_action_are_required_without_reconsent_or_dispatch(self):
        old = self.principal
        self.change_owner(expires_at=(self.clock[0]+timedelta(seconds=100)).isoformat())
        self.principal = self.verifier.verify('Bearer '+self.raw,now=self.clock[0])
        with self.assertRaisesRegex(WorkflowError,'CONSENT_EXCEEDS_IDENTITY'):
            self.create()
        self.change_owner(expires_at=old.expires_at.isoformat()); self.principal = old; row = self.create()
        with self.assertRaisesRegex(WorkflowError,'SNAPSHOT_CHANGED'):
            self.official.process(self.project['id'],row['vision_id'],Action(expected_snapshot_sha256='f'*64))
        self.assertEqual(self.calls,[])
