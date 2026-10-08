"""Frozen scheduled metadata/current-time initial admission; explicit mock wire only."""
from datetime import datetime,timedelta,timezone
import json,unittest
import httpx
from services.windows_native.tests.test_official_publication_dispatch import OfficialDispatchFixture
from services.windows_native.tests import test_official_publication_worker as worker_fixture
from services.windows_native.official_publication_worker import NativeOfficialPublicationWorker
from services.windows_native.official_publication_models import Action,Create,Renew
from services.windows_native.contracts import WorkflowError,digest
from app.publishing_models import PublicationMetadata

class OfficialMetadataTests(OfficialDispatchFixture,unittest.TestCase):
    step=worker_fixture.OfficialWorkerTests.step
    poll=worker_fixture.OfficialWorkerTests.poll
    upload=worker_fixture.OfficialWorkerTests.upload
    def setUp(self):
        super().setUp();self.wire=[];self.ack=0;self.processing='processed';self.privacy='private';self.mode=None;self.observed_schedule=None;self.init_bodies=[]
        self.client.transport.handler=self.response;self.worker=NativeOfficialPublicationWorker(self.service,self.vault)
    def response(self,request):
        if request.method=='POST':self.init_bodies.append(json.loads(request.content))
        response=worker_fixture.OfficialWorkerTests.response(self,request)
        if request.url.path=='/youtube/v3/videos' and self.observed_schedule is not None:
            value=response.json();value['items'][0]['status']['publishAt']=self.observed_schedule.astimezone(timezone.utc).isoformat();return httpx.Response(200,json=value)
        return response
    def scheduled(self,*,seconds=120,approve=True,**changes):
        self.service.cancel(self.project['id'],self.value['publication_id'],Action(expected_snapshot_sha256=self.value['snapshot_sha256']),principal=self.principal)
        self.at=self.clock[0]+timedelta(seconds=seconds);metadata={**self.parent['snapshot']['request']['metadata'],'scheduled_at':self.at.isoformat(),**changes}
        self.value=self.create(self.body(metadata=metadata,request_key='explicit-scheduled-metadata-fixture-key'))
        if approve:self.approve(self.value)
        return self.value
    def test_explicit_metadata_freezes_review_and_never_changes_parent_project_or_approval(self):
        before=self.store.get(self.project['id']);parent=self.publications.get(self.project['id'],self.parent['publication_id'])
        value=self.scheduled(title='Explicit revised publication title',approve=False)
        self.assertEqual(value['snapshot']['metadata_source'],'explicit_owner_request');self.assertEqual(value['snapshot']['reviewed_at'],self.clock[0].isoformat())
        self.assertEqual(value['snapshot']['metadata']['title'],'Explicit revised publication title');self.assertIsNone(value['approval_id']);self.assertFalse(value['published'])
        self.assertEqual(self.store.get(self.project['id']),before);self.assertEqual(self.publications.get(self.project['id'],self.parent['publication_id']),parent)
        self.assertEqual(self.wire,[]);self.approve(value);self.step()
        self.assertEqual(self.init_bodies[0]['snippet']['title'],value['snapshot']['metadata']['title'])
        self.assertEqual(self.init_bodies[0]['status']['publishAt'],self.at.isoformat().replace('+00:00','Z'))
        self.assertEqual(sum(r['method']=='POST' for r in self.wire),1)
    def test_future_private_processing_is_pending_until_observed_public_release(self):
        self.scheduled();self.observed_schedule=self.at;self.upload();pending=self.poll()
        self.assertEqual(pending['status'],'queued');self.assertIsNone(pending['receipt']);self.assertFalse(pending['published'])
        self.clock[0]+=timedelta(seconds=121);self.privacy='public';self.observed_schedule=None
        completed=self.poll();self.assertEqual(completed['status'],'completed');self.assertTrue(completed['mock_publication_complete']);self.assertFalse(completed['published'])
        self.assertEqual(datetime.fromisoformat(completed['snapshot']['metadata']['scheduled_at'].replace('Z','+00:00')),self.at)
        self.assertEqual(sum(r['method']=='POST' for r in self.wire),1)
        with self.store.transaction() as con:self.assertEqual(con.execute('SELECT count(*) FROM native_official_publish_processing').fetchone()[0],2)
    def test_wrong_future_schedule_cannot_produce_a_receipt(self):
        self.scheduled();self.observed_schedule=self.at+timedelta(seconds=1);self.upload();blocked=self.poll()
        self.assertEqual(blocked['status'],'review_required');self.assertEqual(blocked['failure_code'],'YOUTUBE_SCHEDULE_UNCONFIRMED_REVIEW_REQUIRED');self.assertIsNone(blocked['receipt'])
    def test_private_video_after_schedule_is_not_assumed_public(self):
        self.scheduled();self.upload();self.clock[0]+=timedelta(seconds=121);blocked=self.poll()
        self.assertEqual(blocked['status'],'review_required');self.assertEqual(blocked['failure_code'],'YOUTUBE_SCHEDULE_RELEASE_UNCONFIRMED_REVIEW_REQUIRED');self.assertFalse(blocked['published'])
    def test_overdue_prepared_review_and_grant_cannot_approve_renew_or_send(self):
        self.scheduled(approve=False);self.clock[0]+=timedelta(seconds=61)
        with self.assertRaisesRegex(WorkflowError,'FUTURE_SCHEDULE_MARGIN_REQUIRED'):self.approve(self.value)
        self.assertEqual(self.wire,[])
        self.clock[0]-=timedelta(seconds=61);self.approve(self.value);self.clock[0]+=timedelta(seconds=121)
        with self.assertRaisesRegex(WorkflowError,'FUTURE_SCHEDULE_MARGIN_REQUIRED'):self.step()
        body=Renew(expected_snapshot_sha256=self.value['snapshot_sha256'],expected_dispatch_version=self.state()['version'],acknowledged_official_publication=True,request_key='explicit-overdue-renewal-key')
        with self.assertRaisesRegex(WorkflowError,'FUTURE_SCHEDULE_MARGIN_REQUIRED'):self.service.renew(self.project['id'],self.value['publication_id'],body,principal=self.principal)
        self.assertEqual(self.wire,[]);self.assertEqual(self.state()['phase'],'prepared')
        with self.store.transaction() as con:self.assertEqual(con.execute('SELECT count(*) FROM native_official_publish_intents').fetchone()[0],0)
    def test_existing_session_can_finish_after_schedule_without_creating_another_init(self):
        self.scheduled();self.step();reference=self.state()['private_session_ref'];self.clock[0]+=timedelta(seconds=121)
        for _ in range(3):self.step()
        self.privacy='public';completed=self.poll();self.assertTrue(completed['mock_publication_complete']);self.assertEqual(self.state()['private_session_ref'],reference)
        self.assertEqual(sum(r['method']=='POST' for r in self.wire),1)
    def test_numeric_naive_unknown_and_unchecked_metadata_fail_before_any_dispatch(self):
        for metadata in ({'title':'Explicit fixture','scheduled_at':True},{'title':'Explicit fixture','scheduled_at':2000000000},
            {'title':'Explicit fixture','scheduled_at':'2026-10-08T10:00:00'},{'title':'Explicit fixture','endpoint':'https://untrusted.invalid'}):
            with self.assertRaises(ValueError):self.body(metadata=metadata)
        unchecked=self.body().model_copy(update={'metadata':PublicationMetadata(title='Explicit fixture').model_copy(update={'scheduled_at':True})})
        with self.assertRaisesRegex(WorkflowError,'FIELDS_INVALID'):self.service.create(self.project['id'],unchecked,principal=self.principal)
        self.assertEqual(self.wire,[])
    def test_past_near_term_public_or_invalid_metadata_fails_with_no_new_review(self):
        self.service.cancel(self.project['id'],self.value['publication_id'],Action(expected_snapshot_sha256=self.value['snapshot_sha256']),principal=self.principal)
        for changes in ({'scheduled_at':(self.clock[0]-timedelta(seconds=1)).isoformat()},{'scheduled_at':(self.clock[0]+timedelta(seconds=59)).isoformat()},
            {'scheduled_at':(self.clock[0]+timedelta(seconds=120)).isoformat(),'privacy':'public'},{'title':'<Explicit invalid provider metadata>'}):
            body=self.body(metadata={**self.parent['snapshot']['request']['metadata'],**changes})
            with self.assertRaises(WorkflowError):self.create(body)
        self.assertEqual(self.wire,[])
        with self.store.transaction() as con:self.assertEqual(con.execute('SELECT count(*) FROM native_official_publications').fetchone()[0],1)
    def test_changed_explicit_metadata_cannot_reuse_key_or_existing_approval(self):
        self.scheduled();body=self.body(metadata=self.value['snapshot']['metadata'],request_key='explicit-scheduled-metadata-fixture-key')
        same,replay=self.service.create(self.project['id'],body,principal=self.principal);self.assertTrue(replay);self.assertEqual(same['publication_id'],self.value['publication_id'])
        changed=self.body(metadata={**self.value['snapshot']['metadata'],'scheduled_at':(self.at+timedelta(seconds=1)).isoformat()},request_key=body.request_key)
        with self.assertRaisesRegex(WorkflowError,'IDEMPOTENCY_CONFLICT'):self.create(changed)
        with self.assertRaisesRegex(WorkflowError,'DUPLICATE_REVIEW_REQUIRED'):self.create(changed.model_copy(update={'request_key':'explicit-other-key-scheduled-metadata'}))
        self.assertEqual(self.wire,[])
    def test_legacy_unscheduled_request_fingerprint_and_read_survive_additive_metadata_fields(self):
        body=self.body();snapshot={k:v for k,v in self.value['snapshot'].items() if k not in ('reviewed_at','metadata_source')}
        self.service.cancel(self.project['id'],self.value['publication_id'],Action(expected_snapshot_sha256=self.value['snapshot_sha256']),principal=self.principal)
        with self.store.transaction() as con:con.execute('UPDATE native_official_publications SET snapshot_json=?,snapshot_sha256=? WHERE publication_id=?',(json.dumps(snapshot),digest(snapshot),self.value['publication_id']))
        value,replay=self.service.create(self.project['id'],body,principal=self.principal)
        self.assertTrue(replay);self.assertNotIn('metadata',snapshot['request']);self.assertEqual(value['request_fingerprint'],digest(snapshot['request']));self.assertEqual(value['snapshot'],snapshot)
        self.assertEqual(value['status'],'cancelled');self.assertEqual(self.wire,[])

if __name__=='__main__':unittest.main()
