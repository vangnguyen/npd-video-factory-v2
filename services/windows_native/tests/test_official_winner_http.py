"""Owned signed HTTP only; nonplayable media and synthetic provider inputs."""
import copy,json,unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from services.windows_native.tests.test_official_analytics_http import OfficialAnalyticsHTTPFixture
from services.windows_native.official_winners import NativeOfficialWinners,TABLES
from services.windows_native.official_winner_models import Create
from services.windows_native.contracts import digest
from services.windows_native.server import Handler

class OfficialWinnerHTTPFixture(OfficialAnalyticsHTTPFixture):
    def setUp(self):
        super().setUp();self.server.official_winners=NativeOfficialWinners(self.analytics);self.winners=self.server.official_winners
        value=self.create_http();assert self.server.runner.run_one()
        self.observation=self.request('GET',self.base+'/'+value['sync_id'])[1];self.winner_base='/api/projects/'+self.project['id']+'/official-winners'
    def winner_body(self,**changes):
        return Create.model_validate({'sync_id':self.observation['sync_id'],'expected_result_sha256':digest(self.observation['result']),
            'acknowledged_recommendation_only':True,'acknowledged_protocol_mock':True,'request_key':'explicit-signed-winner-assessment-key',**changes}).model_dump(mode='json')
    def create_winner(self,**changes):
        status,value,headers=self.request('POST',self.winner_base,self.winner_body(**changes));assert status==200,value;assert headers['Cache-Control']=='no-store';return value

