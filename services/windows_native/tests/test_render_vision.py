"""Real rendered PNGs, protected synthetic keys and one-use HTTP protocol mocks."""
import copy,json,shutil,tempfile,unittest,uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
import httpx
from pydantic import ValidationError
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
from services.windows_native.tests import test_source_render as source_fixture
from services.windows_native.tests.test_human_identity import fixture as human_fixture
from services.windows_native.tests.test_render_vision_registry import profile
from services.windows_native.tests.test_vision_frame_bridge import response_payload
from services.windows_native.backup import database_status,create_backup
from services.windows_native.contracts import WorkflowError,digest
from services.windows_native.costs import CostLedger
from services.windows_native.pipeline import Pipeline
from services.windows_native.server import Runner
from services.windows_native.shot_preview import PreviewManager
from services.windows_native.store import Store
from services.windows_native.render_vision import NativeRenderVision,TABLES
from services.windows_native.render_vision_models import RenderAnalyze,RenderAction
from services.windows_native.render_vision_registry import NativeRenderVisionFactory
from services.windows_native.render_vision_frame_bridge import NativeRenderEvidenceFrameExtractor
from services.windows_native.vision_credentials import NativeVisionKeyVault,PrivateVisionKey


class NativeRenderVisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Build one real render, then isolate every test in an exact cold copy.
        cls.original=source_fixture.NativeSourceRenderTests('test_real_source_worker_qc_checkpoint_keeps_media_immutable_and_requires_final_review')
        cls.original.setUp();f=cls.original;f.real_source();f.config.secret_file=f.root/'absent-key';f.config.assemblyai_secret_file=f.root/'absent-asr'
        CostLedger(f.store).set_budget(f.project['id'],f.project['revision'],'1000');f.project=f.store.get(f.project['id'])
        manager=PreviewManager(f.config,f.store)
        try:
            manager.generate(f.project['id'],f.project['revision']);assert f.wait(manager)['status']=='READY'
        finally:manager.close()
        f.project=f.store.approve(f.project['id'],f.project['revision'],'EXPLICIT SYNTHETIC RENDER REVIEW — NOT OWNER UAT',True)
        job=f.store.enqueue(f.project['id'],f.project['revision'],'render',uuid.uuid4().hex)
        assert Runner(f.store,Pipeline(f.config)).run_one();cls.original_job=f.store.get_job(job['id']);assert cls.original_job['status']=='succeeded'

    @classmethod
    def tearDownClass(cls):cls.original.tearDown()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'state';shutil.copytree(self.original.root,self.root)
        self.store=Store(self.root);self.config=replace(self.original.config,data_root=self.root,
            secret_file=Path(self.temp.name)/'absent-provider'/'openai.env',assemblyai_secret_file=Path(self.temp.name)/'absent-provider'/'asr.dpapi')
        self.workspace='wsp_native_local';self.project=self.store.get(self.original.project['id']);self.job=self.store.get_job(self.original_job['id'])
        self.clock=[datetime.now(timezone.utc)];self.calls=[];self.mode=None
        raw,data=human_fixture('owner',workspace=self.workspace);self.verifier=HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400)
        self.principal=self.verifier.verify('Bearer '+raw)
        self.vault=NativeVisionKeyVault(Path(self.temp.name)/'private',self.root,self.workspace)
        receipt=self.vault.save(PrivateVisionKey(workspace_id=self.workspace,credential_alias='explicit-render-vision-key',api_key='sk-explicit-synthetic-render-controller-not-real'))
        self.factory=NativeRenderVisionFactory(profile(receipt),self.vault,operator_enabled=True,transport=httpx.MockTransport(self.response))
        self.service=self.runtime(enabled=True)

    def tearDown(self):self.temp.cleanup()
    def runtime(self,**changes):
        return NativeRenderVision(self.store,self.config,workspace_id=self.workspace,factories={self.factory.profile.profile_id:self.factory},
            identity_provider=lambda:self.verifier,clock=lambda:self.clock[0],**changes)
    def bridge(self):return NativeRenderEvidenceFrameExtractor(self.store,self.config,self.project['id'],self.job['id'],workspace_id=self.workspace)
    def request(self,**changes):
        return RenderAnalyze.model_validate({'revision':self.project['revision'],'render_job_id':self.job['id'],'profile_id':self.factory.profile.profile_id,
            'expected_configuration_sha256':self.factory.sha256,'expected_render_input_sha256':digest(self.bridge().binding()),
            'acknowledged_rendered_frame_analysis':True,'acknowledged_protocol_mock':True,'max_operation_cost_vnd':'500',
            'request_key':'explicit-render-vision-controller-key',**changes})
    def create(self,**changes):return self.service.create(self.project['id'],self.request(**changes),principal=self.principal)[0]
    def action(self,row):return RenderAction(expected_snapshot_sha256=row['snapshot_sha256'])
    def process(self,row):return self.service.process(self.project['id'],row['vision_id'],self.action(row))
    def change_owner(self,**changes):
        data=self.verifier.registry.model_dump(mode='json');data['tokens'][self.principal.token_id].update(changes)
        self.verifier=HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400)
    def response(self,request):
        self.calls.append((request.method,str(request.url)));body=response_payload(8)
        if self.mode=='revoke':self.change_owner(enabled=False)
        if self.mode=='edit':self.store.save(self.project['id'],self.project['revision'],prompt='EXPLICIT LATE DOCUMENT CHANGE')
        if self.mode=='expired':self.clock[0]+=timedelta(seconds=601)
        if self.mode=='config':self.factory.operator_enabled=False
        if self.mode=='cancel':self.service.cancel(self.project['id'],self.pending['vision_id'],self.action(self.pending),principal=self.principal)
        if self.mode=='recover':self.service.recover()
        if self.mode=='timeout':raise httpx.ReadTimeout('sk-private-must-not-enter-journal',request=request)
        if self.mode=='invalid':body['output'][0]['content'][0]['text']='EXPLICIT INVALID RESPONSE'
        if self.mode=='missing-usage':body.pop('usage')
        if self.mode=='over-ceiling':body['usage'].update(input_tokens=1000000)
        if self.mode=='rate-limit':return httpx.Response(429,json={'error':{'code':'rate_limit'}})
        return httpx.Response(200,json=body)

    def test_finite_owner_one_use_response_cost_actual_frame_binding_no_project_mutation(self):
        before=self.store.get(self.project['id']);row=self.create();self.assertEqual(row['status'],'approved');self.assertEqual(self.calls,[])
        done=self.process(row);self.assertEqual(done['status'],'succeeded',done['failure_code']);self.assertEqual(len(self.calls),1)
        self.assertEqual(self.process(row),done);self.assertEqual(len(self.calls),1);self.assertEqual(self.store.get(self.project['id']),before)
        self.assertEqual(len(done['result']['frames']),8);self.assertFalse(done['result']['semantic_inference_performed'])
        self.assertTrue(done['result']['decoded_render_pts_verified']);self.assertFalse(done['result']['hard_qc_replaced'])
        self.assertEqual(done['result']['rendered_video_sha256'],self.job['result']['qc']['final_sha256'])
        record=self.service.costs.summary(self.project['id'])['records'][0];self.assertEqual(record['job_id'],self.job['id'])
        self.assertEqual(record['status'],'response_received');self.assertIsNone(record['actual_cost']);self.assertFalse(record['paid']);self.assertFalse(record['external_call'])
        self.assertEqual(record['receipt']['provider_response_sha256'],done['response']['response_sha256'])

    def test_default_disabled_creates_no_cost_decrypt_or_automatic_dispatch(self):
        service=self.runtime()
        with patch.object(self.vault,'key',side_effect=AssertionError('NO DEFAULT KEY READ')):
            self.assertFalse(service.states()['enabled']);row,_=service.create(self.project['id'],self.request(),principal=self.principal)
            self.assertEqual(row['status'],'not_configured');self.assertEqual(service.process(self.project['id'],row['vision_id'],self.action(row)),row)
        self.assertEqual(self.calls,[]);self.assertEqual(service.costs.summary(self.project['id'])['records'],[])

    def test_concurrent_consent_and_dispatch_send_exactly_once(self):
        request=self.request()
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(lambda _:self.service.create(self.project['id'],request,principal=self.principal),range(2)))
        self.assertEqual(sum(not replay for _,replay in rows),1);row=rows[0][0]
        with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda _:self.process(row),range(2)))
        self.assertEqual(len(self.calls),1);self.assertEqual(self.service.get(self.project['id'],row['vision_id'])['status'],'succeeded')

    def test_replay_after_edit_is_historical_and_different_payload_conflicts(self):
        request=self.request();row=self.service.create(self.project['id'],request,principal=self.principal)[0]
        self.store.save(self.project['id'],self.project['revision'],prompt='EXPLICIT HISTORY CHANGE')
        replay,exact=self.service.create(self.project['id'],request,principal=self.principal);self.assertTrue(exact);self.assertEqual(replay,row)
        with self.assertRaisesRegex(WorkflowError,'IDEMPOTENCY_CONFLICT'):
            self.service.create(self.project['id'],request.model_copy(update={'revision':request.revision+1}),principal=self.principal)
        self.assertEqual(self.process(row)['status'],'failed');self.assertEqual(self.calls,[])

    def test_roles_identity_revision_revocation_and_window_block_before_key(self):
        for role in ('viewer','editor','reviewer'):
            raw,data=human_fixture(role,workspace=self.workspace);other=HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400)
            with self.assertRaisesRegex(WorkflowError,'CURRENT_OWNER_REQUIRED'):self.service.create(self.project['id'],self.request(),principal=other.verify('Bearer '+raw))
        row=self.create();self.change_owner(display_name='EXPLICIT CHANGED IDENTITY')
        with patch.object(self.vault,'key',side_effect=AssertionError('NO REVOKED KEY')):self.assertEqual(self.process(row)['status'],'failed')
        self.assertEqual(self.calls,[])

    def test_expiry_and_identity_expiry_never_renew_on_reopen(self):
        row=self.create();self.clock[0]+=timedelta(seconds=601)
        with patch.object(self.vault,'key',side_effect=AssertionError('NO EXPIRED KEY')):done=self.process(row)
        self.assertEqual(done['status'],'failed');self.assertEqual(done['snapshot']['deadline'],row['snapshot']['deadline'])
        reopened=self.runtime();self.assertEqual(reopened.get(self.project['id'],row['vision_id']),done)
        self.change_owner(expires_at=(datetime.now(timezone.utc)+timedelta(seconds=100)).isoformat())
        self.clock[0]=datetime.now(timezone.utc);self.principal=self.verifier.verify('Bearer '+'vf1.explicit-fixture.'+'x'*48)
        with self.assertRaisesRegex(WorkflowError,'CONSENT_EXCEEDS_IDENTITY'):self.create(request_key='explicit-render-short-identity')

    def test_raw_fields_source_acknowledgement_and_unchecked_models_refuse(self):
        for changes in ({'revision':True},{'acknowledged_rendered_frame_analysis':1},{'acknowledged_protocol_mock':1},
            {'max_operation_cost_vnd':True},{'max_operation_cost_vnd':1.5},{'valid_for_seconds':True},{'valid_for_seconds':901},
            {'profile_id':'nvip_'+'a'*32},{'acknowledged_external_image_analysis':True},{'api_key':'NO CLIENT SECRET'}):
            with self.assertRaises(ValidationError):self.request(**changes)
        with self.assertRaisesRegex(WorkflowError,'FIELDS_INVALID'):self.service.create(self.project['id'],self.request().model_copy(update={'revision':True}),principal=self.principal)
        with self.assertRaisesRegex(WorkflowError,'COST_CEILING_REQUIRED'):self.create(max_operation_cost_vnd='300')
        self.assertEqual(self.calls,[])

    def test_budget_existing_and_late_reservations_block_before_private_resolution(self):
        row=self.create()
        self.service.costs.begin(project_id=self.project['id'],provider='explicit-contract',model='mock',operation='late-reservation',request_sha256='a'*64,estimated_cost='600',paid=True,external_call=False)
        with patch.object(self.vault,'key',side_effect=AssertionError('NO OVERBUDGET KEY')):self.assertEqual(self.process(row)['status'],'needs_approval')
        other=self.create(request_key='explicit-render-overbudget-key');self.assertEqual(other['status'],'needs_approval');self.assertEqual(self.calls,[])

    def test_live_fixture_or_unknown_rights_refuses_without_key_or_wire(self):
        live=NativeRenderVisionFactory(self.factory.profile,self.vault,operator_enabled=True)
        service=NativeRenderVision(self.store,self.config,workspace_id=self.workspace,factories={live.profile.profile_id:live},enabled=True,identity_provider=lambda:self.verifier)
        with patch.object(self.vault,'key',side_effect=AssertionError('NO RIGHTS UNCERTAIN KEY')):
            with self.assertRaisesRegex(WorkflowError,'RIGHTS_'):service.create(self.project['id'],self.request(expected_configuration_sha256=live.sha256,acknowledged_protocol_mock=False),principal=self.principal)
        self.assertEqual(self.calls,[])

    def test_late_revocation_after_key_or_frame_decode_blocks_before_wire(self):
        row=self.create();original=self.vault.key
        def late_key(receipt):
            key=original(receipt);self.change_owner(enabled=False);return key
        with patch.object(self.vault,'key',side_effect=late_key):done=self.process(row)
        self.assertEqual(done['status'],'outcome_unknown');self.assertEqual(self.calls,[])
        self.assertEqual(self.service.costs.summary(self.project['id'])['records'][0]['status'],'outcome_unknown')

    def test_revoke_after_image_extraction_refuses_wire_and_retains_rejected_cost(self):
        row=self.create();original=NativeRenderEvidenceFrameExtractor.extract
        async def late_frames(bridge,*args,**kwargs):
            frames=await original(bridge,*args,**kwargs);self.change_owner(enabled=False);return frames
        with patch.object(NativeRenderEvidenceFrameExtractor,'extract',new=late_frames):done=self.process(row)
        self.assertEqual(done['status'],'failed');self.assertEqual(self.calls,[])
        self.assertEqual(self.service.costs.summary(self.project['id'])['records'][0]['status'],'rejected')

    def test_complete_late_revoke_response_is_retained_review_only(self):
        row=self.create();self.mode='revoke';done=self.process(row)
        self.assertEqual(done['status'],'review_required');self.assertIsNotNone(done['response']);self.assertIsNone(done['result'])
        self.assertEqual(self.service.costs.summary(self.project['id'])['records'][0]['status'],'response_received');self.assertEqual(len(self.calls),1)
        self.assertEqual(self.process(row),done);self.assertEqual(len(self.calls),1)

    def test_timeout_rate_limit_bad_output_missing_usage_never_replay(self):
        for i,mode in enumerate(('timeout','rate-limit','invalid','missing-usage','over-ceiling')):
            row=self.create(request_key='explicit-render-errors-key-'+str(i));self.mode=mode;before=len(self.calls);done=self.process(row)
            self.assertEqual(done['status'],'outcome_unknown' if mode=='timeout' else 'review_required',mode)
            self.assertIsNone(done['result']);self.assertEqual(len(self.calls),before+1)
            self.assertEqual(self.process(row),done);self.assertEqual(len(self.calls),before+1)
            self.assertNotIn('sk-private',json.dumps(done))

    def test_cancel_before_and_during_wire_is_local_no_remote_rollback(self):
        row=self.create();cancelled=self.service.cancel(self.project['id'],row['vision_id'],self.action(row),principal=self.principal)
        self.assertEqual(cancelled['status'],'cancelled');self.assertEqual(self.process(row),cancelled);self.assertEqual(self.calls,[])
        row=self.create(request_key='explicit-render-cancel-during-key');self.pending=row;self.mode='cancel';done=self.process(row)
        self.assertEqual(done['status'],'cancelled');self.assertIsNotNone(done['response']);self.assertEqual(len(self.calls),1)

    def test_interrupted_claim_backup_busy_recovery_keyless_history_no_replay(self):
        row=self.create();claim='nrvc_'+'b'*32;cost=digest({'project':self.project['id'],'job':self.job['id'],'provider':'openai-vision','operation':'render-vision.'+claim})
        with self.store.transaction() as con:
            con.execute("UPDATE native_render_vision_intents SET status='claimed',claim_id=?,cost_operation_id=? WHERE vision_id=?",(claim,cost,row['vision_id']))
        facts=database_status(self.store.db);self.assertEqual(facts['active_operations'],1);self.assertTrue(set(TABLES)<=set(facts['counts']))
        with self.assertRaisesRegex(WorkflowError,'BACKUP_SOURCE_HAS_ACTIVE_OPERATIONS'):create_backup(self.config,Path(self.temp.name)/'busy.zip')
        disabled=self.runtime();self.assertEqual(disabled.recover(),1);done=disabled.get(self.project['id'],row['vision_id'])
        self.assertEqual(done['status'],'outcome_unknown');self.assertEqual(self.process(row),done);self.assertEqual(self.calls,[])
        self.assertEqual(database_status(self.store.db)['active_operations'],0)

    def test_history_after_missing_original_pixels_config_keys_owner_remains_read_only(self):
        row=self.create();done=self.process(row);self.assertEqual(done['status'],'succeeded')
        shutil.rmtree(self.root/'jobs'/self.job['id']);self.change_owner(enabled=False)
        reader=NativeRenderVision(self.store,self.config,workspace_id=self.workspace)
        with patch.object(self.vault,'key',side_effect=AssertionError('NO HISTORY KEY')):self.assertEqual(reader.get(self.project['id'],row['vision_id']),done)
        self.assertEqual(self.process(row),done);self.assertEqual(len(self.calls),1)

    def test_result_and_response_corruption_even_rehashed_authority_flags_fail(self):
        row=self.create();done=self.process(row);original=copy.deepcopy(done['result'])
        for key,new in (('hard_qc_replaced',True),('owner_uat_accepted',0),('mock',1),('external_provider_calls',False),('rendered_video_sha256','0'*64)):
            result=copy.deepcopy(original);result[key]=new
            with self.store.transaction() as con:con.execute('UPDATE native_render_vision_intents SET result_json=?,result_sha256=? WHERE vision_id=?',(json.dumps(result),digest(result),row['vision_id']))
            with self.assertRaisesRegex(WorkflowError,'EVIDENCE_INVALID'):self.service.get(self.project['id'],row['vision_id'])
        with self.store.transaction() as con:con.execute('UPDATE native_render_vision_intents SET result_json=?,result_sha256=? WHERE vision_id=?',(json.dumps(original),digest(original),row['vision_id']))
        with self.store.transaction() as con:con.execute("UPDATE native_render_vision_responses SET observation_sha256=? WHERE vision_id=?",('0'*64,row['vision_id']))
        with self.assertRaisesRegex(WorkflowError,'EVIDENCE_INVALID'):self.service.get(self.project['id'],row['vision_id'])

    def test_stale_approval_original_frame_and_config_changes_refuse_before_key(self):
        for i,mode in enumerate(('approval','frame','configuration')):
            row=self.create(request_key='explicit-render-input-change-'+str(i))
            with patch.object(self.vault,'key',side_effect=AssertionError('NO CHANGED INPUT KEY')):
                if mode=='approval':
                    with self.store.transaction() as con:con.execute('UPDATE projects SET approval=NULL WHERE id=?',(self.project['id'],))
                if mode=='frame':
                    frame=self.bridge().binding()['record']['observation']['frames'][0];path=self.root/'jobs'/self.job['id']/frame['evidence_frame_reference'];old=path.read_bytes();path.write_bytes(old+b'changed')
                if mode=='configuration':self.factory.operator_enabled=False
                done=self.process(row);self.assertEqual(done['status'],'failed',mode);self.assertEqual(self.calls,[])
            if mode=='approval':
                with self.store.transaction() as con:con.execute('UPDATE projects SET approval=? WHERE id=?',(json.dumps(self.job['snapshot']['approval']),self.project['id']))
            if mode=='frame':path.write_bytes(old)

    def test_shared_owned_transaction_frame_binding_and_foreign_connection_refusal(self):
        with self.store.transaction() as con:
            bridge=NativeRenderEvidenceFrameExtractor(self.store,self.config,self.project['id'],self.job['id'],con=con)
            self.assertTrue(bridge.binding(con=con)['matches_current_project_document'])
        other=Store(Path(self.temp.name)/'foreign')
        with other.transaction() as con:
            with self.assertRaisesRegex(WorkflowError,'BINDING_INVALID'):
                NativeRenderEvidenceFrameExtractor(self.store,self.config,self.project['id'],self.job['id'],con=con)

    def test_keyless_page_snapshot_binding_and_cancellation_permission(self):
        first=self.create();second=self.create(request_key='explicit-render-page-second-key')
        page=self.service.page(self.project['id'],limit=1);self.assertIsNotNone(page['next_cursor'])
        self.assertEqual(len(self.service.page(self.project['id'],limit=1,cursor=page['next_cursor'])['items']),1)
        with self.assertRaisesRegex(WorkflowError,'CURSOR_INVALID'):self.service.page(self.project['id'],cursor='bad')
        with self.assertRaisesRegex(WorkflowError,'SNAPSHOT_CHANGED'):self.service.process(self.project['id'],first['vision_id'],RenderAction(expected_snapshot_sha256='0'*64))
        self.change_owner(enabled=False)
        with self.assertRaisesRegex(WorkflowError,'CURRENT_OWNER_REQUIRED'):self.service.cancel(self.project['id'],second['vision_id'],self.action(second),principal=self.principal)
        self.assertEqual(self.calls,[])

    def test_snapshot_input_authority_constants_cannot_be_rehashed_into_new_consent(self):
        row=self.create();saved=copy.deepcopy(row['snapshot'])
        for changes in ({'source_asset_analysis_consent_reused':True},{'external_provider_calls':False},{'separate_owner_provider_consent_required':1}):
            snapshot=copy.deepcopy(saved);snapshot['input_binding'].update(changes)
            snapshot['request']['expected_render_input_sha256']=digest(snapshot['input_binding'])
            with self.store.transaction() as con:
                con.execute('UPDATE native_render_vision_intents SET snapshot_json=?,snapshot_sha256=?,request_sha256=? WHERE vision_id=?',
                    (json.dumps(snapshot),digest(snapshot),digest(snapshot['request']),row['vision_id']))
            with self.assertRaisesRegex(WorkflowError,'EVIDENCE_INVALID'):self.service.get(self.project['id'],row['vision_id'])
        self.assertEqual(self.calls,[])


if __name__=='__main__':unittest.main()
