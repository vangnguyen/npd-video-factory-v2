"""Signed synthetic source projection; no provider, browser or Owner acceptance."""
import copy, json, unittest, uuid
from datetime import timedelta
from unittest.mock import patch
from services.windows_native.tests.test_official_learning_http import OfficialLearningHTTPFixture
from services.windows_native.qualified_learning_feedback import NativeQualifiedLearningFeedback, Create
from services.windows_native.contracts import digest
from services.windows_native.server import Handler

BASE='/api/trends/learning/qualified'

class QualifiedFeedbackHTTPFixture(OfficialLearningHTTPFixture):
    def setUp(self):
        super().setUp()
        self.feedback=NativeQualifiedLearningFeedback(self.learning,self.server.trends)
        self.server.qualified_learning=self.feedback;self.server.trends.qualified_learning=self.feedback
        self.server.intelligence.qualified_learning=self.feedback;self.server.store.qualified_learning=self.feedback
        self.learned=self.create_learning();self.learned.pop('idempotent_replay')
        self.server.runner.wake.clear()

    def qualified_body(self,**changes):
        return Create.model_validate({'project_id':self.project['id'],'learning_id':self.learned['learning_id'],
            'expected_learning_sha256':self.learned['snapshot_sha256'],'channel_profile_ref':'ai-education-reference@1',
            'acknowledged_recommendation_only':True,'acknowledged_protocol_mock':True,
            'request_key':'explicit-signed-qualified-learning-key',**changes}).model_dump(mode='json')

    def project_feedback(self,**changes):
        status,value,headers=self.request('POST',BASE,self.qualified_body(**changes))
        assert status==200,value;assert headers['Cache-Control']=='no-store';return value

