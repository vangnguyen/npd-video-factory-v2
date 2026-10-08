"""Owned signed local learning controls; provider/media/account input is synthetic."""
import copy,json,unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from services.windows_native.tests.test_official_winner_http import OfficialWinnerHTTPFixture
from services.windows_native.tests import test_official_publications as review_fixture
from services.windows_native.tests.test_publications import render_fixture
from services.windows_native.official_learning import NativeOfficialLearning,TABLES
from services.windows_native.official_learning_models import Create
from services.windows_native.channel_profiles import select
from services.windows_native.contracts import digest
from services.windows_native.server import Handler

class OfficialLearningHTTPFixture(OfficialWinnerHTTPFixture):
    def configured_render(self,store,**kwargs):
        project=kwargs.pop('project',None) or store.create('EXPLICIT SYNTHETIC LEARNING HTTP FIXTURE','','media',channel_profile=select('ai-education-reference@1'))
        return render_fixture(store,project=project,**kwargs)
    def setUp(self):
        with patch.object(review_fixture,'render_fixture',side_effect=self.configured_render):super().setUp()
        self.server.official_learning=NativeOfficialLearning(self.winners);self.learning=self.server.official_learning
        self.assessment=self.create_winner();self.assessment.pop('idempotent_replay');self.learning_base='/api/projects/'+self.project['id']+'/official-learning'
    def learning_body(self,**changes):
        return Create.model_validate({'assessment_id':self.assessment['assessment_id'],'expected_assessment_sha256':self.assessment['snapshot_sha256'],
            'acknowledged_recommendation_only':True,'acknowledged_protocol_mock':True,'request_key':'explicit-signed-learning-snapshot-key',**changes}).model_dump(mode='json')
    def create_learning(self,**changes):
        status,value,headers=self.request('POST',self.learning_base,self.learning_body(**changes));assert status==200,value;assert headers['Cache-Control']=='no-store';return value