class OfficialWinnerHTTPTests(OfficialWinnerHTTPFixture,unittest.TestCase):
    def test_signed_assessment_source_hash_and_config_are_local_only_no_runner_operation(self):
        wire=copy.deepcopy(self.read_wire);costs=self.analytics.costs.summary(self.project['id']);project=self.server.store.get(self.project['id'])
        status,config,headers=self.request('GET','/api/connections/official-winners');self.assertEqual(status,200);self.assertEqual(config['maximum_candidate_rows'],500)
        self.assertFalse(config['automatic_assessment']);self.assertFalse(config['provider_calls_enabled']);self.assertEqual(headers['Cache-Control'],'no-store')
        status,source,headers=self.request('GET',self.winner_base+'/source/'+self.observation['sync_id']);self.assertEqual(status,200)
        self.assertEqual(source['result_sha256'],digest(self.observation['result']));self.assertEqual(source['consent_sha256'],self.observation['snapshot_sha256'])
        self.assertTrue(source['mock']);self.assertFalse(source['real_audience_observation']);self.assertFalse(source['automatic_action']);self.assertEqual(headers['Cache-Control'],'no-store')
        self.server.runner.wake.clear();value=self.create_winner();self.assertEqual(value['assessment']['state'],'insufficient_data');self.assertIsNone(value['assessment']['score'])
        self.assertEqual(value['peer_count'],0);self.assertTrue(value['recommendation_only']);self.assertFalse(self.server.runner.wake.is_set());self.assertFalse(self.server.runner.run_one())
        self.assertEqual(wire,self.read_wire);self.assertEqual(costs,self.analytics.costs.summary(self.project['id']));self.assertEqual(project,self.server.store.get(self.project['id']))
    def test_roles_and_csrf_are_checked_before_reading_body(self):
        for role in ('editor','reviewer','viewer'):
            self.account(role)
            with patch.object(Handler,'read_body',side_effect=AssertionError('Forbidden body read')):self.assertEqual(self.request('POST',self.winner_base,{})[0],403)
            self.assertEqual(self.request('GET','/api/connections/official-winners')[0],403);self.assertEqual(self.request('GET',self.winner_base)[0],200)
            self.assertEqual(self.request('GET',self.winner_base+'/source/'+self.observation['sync_id'])[0],200)
        self.account('owner')
        with patch.object(Handler,'read_body',side_effect=AssertionError('Missing CSRF body read')):self.assertEqual(self.request('POST',self.winner_base,{}, {'X-VF-CSRF':''})[0],403)
        self.assertEqual(len(self.read_wire),3)
    def test_strict_policy_acknowledgements_and_observation_hash_never_create_on_invalid_request(self):
        body=self.winner_body()
        for change in ({'acknowledged_recommendation_only':1},{'acknowledged_protocol_mock':1},{'policy':{'minimum_peer_posts':True}},
            {'policy':{'weights':{'ctr':1}}},{'token':'NEVER'},{'automatic_action':True},{'endpoint':'https://untrusted.invalid'}):
            self.assertEqual(self.request('POST',self.winner_base,{**body,**change})[0],400)
        self.assertEqual(self.request('POST',self.winner_base,{**body,'acknowledged_protocol_mock':False})[0],409)
        self.assertEqual(self.request('POST',self.winner_base,{**body,'expected_result_sha256':'f'*64})[0],409)
        with self.server.store.transaction() as con:self.assertEqual(con.execute('SELECT count(*) FROM '+TABLES[0]).fetchone()[0],0)
        self.assertEqual(len(self.read_wire),3)
    def test_exact_replay_has_same_frozen_assessment_and_policy_conflicts_never_overwrite(self):
        value=self.create_winner();self.assertFalse(value.pop('idempotent_replay'));again=self.create_winner();self.assertTrue(again.pop('idempotent_replay'));self.assertEqual(again,value)
        self.assertEqual(self.request('GET',self.winner_base+'/'+value['assessment_id'])[1],value)
        body=self.winner_body(policy={'minimum_views':600});self.assertEqual(self.request('POST',self.winner_base,body)[0],409)
        with self.server.store.transaction() as con:self.assertEqual(con.execute('SELECT count(*) FROM '+TABLES[0]).fetchone()[0],1)
        self.assertEqual(len(self.read_wire),3)
    def test_bounded_scoped_pages_and_sources_reject_foreign_queries_and_ids(self):
        for i in range(3):self.create_winner(request_key='explicit-signed-winner-page-key-'+str(i))
        pub=self.completed['publication_id'];first=self.request('GET',self.winner_base+'?limit=2&publication='+pub)[1];self.assertTrue(first['truncated']);self.assertEqual(len(first['items']),2)
        self.assertEqual(len(self.request('GET',self.winner_base+'?limit=2&publication='+pub+'&cursor='+first['next_cursor'])[1]['items']),1)
        other=self.server.store.create('Other winner fixture','','media');foreign='/api/projects/'+other['id']+'/official-winners'
        self.assertEqual(self.request('GET',foreign+'/'+first['items'][0]['assessment_id'])[0],404)
        self.assertEqual(self.request('GET',foreign+'/source/'+self.observation['sync_id'])[0],404)
        self.assertEqual(self.request('GET',foreign+'?publication='+pub+'&cursor='+first['next_cursor'])[0],400)
        for query in ('?limit=0','?limit=101','?limit=1&limit=2','?cursor=[]','?publication=npub_'+'a'*32,'?token=NEVER'):
            self.assertEqual(self.request('GET',self.winner_base+query)[0],400)
        for path in ('/api/connections/official-winners',self.winner_base+'/source/'+self.observation['sync_id'],self.winner_base+'/'+first['items'][0]['assessment_id']):
            self.assertEqual(self.request('GET',path+'?token=NEVER')[0],400)
        self.assertEqual(len(self.read_wire),3)
    def test_history_qualified_after_edit_archive_provider_removal_and_expired_original_owner(self):
        value=self.create_winner();value.pop('idempotent_replay');wire=self.read_wire.copy()
        with self.server.store.transaction() as con:
            doc=copy.deepcopy(self.project['document']);doc['prompt']='LATER EXPLICIT FIXTURE EDIT'
            con.execute('UPDATE projects SET revision=revision+1,document=? WHERE id=?',(json.dumps(doc),self.project['id']));self.server.store.version(con,self.project['id'])
        self.server.store.archive(self.project['id'],self.server.store.get(self.project['id'])['revision'],True)
        self.server.official_accounts.factories.clear();self.server.official_publications.factories.clear();self.clock[0]+=timedelta(days=2)
        self.account('viewer');self.assertEqual(self.request('GET',self.winner_base+'/'+value['assessment_id'])[1],value)
        self.assertEqual(self.request('GET',self.winner_base+'/source/'+self.observation['sync_id'])[0],200);self.assertEqual(wire,self.read_wire)
        self.assertEqual(self.request('POST',self.winner_base,self.winner_body(request_key='explicit-new-forbidden-winner-key'))[0],403)
    def test_unqualified_queued_observation_and_rehashed_source_mutation_fail_closed(self):
        queued=self.create_http(request_key='explicit-uncollected-winner-source-key');body=self.winner_body(sync_id=queued['sync_id'])
        self.assertEqual(self.request('POST',self.winner_base,body)[0],409);self.assertEqual(self.request('GET',self.winner_base+'/source/'+queued['sync_id'])[0],409)
        value=self.create_winner()
        with self.server.store.transaction() as con:con.execute("UPDATE native_cost_operations SET paid=1 WHERE provider='official-youtube-analytics'")
        self.assertEqual(self.request('GET',self.winner_base+'/'+value['assessment_id'])[0],409);self.assertEqual(len(self.read_wire),3)
    def test_studio_module_card_and_parent_selection_binding_are_served(self):
        root=Path(__file__).resolve().parents[3]/'apps'/'studio-web'
        for name in ('native-official-winners.mjs','native-official-analytics.mjs','native.mjs','native.html','shot-studio.mjs'):
            status,body,_=self.request('GET','/'+name);self.assertEqual(status,200);self.assertEqual(body,(root/name).read_bytes())
        self.assertIn('native-official-winners-card',(root/'native.html').read_text(encoding='utf-8'));self.assertIn('officialAnalyticsUI.currentBinding()',(root/'native.mjs').read_text(encoding='utf-8'))
        self.assertEqual(len(self.read_wire),3)

if __name__=='__main__':unittest.main()
