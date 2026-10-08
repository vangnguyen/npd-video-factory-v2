"""Qualified protocol mocks/nonplayable renders only; no real audience or Owner UAT."""
import copy,json,subprocess,sys,unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch
import httpx
from pydantic import ValidationError
from services.windows_native.tests import test_official_analytics as analytics_fixture
from services.windows_native.tests import test_official_publications as review_fixture
from services.windows_native.tests import test_official_publication_worker as worker_fixture
from services.windows_native.tests.test_publications import render_fixture
from services.windows_native.official_winners import NativeOfficialWinners,TABLES
from services.windows_native.official_winner_models import Create
from services.windows_native.official_analytics import NativeOfficialAnalytics
from services.windows_native.official_accounts import Verify
from services.windows_native.official_publication_worker import NativeOfficialPublicationWorker
from services.windows_native.publication_models import NativePublicationCreate,NativePublishApproval
from services.windows_native.channel_profiles import select
from services.windows_native.contracts import WorkflowError,digest
from services.windows_native.backup import database_status
from app.youtube_upload import UNIT
from app.analytics_channel_policy import WinnerChannelPolicy,VERSION

class OfficialWinnerFixture(analytics_fixture.OfficialAnalyticsFixture):
    def configured_render(self,store,**kwargs):
        project=kwargs.pop('project',None) or store.create('EXPLICIT PROTOCOL-MOCK COHORT FIXTURE','','media',channel_profile=select(self.reference))
        return render_fixture(store,project=project,**kwargs)
    def setUp(self):
        self.reference='ai-education-reference@1'
        with patch.object(review_fixture,'render_fixture',side_effect=self.configured_render):super().setUp()
        self.winners=NativeOfficialWinners(self.analytics);self.remote='FIXTURE0001';self.client.transport.handler=self.publish_response
        self.anchor=self.run_collection();self.anchor_project=self.project['id'];self.anchor_job=self.job['id'];self.anchor_publication=self.completed
    def publish_response(self,request):
        response=worker_fixture.OfficialWorkerTests.response(self,request)
        if response.status_code==200 and request.url.path!='/youtube/v3/channels' and request.method!='POST':
            data=response.json()
            if 'id' in data:data['id']=self.remote
            if 'items' in data:
                for item in data['items']:item['id']=self.remote
            return httpx.Response(200,json=data)
        return response
    def read_response(self,request):
        response=super().read_response(request)
        if response.status_code==200 and request.url.path=='/youtube/v3/videos':
            data=response.json()
            for item in data['items']:item['id']=request.url.params['id']
            return httpx.Response(200,json=data)
        return response
    def peer(self,index,*,reference='ai-education-reference@1',query=None):
        self.reference=reference;content=('EXPLICIT NONPLAYABLE COHORT FIXTURE '+str(index)+'; NO FULL QC\n').encode();content+=b'X'*(2*UNIT+17-len(content))
        self.project,self.job=self.configured_render(self.store,final_bytes=content)
        parent,_=self.publications.create(self.project['id'],NativePublicationCreate(revision=self.project['revision'],final_job_id=self.job['id'],platform='youtube',
            metadata={'title':'EXPLICIT PROTOCOL-MOCK COHORT FIXTURE '+str(index),'privacy':'private'},request_key='explicit-winner-peer-dry-run-'+str(index)),actor=self.principal.token_id)
        self.publications.approve(self.project['id'],parent['publication_id'],NativePublishApproval(expected_fingerprint=parent['request_fingerprint'],expected_artifact_sha256=parent['snapshot']['final_sha256'],acknowledged=True),actor=self.principal.token_id)
        self.parent=self.publications.process()
        self.accounts.create(self.project['id'],self.reader.account.account_ref,Verify(revision=self.project['revision'],expected_configuration_sha256=self.reader.sha256,
            acknowledged_read_only=True,request_key='explicit-winner-peer-account-'+str(index)),actor=self.principal.token_id);self.check=self.accounts.process()
        self.value=self.create();self.approve(self.value);self.ack=0;self.remote='FIXTURE'+str(index).zfill(4);worker=NativeOfficialPublicationWorker(self.service,self.vault)
        for _ in range(4):worker.step(self.project['id'],self.value['publication_id'],self.state()['version'])
        self.completed=worker.poll_processing(self.project['id'],self.value['publication_id'],self.state()['version'])
        self.metric_values=[1000,20,1.2,25,2,5,5]
        return self.run_collection(request_key='explicit-winner-peer-read-'+str(index),**({'query':query} if query else {}))
    def cohort(self,count=5):
        for i in range(2,count+2):self.peer(i)
        self.project=self.store.get(self.anchor_project);self.job=self.store.get_job(self.anchor_job);self.completed=self.anchor_publication
        self.metric_values=[1000,40,2.4,50,4,10,10];self.anchor=self.run_collection(request_key='explicit-winner-qualified-candidate-refresh')
        return self.anchor
    def winner_body(self,**changes):
        return Create.model_validate({'sync_id':self.anchor['sync_id'],'expected_result_sha256':digest(self.anchor['result']),
            'acknowledged_recommendation_only':True,'acknowledged_protocol_mock':True,'request_key':'explicit-native-winner-assessment-key',**changes})
    def assess(self,**changes):return self.winners.create(self.anchor_project,self.winner_body(**changes),principal=self.principal)[0]

