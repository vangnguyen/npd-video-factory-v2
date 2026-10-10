"""Actual DPAPI/SQLite with explicit TikTok protocol and nonplayable media fixtures."""
import asyncio,copy,json,tempfile,unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
import httpx
from pydantic import ValidationError
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
from app.publishing_models import PublishingTargetBinding,PublicationMetadata
from app.publishing_wire import PublishingWireError
from app.tiktok_credentials import SCOPES
from services.windows_native import tiktok_connection as connection
from services.windows_native.tiktok_creators import NativeTikTokCreators,Check,Action,Draft,TABLE,RESPONSES,DRAFTS
from services.windows_native.contracts import WorkflowError,digest,file_sha
from services.windows_native.store import Store
from services.windows_native.publications import NativePublications
from services.windows_native.official_accounts import NativeOfficialAccounts
from services.windows_native.official_publications import NativeOfficialPublications
from services.windows_native.tests.test_human_identity import fixture as human_fixture
from services.windows_native.tests.test_publications import render_fixture,CAPABILITIES
from services.windows_native.backup import database_status

TOKEN='EXPLICIT-TIKTOK-PUBLISHER-ACCESS-FIXTURE-0123456789'
class TikTokCreatorFixture:
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name).resolve();self.root=self.folder/'state';self.root.mkdir();self.store=Store(self.root)
        self.workspace='wsp_tiktok_creator_fixture';self.clock=[datetime.now(timezone.utc)];self.wire=[];self.mode=None
        (self.root/'.vf-auth-workspace.json').write_text(json.dumps({'schema':'vf-native-workspace-binding-v1','workspace_id':self.workspace}),encoding='utf-8')
        self.raw,data=human_fixture('owner',workspace=self.workspace);self.verifier=HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400);self.principal=self.verifier.verify('Bearer '+self.raw)
        self.publications=NativePublications(self.store,CAPABILITIES,workspace_id=self.workspace,clock=lambda:self.clock[0]);self.accounts=NativeOfficialAccounts(self.store,workspace_id=self.workspace,clock=lambda:self.clock[0])
        self.official=NativeOfficialPublications(self.store,self.publications,self.accounts,identity_provider=lambda:self.verifier,clock=lambda:self.clock[0])
        self.project,self.job=render_fixture(self.store);self.project=self.store.get(self.project['id'])
        self.target=PublishingTargetBinding(workspace_id=self.workspace,profile_id='ppf_tiktok_creator_fixture',profile_version=1,platform='tiktok',provider_key='tiktok-content-posting-api',target_account_id='EXPLICIT_TIKTOK_OPEN_ID',credential_binding_sha256='a'*64)
        self.path=self.folder/'private'/'tiktok-publisher.dpapi';self.token=connection.AccessToken(target=self.target,credential_alias='explicit-tiktok-publisher',expires_at=self.clock[0]+timedelta(hours=1),scopes=sorted(SCOPES),token=TOKEN)
        self.receipt=connection.save_token(self.path,self.root,self.token)
        self.binding=connection.Binding(profile=connection.Profile(target=self.target),credential_alias=self.token.credential_alias,token_file=str(self.path),creator_reads_enabled=True)
        self.factory=connection.NativeTikTokFactory(self.binding,self.root,self.workspace,owner_read_enabled=True,transport=httpx.MockTransport(self.response))
        self.service=NativeTikTokCreators(self.official,factories={self.target.profile_id:self.factory},enabled=True)
    def tearDown(self):self.temp.cleanup()
    def fixture_document_drift(self):
        # This nonplayable publication fixture has a deliberately thin timeline.
        # Seed hostile database drift; it is not a product editing/approval path.
        with self.store.transaction() as con:
            current=self.store.editable(con,self.project['id'],self.project['revision']);document=copy.deepcopy(current['document']);document['prompt']='EXPLICIT FIXTURE DOCUMENT DRIFT'
            con.execute('UPDATE projects SET revision=?,document=?,approval=NULL,updated_at=? WHERE id=?',(current['revision']+1,json.dumps(document),self.clock[0].isoformat(),current['id']))
            self.store.version(con,current['id']);self.store.event(con,current['id'],'explicit_fixture_document_drift',{'fixture':True})
        self.project=self.store.get(self.project['id'])
    def response(self,request):
        self.assertEqual(request.headers['authorization'],'Bearer '+TOKEN);self.wire.append({'method':request.method,'host':request.url.host,'path':request.url.path})
        if self.mode=='timeout':raise httpx.ReadTimeout(TOKEN,request=request)
        if self.mode=='revoke':
            raw=copy.deepcopy(self.verifier.registry.model_dump(mode='json'));raw['tokens'][self.principal.token_id]['enabled']=False;self.verifier=HumanAuthVerifier(HumanAuthRegistry.model_validate(raw),max_token_ttl_seconds=86400)
        if self.mode=='edit':self.fixture_document_drift()
        if self.mode=='recover':self.service.recover()
        if self.mode=='busy':self.busy=database_status(self.store.db)
        if self.mode=='rate-limit':return httpx.Response(429,headers={'retry-after':'30'})
        if request.url.path=='/v2/user/info/':
            self.assertEqual(request.method,'GET');self.assertEqual(request.url.params['fields'],'open_id')
            return httpx.Response(200,json={'error':{'code':'ok'},'data':{'user':{'open_id':'FOREIGN' if self.mode=='foreign' else self.target.target_account_id}}})
        self.assertEqual(request.url.path,'/v2/post/publish/creator_info/query/');self.assertEqual(request.method,'POST');self.assertEqual(request.content,b'{}')
        return httpx.Response(200,json={'error':{'code':'ok'},'data':{'creator_username':'explicit_fixture_creator','creator_nickname':'Người tạo mô phỏng',
            'privacy_level_options':['SELF_ONLY','PUBLIC_TO_EVERYONE'],'comment_disabled':False,'duet_disabled':True,'stitch_disabled':False,'max_video_post_duration_sec':180}})
    def body(self,**changes):return Check.model_validate({'revision':self.project['revision'],'profile_id':self.target.profile_id,'expected_configuration_sha256':self.factory.sha256,
        'acknowledged_creator_read':True,'acknowledged_protocol_mock':True,'request_key':'explicit-tiktok-creator-read-key',**changes})
    def create(self,**changes):return self.service.create(self.project['id'],self.body(**changes),principal=self.principal)[0]
    def fetch(self,value):return asyncio.run(self.service.fetch(self.project['id'],value['check_id'],principal=self.principal,expected_snapshot_sha256=value['snapshot_sha256']))
    def completed(self):return self.fetch(self.create())
    def draft_body(self,value,**changes):
        return Draft.model_validate({'revision':self.project['revision'],'creator_check_id':value['check_id'],'expected_creator_result_sha256':value['result_sha256'],
            'final_job_id':self.job['id'],'expected_final_sha256':self.job['result']['qc']['final_sha256'],
            'metadata':{'title':'Tiêu đề fixture có thể sửa','privacy':'private'},'choices':{'privacy_level':'SELF_ONLY','disable_comment':True,'disable_duet':True,'disable_stitch':True,
                'brand_content_toggle':False,'brand_organic_toggle':False,'is_aigc':True,'music_usage_confirmed':True},
            'acknowledged_video_selection':True,'acknowledged_ai_disclosure':True,'request_key':'explicit-tiktok-post-draft-key',**changes})

