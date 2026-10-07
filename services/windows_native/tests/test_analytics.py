"""Explicit Native analytics fixtures are never real audience or Owner acceptance."""
import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from pydantic import ValidationError
from services.windows_native.analytics import NativeAnalytics
from services.windows_native.analytics_models import NativeAnalyticsRequest
from services.windows_native.publications import NativePublications
from services.windows_native.publication_models import NativePublicationCreate,NativePublishApproval
from services.windows_native.store import Store
from services.windows_native.contracts import WorkflowError
from services.windows_native.tests.test_publications import render_fixture,CAPABILITIES


class NativeAnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.store=Store(self.root)
        self.project,self.job=render_fixture(self.store);self.pubservice=NativePublications(self.store,CAPABILITIES)
        self.pub=self.publish();self.clock=[datetime.now(timezone.utc)];self.service=NativeAnalytics(self.store,self.pubservice,clock=lambda:self.clock[0])

    def tearDown(self):self.temp.cleanup()

    def publish(self,platform='youtube'):
        payload=NativePublicationCreate(revision=self.project['revision'],final_job_id=self.job['id'],platform=platform,
            metadata={'title':'EXPLICIT MOCK METRICS FIXTURE'},request_key='native-analytics-publication-fixture-'+platform)
        value,_=self.pubservice.create(self.project['id'],payload,actor='fixture-editor')
        self.pubservice.approve(self.project['id'],value['publication_id'],NativePublishApproval(expected_fingerprint=value['request_fingerprint'],
            expected_artifact_sha256=value['snapshot']['final_sha256'],acknowledged=True),actor='fixture-owner')
        return self.pubservice.process()

    def payload(self,**changes):
        return NativeAnalyticsRequest.model_validate({'publication_id':self.pub['publication_id'],'provider_mode':'fixture',
            'fixture_acknowledged':True,'fixture_profile':'insufficient_data','request_key':'native-analytics-owned-fixture-key',**changes})

    def create(self,**changes):return self.service.create(self.project['id'],self.payload(**changes),actor='fixture-owner')[0]

    def test_pure_provider_and_native_models_import_without_framework_database_or_gpu(self):
        source="from services.windows_native import ingestion; import sys; from app.analytics_providers import DeterministicAnalyticsProvider; from services.windows_native.analytics import NativeAnalytics; assert not any(n.startswith(('sqlalchemy','fastapi','torch','vieneu')) for n in sys.modules)"
        subprocess.run([sys.executable,'-c',source],cwd=Path(__file__).resolve().parents[3],capture_output=True,check=True,timeout=15)

    def test_empty_reads_and_official_requests_never_collect_or_invent_metrics(self):
        before=self.store.get(self.project['id']);self.assertEqual(self.service.page(self.project['id'])['items'],[])
        self.assertFalse(self.service.states()['external_calls_enabled'])
        official=self.payload(provider_mode='official',fixture_acknowledged=False,fixture_profile=None)
        with patch.object(self.service.provider,'collect',side_effect=AssertionError('No official fixture fallback')):
            row,_=self.service.create(self.project['id'],official,actor='fixture-owner');self.assertEqual(row['status'],'not_configured')
            self.assertIsNone(self.service.process());self.assertIsNone(self.service.get(self.project['id'],row['sync_id'])['snapshot'])
        self.assertEqual(self.store.get(self.project['id']),before)

    def test_four_platform_fixtures_keep_missing_metrics_null_and_assessment_explainable(self):
        for platform in ['youtube','tiktok','instagram_reels','facebook']:
            pub=self.pub if platform=='youtube' else self.publish(platform)
            value=self.create(publication_id=pub['publication_id'],request_key='native-four-metric-fixture-'+platform)
            self.service.process();detail=self.service.get(self.project['id'],value['sync_id']);snapshot=detail['snapshot']
            self.assertEqual(snapshot['platform'],platform);self.assertTrue(snapshot['mock']);self.assertFalse(snapshot['external_call'])
            self.assertIsNone(snapshot['metrics']['completion_rate']);self.assertIsNone(snapshot['metrics']['revenue'])
            self.assertEqual(snapshot['assessment']['state'],'insufficient_data');self.assertFalse(snapshot['assessment']['automatic_action'])
            self.assertFalse(snapshot['evidence']['real_audience_observation']);self.assertIsNone(snapshot['features']['publishing_time'])

    def test_idempotency_refresh_history_and_fresh_service_restore_are_exact(self):
        first=self.create();self.service.process();original=self.service.get(self.project['id'],first['sync_id'])
        second=self.create(trigger='manual_refresh',fixture_profile='normal',request_key='native-analytics-manual-fixture-key');self.service.process()
        restored=NativeAnalytics(Store(self.root),NativePublications(Store(self.root),CAPABILITIES))
        self.assertEqual(restored.get(self.project['id'],first['sync_id']),original)
        value,replay=restored.create(self.project['id'],self.payload(),actor='fixture-another-owner');self.assertTrue(replay)
        self.assertEqual(value['snapshot_id'],original['snapshot']['snapshot_id']);self.assertEqual(len(restored.page(self.project['id'])['items']),2)
        with self.assertRaisesRegex(WorkflowError,'IDEMPOTENCY_CONFLICT'):
            self.create(fixture_profile='winner_candidate')
        self.assertEqual(restored.process(project=self.project['id'],identity=first['sync_id'],fingerprint=first['request_fingerprint'])['status'],'succeeded')

    def test_queued_features_use_published_job_not_later_project_labels(self):
        value=self.create()
        with self.store.transaction() as con:
            document=copy.deepcopy(self.project['document']);document['analytics_features']={'topic':'EXPLICIT LATER EDIT','niche':'later-fixture'}
            con.execute('UPDATE projects SET revision=revision+1,document=?,approval=NULL WHERE id=?',(json.dumps(document),self.project['id']))
            self.store.version(con,self.project['id'])
        self.service.process();snapshot=self.service.get(self.project['id'],value['sync_id'])['snapshot']
        self.assertIsNone(snapshot['features']['niche']);self.assertIsNone(snapshot['features']['topic'])
        self.assertFalse(snapshot['features']['evidence']['current_project_metadata_used'])
        self.assertEqual(snapshot['features']['evidence']['job_snapshot_sha256'],self.pub['snapshot']['job_snapshot_sha256'])

    def test_schedule_rate_limit_backoff_and_cancellation_are_persisted(self):
        row=self.create(trigger='scheduled_refresh',scheduled_for=self.clock[0]+timedelta(hours=1));self.assertEqual(row['status'],'scheduled')
        self.assertIsNone(self.service.process());self.service.cancel(self.project['id'],row['sync_id'],fingerprint=row['request_fingerprint'],actor='fixture-owner')
        self.clock[0]+=timedelta(hours=1);self.assertIsNone(self.service.process())
        row=self.create(fixture_profile='rate_limited',request_key='native-analytics-rate-limit-fixture-key')
        first=self.service.process();self.assertEqual(first['status'],'retry_scheduled');self.assertIsNone(self.service.process())
        self.clock[0]+=timedelta(seconds=30);second=self.service.process();self.assertEqual(second['attempts'],2)
        self.clock[0]+=timedelta(seconds=59);self.assertIsNone(self.service.process())
        self.clock[0]+=timedelta(seconds=1);third=self.service.process();self.assertEqual(third['status'],'failed');self.assertEqual(third['attempts'],3)
        self.assertIsNone(self.service.get(self.project['id'],row['sync_id'])['snapshot'])

    def test_concurrent_create_and_dispatch_have_one_historical_snapshot(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            rows=list(pool.map(lambda _:self.service.create(self.project['id'],self.payload(),actor='fixture-owner'),range(2)))
        self.assertEqual(sum(not replay for _,replay in rows),1)
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:self.service.process(),range(2)))
        self.assertEqual(sum(row is not None for row in results),1)
        with self.store.transaction() as con:self.assertEqual(con.execute('SELECT COUNT(*) FROM native_analytics_snapshots').fetchone()[0],1)

    def test_snapshot_insert_rolls_back_if_completion_event_fails(self):
        value=self.create();original=self.service.event
        def event(con,row,action,actor,**evidence):
            if action=='analytics.fixture.collected':raise RuntimeError('EXPLICIT SNAPSHOT COMMIT FAILURE FIXTURE')
            return original(con,row,action,actor,**evidence)
        with patch.object(self.service,'event',side_effect=event):result=self.service.process()
        self.assertEqual(result['status'],'failed');self.assertIsNone(self.service.get(self.project['id'],value['sync_id'])['snapshot'])
        with self.store.transaction() as con:self.assertEqual(con.execute('SELECT COUNT(*) FROM native_analytics_snapshots').fetchone()[0],0)

    def test_scoped_history_filter_cursor_and_snapshot_integrity(self):
        rows=[self.create(request_key='native-history-metric-fixture-'+str(i)) for i in range(4)]
        for _ in rows:self.service.process()
        first=self.service.page(self.project['id'],limit=2,publication=self.pub['publication_id'])
        second=self.service.page(self.project['id'],limit=2,publication=self.pub['publication_id'],cursor=first['next_cursor'])
        self.assertEqual(len({row['sync_id'] for row in first['items']+second['items']}),4);self.assertIsNone(second['next_cursor'])
        with self.assertRaisesRegex(WorkflowError,'CURSOR_INVALID'):self.service.page(self.project['id'],cursor=first['next_cursor'])
        other=NativeAnalytics(self.store,NativePublications(self.store,CAPABILITIES,workspace_id='wsp_other_fixture'))
        self.assertEqual(other.page(self.project['id'])['items'],[])
        with self.assertRaisesRegex(WorkflowError,'NOT_FOUND'):other.get(self.project['id'],rows[0]['sync_id'])
        with self.store.transaction() as con:
            con.execute("UPDATE native_analytics_snapshots SET snapshot_json='{}' WHERE sync_id=?",(rows[0]['sync_id'],))
        with self.assertRaisesRegex(WorkflowError,'SNAPSHOT_EVIDENCE_INVALID'):self.service.get(self.project['id'],rows[0]['sync_id'])

    def test_explicit_fixture_and_timezone_contract_rejects_coercion_or_live_flags(self):
        for changes in [{'fixture_acknowledged':False},{'fixture_acknowledged':1},{'fixture_profile':None},
            {'provider_mode':'official'},{'publish_enabled':True},{'trigger':'scheduled_refresh'},
            {'scheduled_for':1800000000},{'scheduled_for':'2026-10-07T12:00:00'},{'actor_ref':'spoofed-fixture-owner'}]:
            with self.subTest(fields=list(changes)),self.assertRaises(ValidationError):self.payload(**changes)

    def test_workspace_overview_keeps_latest_distinct_posts_and_scoped_cursor_without_account_totals(self):
        for platform in ['youtube','tiktok','facebook']:
            pub=self.pub if platform=='youtube' else self.publish(platform)
            for i in range(2):
                self.create(publication_id=pub['publication_id'],fixture_profile='normal' if i else 'insufficient_data',
                    request_key='native-overview-fixture-'+platform+'-'+str(i));self.service.process()
        first=self.service.overview(limit=2);second=self.service.overview(limit=2,cursor=first['next_cursor'])
        items=first['items']+second['items'];self.assertEqual(len({row['publication_id'] for row in items}),3)
        self.assertTrue(all(row['metrics']['views']==18000 for row in items));self.assertIsNone(second['next_cursor'])
        self.assertFalse(first['channel_account_verified']);self.assertIsNone(first['account_totals'])
        other=NativeAnalytics(self.store,NativePublications(self.store,CAPABILITIES,workspace_id='wsp_other_fixture'))
        self.assertEqual(other.overview()['items'],[])
        with self.assertRaisesRegex(WorkflowError,'CURSOR_INVALID'):other.overview(cursor=first['next_cursor'])


if __name__=='__main__':unittest.main()