class QualifiedFeedbackHTTPTests(QualifiedFeedbackHTTPFixture,unittest.TestCase):
    def test_signed_projection_source_dimensions_history_and_templates_are_local_only(self):
        wire=self.read_wire.copy();before=self.server.store.get(self.project['id']);costs=self.analytics.costs.summary(self.project['id'])
        self.server.runner.wake.clear();value=self.project_feedback();record=value['record']
        self.assertEqual(value['schema_version'],'native-qualified-learning-feedback-result-v1');self.assertEqual(value['record_sha256'],digest(record))
        self.assertFalse(value['idempotent_replay']);self.assertTrue(record['payload']['mock']);self.assertFalse(record['payload']['real_audience_observation'])
        self.assertEqual(record['payload']['source_binding']['learning_sha256'],self.learned['snapshot_sha256'])
        self.assertEqual(record['payload']['recommendations'],self.learned['dimensions']);self.assertFalse(value['automatic_application'])
        self.assertEqual(self.request('GET','/api/trends/learning')[1]['items'],[record])
        detail=self.request('GET','/api/trends/records/'+record['id']);self.assertEqual(detail[0],200);self.assertEqual(detail[1]['record'],record)
        status,templates,headers=self.request('GET',BASE+'/'+record['id']+'/templates');self.assertEqual(status,200)
        self.assertEqual(templates['suggestions'],[]);self.assertEqual(templates['source_binding'],record['payload']['source_binding']);self.assertFalse(templates['automatic_application'])
        self.assertFalse(self.server.runner.wake.is_set());self.assertEqual(self.read_wire,wire);self.assertEqual(self.server.store.get(self.project['id']),before)
        self.assertEqual(self.analytics.costs.summary(self.project['id']),costs);self.assertEqual(headers['Cache-Control'],'no-store')

    def test_owner_and_csrf_are_checked_before_projection_body_and_viewers_read_history(self):
        value=self.project_feedback()
        for role in ('viewer','editor','reviewer'):
            self.account(role)
            with patch.object(Handler,'read_body',side_effect=AssertionError('Forbidden body read')):self.assertEqual(self.request('POST',BASE,{})[0],403)
            self.assertEqual(self.request('GET',BASE+'/'+value['record']['id']+'/templates')[0],200)
        self.account('owner')
        with patch.object(Handler,'read_body',side_effect=AssertionError('Missing CSRF body read')):
            self.assertEqual(self.request('POST',BASE,{}, {'X-VF-CSRF':''})[0],403)

    def test_raw_mock_recommendation_extra_fields_and_changed_digest_are_rejected(self):
        body=self.qualified_body()
        for changes in ({'acknowledged_recommendation_only':1},{'acknowledged_protocol_mock':1},{'automatic_application':True},
            {'token':'NEVER'},{'request_key':'unsafe/key-with-slash'},{'scope':{'mock':False}}):
            self.assertEqual(self.request('POST',BASE,{**body,**changes})[0],400)
        for changes in ({'acknowledged_protocol_mock':False},{'expected_learning_sha256':'f'*64},{'platform':'tiktok'}):
            self.assertEqual(self.request('POST',BASE,{**body,**changes})[0],409)
        self.assertEqual(self.request('GET','/api/trends/learning')[1]['items'],[])

    def test_exact_key_replay_and_changed_request_conflict_preserve_one_projection(self):
        first=self.project_feedback();second=self.project_feedback();self.assertTrue(second['idempotent_replay']);self.assertEqual(first['record'],second['record'])
        changed=self.qualified_body(expected_learning_sha256='f'*64);self.assertEqual(self.request('POST',BASE,changed)[0],409)
        self.assertEqual(self.request('GET','/api/trends/learning')[1]['items'],[first['record']])

    def test_foreign_project_learning_identity_queries_and_record_scope_fail_closed(self):
        other=self.server.store.create('Foreign source fixture','','media')
        self.assertEqual(self.request('POST',BASE,self.qualified_body(project_id=other['id']))[0],404)
        self.assertEqual(self.request('POST',BASE,self.qualified_body(learning_id='nols_'+'f'*32))[0],404)
        value=self.project_feedback();path=BASE+'/'+value['record']['id']+'/templates'
        for query in ('?limit=1','?a=x&a=y','?mock=false'):self.assertEqual(self.request('GET',path+query)[0],400)
        self.assertEqual(self.request('GET',BASE+'/'+'f'*32+'/templates')[0],404)

    def test_archived_history_after_provider_removal_and_original_owner_expiry_is_exact_for_viewer(self):
        value=self.project_feedback();record=value['record'];wire=self.read_wire.copy();before=self.server.store.get(self.project['id'])
        self.server.store.archive(self.project['id'],before['revision'],True);self.accounts.factories.clear();self.server.official_publications.factories.clear()
        self.clock[0]+=timedelta(days=2);self.account('viewer')
        self.assertEqual(self.request('GET','/api/trends/records/'+record['id'])[1]['record'],record)
        self.assertEqual(self.request('GET',BASE+'/'+record['id']+'/templates')[1]['projection_sha256'],digest(record));self.assertEqual(self.read_wire,wire)

    def test_rehashed_projection_or_original_response_cost_refuses_scoped_history(self):
        value=self.project_feedback();record=value['record'];changed=copy.deepcopy(record);changed['payload']['consumers']['idea_engine'][0]['missing_feature_posts']=999
        with self.feedback.store.transaction() as con:
            raw=json.dumps(changed);con.execute('UPDATE records SET document=? WHERE id=?',(raw,record['id']))
            con.execute('UPDATE versions SET document=?,sha256=? WHERE id=? AND version=1',(raw,digest(changed),record['id']))
        self.assertEqual(self.request('GET','/api/trends/records/'+record['id'])[0],409)
        changed=copy.deepcopy(record);changed['payload'].pop('schema_version')
        with self.feedback.store.transaction() as con:
            raw=json.dumps(changed);con.execute('UPDATE records SET document=? WHERE id=?',(raw,record['id']))
            con.execute('UPDATE versions SET document=?,sha256=? WHERE id=? AND version=1',(raw,digest(changed),record['id']))
        self.assertEqual(self.request('GET','/api/trends/learning')[0],409)
        with self.feedback.store.transaction() as con:
            raw=json.dumps(record);con.execute('UPDATE records SET document=? WHERE id=?',(raw,record['id']))
            con.execute('UPDATE versions SET document=?,sha256=? WHERE id=? AND version=1',(raw,digest(record),record['id']))
        with self.server.store.transaction() as con:con.execute("UPDATE native_cost_operations SET paid=1 WHERE provider='official-youtube-analytics'")
        self.assertEqual(self.request('GET',BASE+'/'+record['id']+'/templates')[0],409)

    def test_legacy_learning_and_current_registry_separation_preserve_existing_contract(self):
        value=self.project_feedback();self.server.trends.qualified_learning=None
        self.assertEqual(self.request('GET','/api/trends/records/'+value['record']['id'])[0],409)
        self.assertEqual(self.request('GET',self.learning_base+'/'+self.learned['learning_id'])[1],self.learned)
        self.assertFalse(self.server.runner.wake.is_set())

if __name__=='__main__':unittest.main()