class OfficialWinnersTests(OfficialWinnerFixture,unittest.TestCase):
    def test_sparse_first_observation_is_immutable_insufficient_and_has_no_operation(self):
        before=self.store.get(self.anchor_project);wire=copy.deepcopy(self.read_wire);costs=self.analytics.costs.summary(self.anchor_project)
        result=self.assess();assessment=result['assessment'];self.assertEqual(assessment['state'],'insufficient_data');self.assertIsNone(assessment['score']);self.assertEqual(result['peer_count'],0)
        self.assertEqual(assessment['algorithm_version'],VERSION);self.assertTrue(result['mock']);self.assertFalse(result['real_audience_observation']);self.assertFalse(assessment['channel_baseline_verified'])
        self.assertIsNone(next(v for v in assessment['factors'] if v['factor']=='view_velocity')['score']);self.assertIsNone(assessment['publishing_age_hours'])
        self.assertFalse(result['automatic_action']);self.assertFalse(result['external_call']);self.assertEqual(self.read_wire,wire);self.assertEqual(self.analytics.costs.summary(self.anchor_project),costs);self.assertEqual(self.store.get(self.anchor_project),before)
        self.assertEqual(self.winners.get(self.anchor_project,result['assessment_id']),result)
    def test_five_qualified_distinct_peer_posts_score_relative_protocol_mock_without_velocity_or_real_claim(self):
        self.cohort();before=self.read_wire.copy();value=self.assess();a=value['assessment'];self.assertEqual(value['peer_count'],5);self.assertEqual(a['state'],'winner_candidate');self.assertEqual(a['score'],100)
        self.assertEqual(a['data_coverage'],.43);self.assertFalse(a['view_velocity_supported']);self.assertFalse(a['channel_baseline_verified']);self.assertFalse(a['real_audience_observation'])
        factors={f['factor']:f for f in a['factors']};self.assertAlmostEqual(factors['retention']['evidence']['peer_median'],.4);self.assertEqual(factors['retention']['evidence']['peer_count'],5)
        self.assertIsNone(factors['completion']['score']);self.assertIsNone(factors['ctr']['score']);self.assertIsNone(factors['production_cost_efficiency']['score']);self.assertEqual(self.read_wire,before)
        self.assertEqual(len({p['remote_post_id'] for p in value['snapshot']['peers']}),5)
        for i,(metrics,expected) in enumerate((([1000,20,1.2,25,2,5,5],'normal'),([1000,10,.6,12,1,2,2],'underperforming'),(None,'insufficient_data'))):
            self.rows=metrics is not None
            if metrics is not None:self.metric_values=metrics
            self.anchor=self.run_collection(request_key='explicit-winner-classification-refresh-'+str(i));assessment=self.assess(request_key='explicit-winner-classification-assessment-'+str(i))
            self.assertEqual(assessment['assessment']['state'],expected);self.assertTrue(assessment['mock']);self.assertFalse(assessment['real_audience_observation'])
            self.assertEqual(self.winners.get(self.anchor_project,value['assessment_id']),value)
    def test_exact_replay_concurrent_keys_and_policy_conflicts_do_not_duplicate_or_rewrite(self):
        def attempt(_):return self.winners.create(self.anchor_project,self.winner_body(),principal=self.principal)
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(attempt,range(2)))
        self.assertEqual(len({v[0]['assessment_id'] for v in results}),1);self.assertEqual(sum(replay for _,replay in results),1)
        with self.store.transaction() as con:self.assertEqual(con.execute('SELECT count(*) FROM '+TABLES[0]).fetchone()[0],1);self.assertEqual(con.execute('SELECT count(*) FROM '+TABLES[1]).fetchone()[0],1)
        with self.assertRaisesRegex(WorkflowError,'IDEMPOTENCY_CONFLICT'):self.assess(policy=WinnerChannelPolicy(minimum_views=600))
    def test_explicit_mock_raw_boolean_model_and_expected_digest_are_enforced(self):
        with self.assertRaisesRegex(WorkflowError,'MOCK_ACK_REQUIRED'):self.assess(acknowledged_protocol_mock=False)
        with self.assertRaisesRegex(WorkflowError,'OBSERVATION_CHANGED'):self.assess(expected_result_sha256='f'*64)
        for change in ({'acknowledged_recommendation_only':1},{'acknowledged_protocol_mock':1},{'policy':{'minimum_peer_posts':True}},{'endpoint':'PRIVATE'},{'token':'PRIVATE'}):
            with self.assertRaises(ValidationError):self.winner_body(**change)
        payload=self.winner_body();object.__setattr__(payload,'acknowledged_protocol_mock',1)
        with self.assertRaisesRegex(WorkflowError,'FIELDS_INVALID'):self.winners.create(self.anchor_project,payload,principal=self.principal)
    def test_history_survives_source_edit_archive_expired_authority_and_removed_factories_without_network(self):
        value=self.assess();before=self.read_wire.copy()
        with self.store.transaction() as con:
            document=copy.deepcopy(self.project['document']);document['prompt']='EXPLICIT LATER EDIT'
            con.execute('UPDATE projects SET revision=revision+1,document=? WHERE id=?',(json.dumps(document),self.anchor_project));self.store.version(con,self.anchor_project)
        self.store.archive(self.anchor_project,self.store.get(self.anchor_project)['revision'],True)
        self.assertTrue(self.store.get(self.anchor_project)['archived'])
        self.accounts.factories.clear();self.service.factories.clear();self.clock[0]+=timedelta(days=2)
        self.assertEqual(self.winners.get(self.anchor_project,value['assessment_id']),value);self.assertEqual(NativeOfficialWinners(NativeOfficialAnalytics(self.service)).get(self.anchor_project,value['assessment_id']),value)
        self.assertEqual(self.read_wire,before)
        with self.assertRaises(WorkflowError):self.assess(request_key='explicit-expired-owner-new-winner-key')
    def test_source_rows_proofs_costs_features_and_rehashed_score_mutations_fail_closed(self):
        value=self.assess();identity=value['assessment_id']
        with self.store.transaction() as con:original=con.execute('SELECT snapshot_json,snapshot_sha256 FROM '+TABLES[0]+' WHERE assessment_id=?',(identity,)).fetchone();original=tuple(original)
        for mutate in (lambda s:s['assessment'].update(state='winner_candidate',score=100),lambda s:s['candidate']['metrics'].update(views=1000),
            lambda s:s.update(policy_sha256='a'*64),lambda s:s['assessment'].update(real_audience_observation=True),lambda s:s['candidate']['scope'].update(mock=False)):
            changed=json.loads(original[0]);mutate(changed)
            with self.store.transaction() as con:con.execute('UPDATE '+TABLES[0]+' SET snapshot_json=?,snapshot_sha256=? WHERE assessment_id=?',(json.dumps(changed),digest(changed),identity))
            with self.assertRaises(WorkflowError):self.winners.get(self.anchor_project,identity)
        with self.store.transaction() as con:con.execute('UPDATE '+TABLES[0]+' SET snapshot_json=?,snapshot_sha256=? WHERE assessment_id=?',(*original,identity))
        self.assertEqual(self.winners.get(self.anchor_project,identity),value)
        with self.store.transaction() as con:con.execute("UPDATE native_cost_operations SET paid=1 WHERE provider='official-youtube-analytics'")
        with self.assertRaises(WorkflowError):self.winners.get(self.anchor_project,identity)
    def test_wrong_project_and_scoped_bounded_cursors_do_not_leak_history(self):
        for i in range(3):self.assess(request_key='explicit-winner-page-key-'+str(i))
        first=self.winners.page(self.anchor_project,limit=2,publication=self.anchor_publication['publication_id']);self.assertEqual(len(first['items']),2);self.assertTrue(first['truncated'])
        self.assertEqual(len(self.winners.page(self.anchor_project,limit=2,publication=self.anchor_publication['publication_id'],cursor=first['next_cursor'])['items']),1)
        other=self.store.create('Other cohort fixture','','media')
        with self.assertRaisesRegex(WorkflowError,'NOT_FOUND'):self.winners.get(other['id'],first['items'][0]['assessment_id'])
        for change in ({'limit':True},{'limit':0},{'limit':101},{'cursor':'[]'},{'cursor':first['next_cursor'],'publication':None}):
            with self.assertRaisesRegex(WorkflowError,'PAGE_INVALID'):self.winners.page(self.anchor_project,**change)
        with self.assertRaisesRegex(WorkflowError,'PAGE_INVALID'):self.winners.page(other['id'],cursor=first['next_cursor'])
    def test_owner_rechecked_after_selection_and_source_transaction_reuse_never_nests(self):
        body=self.winner_body();wire=self.read_wire.copy();original=self.winners.context
        def changed(*args):
            result=original(*args);object.__setattr__(self.verifier.registry.tokens[self.principal.token_id],'enabled',False);return result
        with patch.object(self.winners,'context',side_effect=changed),self.assertRaisesRegex(WorkflowError,'OWNER_REQUIRED'):
            self.winners.create(self.anchor_project,body,principal=self.principal)
        with self.store.transaction() as con:self.assertEqual(con.execute('SELECT count(*) FROM '+TABLES[0]).fetchone()[0],0)
        self.assertEqual(wire,self.read_wire)
    def test_future_observation_unknown_niche_format_and_report_scope_remain_unclassified(self):
        self.clock[0]-=timedelta(seconds=1)
        with self.assertRaisesRegex(WorkflowError,'FUTURE_OBSERVATION'):self.assess()
        self.clock[0]+=timedelta(seconds=1)
        with self.store.transaction() as con:candidate=self.winners.proof(con,self.anchor_project,self.anchor['sync_id'])
        for field,value in [('niche',None),('duration_bucket',None),('format',{'width':True,'height':1920,'video_codec':'h264'})]:
            incomplete=copy.deepcopy(candidate);incomplete['scope'][field]=value;self.assertFalse(self.winners.known_scope(incomplete))
            a=self.winners.assessment(incomplete,[],WinnerChannelPolicy(),False);self.assertEqual(a['state'],'insufficient_data')
        for field,value in [('query',{'start_date':'2026-09-01','end_date':'2026-10-07','include_revenue':False}),('source_kind','official_provider'),('mock',False),('target_binding_sha256','f'*64),('niche','real_estate')]:
            peer=copy.deepcopy(candidate);peer['remote_post_id']='FIXTURE9999';peer['scope'][field]=value;self.assertFalse(self.winners.compatible(candidate,peer))
    def test_qualified_protocol_mock_different_niche_and_report_peers_are_excluded_without_fallback(self):
        self.peer(2,reference='property-reference@1');self.peer(3,query={'start_date':'2026-09-01','end_date':'2026-10-07'})
        self.project=self.store.get(self.anchor_project);self.job=self.store.get_job(self.anchor_job);self.completed=self.anchor_publication
        self.anchor=self.run_collection(request_key='explicit-incompatible-cohort-anchor-refresh');value=self.assess()
        self.assertEqual(value['peer_count'],0);self.assertEqual(value['assessment']['state'],'insufficient_data');self.assertGreaterEqual(value['snapshot']['excluded_rows']['incompatible_scope_or_anchor'],3)
    def test_peer_refresh_ties_use_latest_saved_result_and_duplicate_remote_posts_do_not_inflate_baseline(self):
        peer=self.peer(2);self.metric_values=[1000,30,1.8,30,3,6,6];new=self.run_collection(request_key='explicit-latest-peer-report-key')
        self.project=self.store.get(self.anchor_project);self.job=self.store.get_job(self.anchor_job);self.completed=self.anchor_publication
        self.anchor=self.run_collection(request_key='explicit-anchor-after-peer-refresh-key');value=self.assess();self.assertEqual(value['peer_count'],1)
        self.assertEqual(value['snapshot']['peers'][0]['result_snapshot_id'],new['result_snapshot_id']);self.assertNotEqual(peer['result_snapshot_id'],new['result_snapshot_id'])
        self.assertEqual(value['snapshot']['excluded_rows']['duplicate_remote_post'],1);self.assertEqual(value['assessment']['state'],'insufficient_data')
    def test_backup_count_has_immutable_assessment_events_without_active_operations(self):
        self.assess();status=database_status(self.store.db);self.assertEqual(status['counts'][TABLES[0]],1);self.assertEqual(status['counts'][TABLES[1]],1);self.assertEqual(status['active_operations'],0)
    def test_frozen_configuration_and_cold_import_need_no_orm_or_provider_sdk(self):
        original=self.winners.workspace;self.winners.workspace='wsp_foreign'
        with self.assertRaisesRegex(WorkflowError,'CONFIGURATION_CHANGED'):self.assess()
        self.winners.workspace=original
        code="import sys;from services.windows_native.official_winners import NativeOfficialWinners;from app.analytics_channel_policy import WinnerChannelPolicy;assert 'sqlalchemy' not in sys.modules;assert WinnerChannelPolicy().minimum_peer_posts==5;print('PURE_NATIVE_WINNER_IMPORT_PASS')"
        result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True);self.assertEqual(result.returncode,0,result.stderr);self.assertIn('PURE_NATIVE_WINNER_IMPORT_PASS',result.stdout)

if __name__=='__main__':unittest.main()