class OfficialLearningHTTPTests(OfficialLearningHTTPFixture,unittest.TestCase):
    def test_signed_config_source_hash_and_sparse_learning_are_local_only_no_runner_action(self):
        wire=self.read_wire.copy();project=self.server.store.get(self.project['id']);costs=self.analytics.costs.summary(self.project['id'])
        status,config,headers=self.request('GET','/api/connections/official-learning');self.assertEqual(status,200);self.assertEqual(len(config['dimensions']),7)
        self.assertFalse(config['automatic_learning']);self.assertFalse(config['provider_calls_enabled']);self.assertEqual(headers['Cache-Control'],'no-store')
        status,source,headers=self.request('GET',self.learning_base+'/source/'+self.assessment['assessment_id']);self.assertEqual(status,200)
        self.assertEqual(source['assessment_sha256'],self.assessment['snapshot_sha256']);self.assertEqual(source['candidate_sha256'],digest(self.assessment['snapshot']['candidate']))
        self.assertTrue(source['qualified_scope']);self.assertTrue(source['mock']);self.assertFalse(source['real_audience_observation']);self.assertEqual(headers['Cache-Control'],'no-store')
        self.server.runner.wake.clear();value=self.create_learning();self.assertEqual(value['status'],'insufficient_data');self.assertEqual(value['observation_count'],0)
        self.assertFalse(self.server.runner.wake.is_set());self.assertFalse(self.server.runner.run_one());self.assertEqual(wire,self.read_wire)
        self.assertEqual(project,self.server.store.get(self.project['id']));self.assertEqual(costs,self.analytics.costs.summary(self.project['id']))
    def test_roles_and_csrf_are_checked_before_reading_body_and_viewer_sources_are_readable(self):
        for role in ('editor','reviewer','viewer'):
            self.account(role)
            with patch.object(Handler,'read_body',side_effect=AssertionError('Forbidden body read')):self.assertEqual(self.request('POST',self.learning_base,{})[0],403)
            self.assertEqual(self.request('GET','/api/connections/official-learning')[0],403);self.assertEqual(self.request('GET',self.learning_base)[0],200)
            self.assertEqual(self.request('GET',self.learning_base+'/source/'+self.assessment['assessment_id'])[0],200)
        self.account('owner')
        with patch.object(Handler,'read_body',side_effect=AssertionError('Missing CSRF body read')):self.assertEqual(self.request('POST',self.learning_base,{}, {'X-VF-CSRF':''})[0],403)
        self.assertEqual(len(self.read_wire),3)
    def test_strict_policy_mock_recommendation_digest_and_extra_fields_never_create_invalid_request(self):
        body=self.learning_body()
        for change in ({'acknowledged_recommendation_only':1},{'acknowledged_protocol_mock':1},{'policy':{'minimum_group_posts':True}},
            {'policy':{'maximum_posts':5}},{'policy':{'minimum_group_posts':50,'minimum_control_posts':50,'maximum_posts':99}},
            {'token':'NEVER'},{'automatic_action':True},{'endpoint':'https://untrusted.invalid'}):self.assertEqual(self.request('POST',self.learning_base,{**body,**change})[0],400)
        self.assertEqual(self.request('POST',self.learning_base,{**body,'acknowledged_protocol_mock':False})[0],409)
        self.assertEqual(self.request('POST',self.learning_base,{**body,'expected_assessment_sha256':'f'*64})[0],409)
        with self.server.store.transaction() as con:self.assertEqual(con.execute('SELECT count(*) FROM '+TABLES[0]).fetchone()[0],0)
        self.assertEqual(len(self.read_wire),3)
    def test_exact_replay_returns_original_snapshot_and_policy_conflict_does_not_overwrite(self):
        first=self.create_learning();self.assertFalse(first.pop('idempotent_replay'));again=self.create_learning();self.assertTrue(again.pop('idempotent_replay'));self.assertEqual(first,again)
        self.assertEqual(self.request('GET',self.learning_base+'/'+first['learning_id'])[1],first)
        self.assertEqual(self.request('POST',self.learning_base,self.learning_body(policy={'minimum_score_difference':20}))[0],409)
        with self.server.store.transaction() as con:self.assertEqual(con.execute('SELECT count(*) FROM '+TABLES[0]).fetchone()[0],1)
        self.assertEqual(len(self.read_wire),3)
    def test_scoped_bounded_pages_sources_unknown_or_duplicate_queries_and_foreign_ids_are_refused(self):
        for i in range(3):self.create_learning(request_key='explicit-signed-learning-page-key-'+str(i))
        pub=self.completed['publication_id'];first=self.request('GET',self.learning_base+'?limit=2&publication='+pub)[1];self.assertTrue(first['truncated']);self.assertEqual(len(first['items']),2)
        self.assertEqual(len(self.request('GET',self.learning_base+'?limit=2&publication='+pub+'&cursor='+first['next_cursor'])[1]['items']),1)
        other=self.server.store.create('Other learning HTTP fixture','','media');foreign='/api/projects/'+other['id']+'/official-learning'
        self.assertEqual(self.request('GET',foreign+'/'+first['items'][0]['learning_id'])[0],404);self.assertEqual(self.request('GET',foreign+'/source/'+self.assessment['assessment_id'])[0],404)
        self.assertEqual(self.request('GET',foreign+'?publication='+pub+'&cursor='+first['next_cursor'])[0],400)
        for query in ('?limit=0','?limit=101','?limit=1&limit=2','?cursor=[]','?publication=npub_'+'a'*32,'?token=NEVER'):self.assertEqual(self.request('GET',self.learning_base+query)[0],400)
        for path in ('/api/connections/official-learning',self.learning_base+'/source/'+self.assessment['assessment_id'],self.learning_base+'/'+first['items'][0]['learning_id']):self.assertEqual(self.request('GET',path+'?token=NEVER')[0],400)
        self.assertEqual(len(self.read_wire),3)
    def test_original_history_survives_edit_archive_provider_removal_and_expired_original_owner(self):
        first=self.create_learning();first.pop('idempotent_replay');wire=self.read_wire.copy()
        with self.server.store.transaction() as con:
            doc=copy.deepcopy(self.project['document']);doc['prompt']='EXPLICIT LATER EDIT'
            con.execute('UPDATE projects SET revision=revision+1,document=? WHERE id=?',(json.dumps(doc),self.project['id']));self.server.store.version(con,self.project['id'])
        self.server.store.archive(self.project['id'],self.server.store.get(self.project['id'])['revision'],True)
        self.server.official_accounts.factories.clear();self.server.official_publications.factories.clear();self.clock[0]+=timedelta(days=2);self.account('viewer')
        self.assertEqual(self.request('GET',self.learning_base+'/'+first['learning_id'])[1],first);self.assertEqual(self.request('GET',self.learning_base+'/source/'+self.assessment['assessment_id'])[0],200)
        self.assertEqual(self.request('POST',self.learning_base,self.learning_body(request_key='explicit-forbidden-new-learning-key'))[0],403);self.assertEqual(wire,self.read_wire)
    def test_rehashed_aggregation_or_source_cost_tampering_fails_closed_without_new_read(self):
        first=self.create_learning();identity=first['learning_id'];snapshot=copy.deepcopy(first['snapshot']);snapshot['dimensions'][0]['state']='recommendations_available'
        with self.server.store.transaction() as con:con.execute('UPDATE '+TABLES[0]+' SET snapshot_json=?,snapshot_sha256=? WHERE learning_id=?',(json.dumps(snapshot),digest(snapshot),identity))
        self.assertEqual(self.request('GET',self.learning_base+'/'+identity)[0],409)
        with self.server.store.transaction() as con:con.execute("UPDATE native_cost_operations SET paid=1 WHERE provider='official-youtube-analytics'")
        self.assertEqual(self.request('GET',self.learning_base+'/source/'+self.assessment['assessment_id'])[0],409);self.assertEqual(len(self.read_wire),3)
    def test_all_learning_studio_files_and_selected_winner_binding_are_served_exactly(self):
        root=Path(__file__).resolve().parents[3]/'apps'/'studio-web'
        for name in ('native-official-learning.mjs','native-official-winners.mjs','native.mjs','native.html','shot-studio.mjs'):
            status,body,_=self.request('GET','/'+name);self.assertEqual(status,200);self.assertEqual(body,(root/name).read_bytes())
        self.assertIn('native-official-learning-card',(root/'native.html').read_text(encoding='utf-8'));self.assertIn('officialWinnerUI.currentBinding()',(root/'native.mjs').read_text(encoding='utf-8'))
        self.assertEqual(len(self.read_wire),3)

if __name__=='__main__':unittest.main()