class TikTokCreatorTests(TikTokCreatorFixture,unittest.TestCase):
    def test_default_service_discovery_prepare_and_registry_never_decrypt_or_send(self):
        service=NativeTikTokCreators(self.official,factories={self.target.profile_id:self.factory})
        with patch.object(connection,'load_token',side_effect=AssertionError('No startup/history decrypt')):
            self.assertFalse(service.states()['enabled']);value=service.create(self.project['id'],self.body(),principal=self.principal)[0]
            self.assertEqual(value['status'],'not_configured');service.get(self.project['id'],value['check_id']);service.page(self.project['id']);self.assertEqual(service.recover(),0)
        self.assertEqual(self.wire,[]);self.assertFalse(self.factory.public()['publication_dispatch_supported'])
    def test_same_grant_account_then_creator_proof_costs_and_no_publication(self):
        before=self.store.get(self.project['id']);value=self.completed();self.assertEqual(value['status'],'succeeded',value)
        self.assertEqual([r['path'] for r in self.wire],['/v2/user/info/','/v2/post/publish/creator_info/query/'])
        self.assertEqual(value['result']['creator']['nickname'],'Người tạo mô phỏng');self.assertFalse(value['result']['real_provider_tested']);self.assertFalse(value['publishing_enabled'])
        costs=self.service.costs.summary(self.project['id']);self.assertEqual(costs['attempted_operations'],2);self.assertTrue(all(not c['paid'] and not c['external_call'] and c['actual_cost'] is None for c in costs['records']))
        with self.store.transaction() as con:self.assertEqual(con.execute('SELECT count(*) FROM native_official_publications').fetchone()[0],0)
        self.assertEqual(self.store.get(self.project['id']),before)
        for private in (TOKEN,self.raw,str(self.path)):self.assertNotIn(private,json.dumps([value,self.service.states(),costs]))
    def test_idempotency_success_replay_does_not_query_again(self):
        first=self.completed();value,found=self.service.create(self.project['id'],self.body(),principal=self.principal);self.assertTrue(found);self.assertEqual(value,first)
        self.assertEqual(self.fetch(value),first);self.assertEqual(len(self.wire),2)
        with self.assertRaisesRegex(WorkflowError,'IDEMPOTENCY_CONFLICT'):self.create(valid_for_seconds=601)
    def test_wrong_open_id_blocks_creator_request_and_private_errors_are_redacted(self):
        self.mode='foreign';value=self.completed();self.assertNotEqual(value['status'],'succeeded');self.assertIsNone(value['result']);self.assertEqual(len(self.wire),1)
        self.assertNotIn(TOKEN,json.dumps(value))
    def test_timeout_or_rate_limit_never_automatically_replays(self):
        for mode in ('timeout','rate-limit'):
            self.mode=mode;value=self.fetch(self.create(request_key='explicit-tiktok-creator-'+mode));self.assertNotEqual(value['status'],'succeeded')
            with self.assertRaises(WorkflowError):self.fetch(value)
        self.assertEqual(len(self.wire),2);self.assertIsNone(value['result'])
    def test_document_change_after_account_blocks_creator_wire(self):
        self.mode='edit';value=self.completed();self.assertNotEqual(value['status'],'succeeded');self.assertEqual(len(self.wire),1)
    def test_recovery_claim_is_unknown_with_no_private_load_or_provider_replay(self):
        self.mode='recover';value=self.completed();self.assertEqual(value['status'],'outcome_unknown');self.assertEqual(len(self.wire),1)
        with patch.object(connection,'load_token',side_effect=AssertionError('No recovery decrypt')):self.assertEqual(self.service.recover(),0);self.service.get(self.project['id'],value['check_id'])
    def test_revoked_owner_after_account_blocks_creator_wire(self):
        self.mode='revoke';value=self.completed();self.assertNotEqual(value['status'],'succeeded');self.assertEqual(len(self.wire),1)
    def test_last_private_load_revocation_blocks_both_wires(self):
        value=self.create();load=connection.load_token
        def revoked(*args):
            credential=load(*args);raw=copy.deepcopy(self.verifier.registry.model_dump(mode='json'));raw['tokens'][self.principal.token_id]['enabled']=False
            self.verifier=HumanAuthVerifier(HumanAuthRegistry.model_validate(raw),max_token_ttl_seconds=86400);return credential
        with patch.object(connection,'load_token',side_effect=revoked):result=self.fetch(value)
        self.assertEqual(result['status'],'failed');self.assertEqual(self.wire,[])
    def test_cipher_change_before_fetch_is_fenced_without_decrypt(self):
        value=self.create();self.path.write_bytes(self.path.read_bytes()+b'corrupt')
        with patch.object(connection,'load_token',side_effect=AssertionError('No changed ciphertext decrypt')):
            with self.assertRaises(WorkflowError):self.fetch(value)
        self.assertEqual(self.wire,[])
    def test_token_expiry_margin_blocks_wire_at_last_private_load(self):
        self.path=self.folder/'private'/'short-lived-tiktok.dpapi';self.token=self.token.model_copy(update={'expires_at':self.clock[0]+timedelta(seconds=90)})
        connection.save_token(self.path,self.root,self.token);self.binding=self.binding.model_copy(update={'token_file':str(self.path)})
        self.factory=connection.NativeTikTokFactory(self.binding,self.root,self.workspace,owner_read_enabled=True,transport=httpx.MockTransport(self.response))
        self.service=NativeTikTokCreators(self.official,factories={self.target.profile_id:self.factory},enabled=True)
        value=self.create()
        result=self.fetch(value);self.assertEqual(result['status'],'failed');self.assertEqual(self.wire,[])
    def test_backup_counts_claim_before_both_wires(self):
        self.mode='busy';self.completed();self.assertEqual(self.busy['active_operations'],1);self.assertEqual(self.busy['counts'][TABLE],1);self.assertEqual(database_status(self.store.db)['active_operations'],0)
    def test_successful_choices_bind_original_final_without_upload_or_timeline_mutation(self):
        source=self.completed();before=self.store.get(self.project['id']);sha=file_sha(self.root/self.job['result']['final_path']) if 'final_path' in self.job['result'] else self.job['result']['qc']['final_sha256']
        draft,found=self.service.draft(self.project['id'],self.draft_body(source),principal=self.principal);self.assertFalse(found)
        self.assertTrue(draft['publish_approval_required']);self.assertFalse(draft['publishing_enabled']);self.assertEqual(draft['snapshot']['source']['final_sha256'],sha)
        self.assertEqual(self.service.get_draft(self.project['id'],draft['draft_id']),draft);self.assertEqual(self.store.get(self.project['id']),before);self.assertEqual(len(self.wire),2)
        self.assertEqual(self.service.draft(self.project['id'],self.draft_body(source),principal=self.principal),(draft,True))
    def test_unaudited_privacy_disabled_interaction_long_caption_and_music_ack_block_draft(self):
        source=self.completed();base=self.draft_body(source).model_dump(mode='python')
        variants=[{'metadata':{'title':'fixture','privacy':'public'},'choices':{**base['choices'],'privacy_level':'PUBLIC_TO_EVERYONE'}},
            {'choices':{**base['choices'],'disable_duet':False}},{'metadata':{'title':'fixture','privacy':'private','description':'X'*2201}},
            {'choices':{**base['choices'],'music_usage_confirmed':1}},{'acknowledged_video_selection':1},{'acknowledged_ai_disclosure':1}]
        for change in variants:
            with self.assertRaises((WorkflowError,PublishingWireError,ValidationError)):self.service.draft(self.project['id'],Draft.model_validate({**base,**change}),principal=self.principal)
        self.assertEqual(self.service.page(self.project['id'],kind='draft')['items'],[]);self.assertEqual(len(self.wire),2)
    def test_draft_history_survives_local_creator_cancel_and_never_becomes_publish_authority(self):
        source=self.completed();draft=self.service.draft(self.project['id'],self.draft_body(source),principal=self.principal)[0]
        self.service.cancel(self.project['id'],source['check_id'],Action(expected_snapshot_sha256=source['snapshot_sha256']),principal=self.principal)
        self.assertEqual(self.service.get_draft(self.project['id'],draft['draft_id']),draft);self.assertFalse(draft['publishing_enabled'])
    def test_foreign_scope_numeric_ack_and_unbounded_pages_rejected(self):
        source=self.completed();other=self.store.create('Foreign fixture','','media')
        with self.assertRaises(WorkflowError):self.service.get(other['id'],source['check_id'])
        for change in ({'acknowledged_creator_read':1},{'acknowledged_protocol_mock':1},{'token':TOKEN},{'valid_for_seconds':901}):
            with self.assertRaises(ValidationError):self.body(**change)
        for change in ({'limit':0},{'limit':101},{'cursor':'ntpd_'+'f'*32},{'kind':'foreign'}):
            with self.assertRaises(WorkflowError):self.service.page(self.project['id'],**change)
    def test_tampered_response_cost_or_public_factory_cannot_be_trusted(self):
        source=self.completed()
        with self.store.transaction() as con:
            con.execute('UPDATE '+RESPONSES+" SET response_sha256=? WHERE check_id=? AND operation='creator'",('f'*64,source['check_id']))
        with self.assertRaises(WorkflowError):self.service.get(self.project['id'],source['check_id'])
    def test_draft_cannot_bind_an_approved_final_from_a_prior_project_revision(self):
        self.fixture_document_drift()
        source=self.completed()
        with self.assertRaisesRegex(WorkflowError,'STALE_VERSION_RELOAD|DRAFT_FINAL_CHANGED'):self.service.draft(self.project['id'],self.draft_body(source),principal=self.principal)
        self.assertEqual(self.service.page(self.project['id'],kind='draft')['items'],[])
    def test_historical_draft_links_original_job_and_creator_cost_not_just_rehashed_json(self):
        source=self.completed();draft=self.service.draft(self.project['id'],self.draft_body(source),principal=self.principal)[0]
        with self.store.transaction() as con:
            row=con.execute('SELECT result FROM jobs WHERE id=?',(self.job['id'],)).fetchone();result=json.loads(row['result']);result['qc']['duration_seconds']=123
            con.execute('UPDATE jobs SET result=? WHERE id=?',(json.dumps(result),self.job['id']))
        with self.assertRaisesRegex(WorkflowError,'DRAFT_FINAL_CHANGED'):self.service.get_draft(self.project['id'],draft['draft_id'])
        with self.assertRaisesRegex(WorkflowError,'DRAFT_FINAL_CHANGED'):self.service.draft(self.project['id'],self.draft_body(source),principal=self.principal)

if __name__=='__main__':unittest.main()
