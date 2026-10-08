"""Recurring fixture recovery and cancellation never imply audience acceptance."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
from pydantic import ValidationError
from services.windows_native.analytics_refresh import NativeAnalyticsRefresh
from services.windows_native.analytics_refresh_models import NativeAnalyticsRefreshCreate, NativeAnalyticsRefreshState
from services.windows_native.analytics import NativeAnalytics
from services.windows_native.publications import NativePublications
from services.windows_native.store import Store
from services.windows_native.contracts import WorkflowError
from services.windows_native.tests import test_analytics as fixtures


class NativeAnalyticsRefreshTests(unittest.TestCase):
    def setUp(self):
        fixtures.NativeAnalyticsTests.setUp(self)
        self.refresh=NativeAnalyticsRefresh(self.service)
    tearDown=fixtures.NativeAnalyticsTests.tearDown
    publish=fixtures.NativeAnalyticsTests.publish

    def payload(self,**changes):
        return NativeAnalyticsRefreshCreate.model_validate({'publication_id':self.pub['publication_id'],
            'provider_mode':'fixture','fixture_acknowledged':True,'fixture_profile':'normal',
            'first_run_at':self.clock[0].isoformat(),'request_key':'native-recurring-fixture-policy-key',**changes})
    def create(self,**changes):return self.refresh.create(self.project['id'],self.payload(**changes),actor='fixture-owner')[0]
    def state(self,plan,enabled,**changes):
        return self.refresh.state(self.project['id'],plan['plan_id'],NativeAnalyticsRefreshState.model_validate({
            'expected_revision':plan['revision'],'enabled':enabled,'acknowledged_read_only':enabled,
            'fixture_acknowledged':enabled,**changes}),actor='fixture-second-owner')

    def test_pure_model_reuses_report_queries_without_framework_or_gpu(self):
        source="import sys; from services.windows_native.analytics_refresh import NativeAnalyticsRefresh; assert not any(n.startswith(('sqlalchemy','fastapi','torch','vieneu')) for n in sys.modules)"
        subprocess.run([sys.executable,'-c',source],cwd=Path(__file__).resolve().parents[3],capture_output=True,check=True,timeout=15)

    def test_default_disabled_frozen_profile_and_official_never_fall_back(self):
        before=self.store.get(self.project['id']);plan=self.create()
        self.assertEqual(plan['status'],'paused');self.assertFalse(plan['enabled']);self.assertEqual(self.refresh.tick()['created_sync_ids'],[])
        profile=plan['analytics_profile'];self.assertEqual(profile['profile_ref'],'native-recorded-fixture-analytics@1')
        self.assertEqual(profile['missing_metric_policy'],'null');self.assertFalse(profile['publishing_enabled'])
        official=self.create(provider_mode='official',fixture_acknowledged=False,query_policy='rolling_complete_days',lookback_days=7,
            request_key='native-recurring-official-not-configured-key')
        self.assertEqual(official['status'],'not_configured');self.assertEqual(official['analytics_profile']['provider_status'],'NOT_CONFIGURED')
        with patch.object(self.service.provider,'collect',side_effect=AssertionError('No live fallback')):
            with self.assertRaisesRegex(WorkflowError,'OFFICIAL_NOT_CONFIGURED'):self.state(official,True)
            self.assertEqual(self.refresh.tick()['created_sync_ids'],[]);self.assertIsNone(self.service.process())
        self.assertEqual(self.store.get(self.project['id']),before)

    def test_recurring_occurrences_append_history_once_and_exhaust(self):
        plan=self.create(enabled=True,acknowledged_read_only=True,max_runs=2,interval_hours=1)
        first=self.refresh.tick()['created_sync_ids'];self.assertEqual(len(first),1)
        self.assertEqual(self.refresh.tick()['created_sync_ids'],[])
        self.service.process();snapshot=self.service.get(self.project['id'],first[0])['snapshot']
        self.assertEqual(snapshot['evidence']['refresh_occurrence']['ordinal'],1)
        self.assertEqual(self.refresh.tick()['created_sync_ids'],[])
        self.clock[0]+=timedelta(hours=1);second=self.refresh.tick()['created_sync_ids'];self.assertEqual(len(second),1)
        self.assertEqual(self.refresh.get(self.project['id'],plan['plan_id'])['status'],'exhausted')
        self.service.process();self.assertEqual(self.service.get(self.project['id'],second[0])['status'],'succeeded')
        self.clock[0]+=timedelta(days=1);self.assertEqual(self.refresh.tick()['created_sync_ids'],[])
        self.assertEqual(self.service.get(self.project['id'],first[0])['snapshot'],snapshot)
        self.assertEqual(len(self.service.page(self.project['id'])['items']),2)
        with self.assertRaisesRegex(WorkflowError,'EXHAUSTED'):self.state(self.refresh.get(self.project['id'],plan['plan_id']),True)

    def test_missed_periods_make_one_current_job_and_no_burst(self):
        plan=self.create(enabled=True,acknowledged_read_only=True,interval_hours=1)
        self.clock[0]+=timedelta(hours=9,minutes=12)
        self.assertEqual(len(self.refresh.tick()['created_sync_ids']),1)
        detail=self.refresh.get(self.project['id'],plan['plan_id']);occurrence=detail['occurrences'][0]
        self.assertEqual(occurrence['skipped_slots'],9);self.assertEqual(detail['run_count'],1)
        self.assertEqual(detail['next_due_at'],(self.clock[0]+timedelta(hours=1)).isoformat())
        self.assertEqual(self.refresh.tick()['created_sync_ids'],[])

    def test_disable_fences_pending_and_retry_jobs_without_erasing_history(self):
        plan=self.create(enabled=True,acknowledged_read_only=True,fixture_profile='rate_limited',interval_hours=1)
        sync=self.refresh.tick()['created_sync_ids'][0];self.service.process()
        self.assertEqual(self.service.get(self.project['id'],sync)['status'],'retry_scheduled')
        self.clock[0]+=timedelta(hours=1);self.assertEqual(self.refresh.tick()['created_sync_ids'],[])
        disabled=self.state(plan,False);self.assertEqual(disabled['revision'],2)
        self.assertEqual(self.service.get(self.project['id'],sync)['status'],'cancelled');self.assertIsNone(self.service.process())
        enabled=self.state(disabled,True);self.assertEqual(enabled['revision'],3)
        new=self.refresh.tick()['created_sync_ids'];self.assertEqual(len(new),1);self.assertNotEqual(sync,new[0])
        with self.assertRaisesRegex(WorkflowError,'REVISION_CONFLICT'):self.state(disabled,False)

    def test_disable_after_exhaustion_cancels_last_occurrence(self):
        plan=self.create(enabled=True,acknowledged_read_only=True,max_runs=1)
        sync=self.refresh.tick()['created_sync_ids'][0];self.state(plan,False)
        self.assertIsNone(self.service.process());self.assertEqual(self.service.get(self.project['id'],sync)['status'],'cancelled')

    def test_concurrent_ticks_restore_and_idempotency_preserve_exact_plan(self):
        plan=self.create(enabled=True,acknowledged_read_only=True)
        with ThreadPoolExecutor(max_workers=3) as pool:values=list(pool.map(lambda _:self.refresh.tick(),range(3)))
        self.assertEqual(sum(len(v['created_sync_ids']) for v in values),1)
        self.service.process();original=self.refresh.get(self.project['id'],plan['plan_id'])
        restored=NativeAnalyticsRefresh(NativeAnalytics(Store(self.root),NativePublications(Store(self.root),fixtures.CAPABILITIES),clock=lambda:self.clock[0]))
        self.assertEqual(restored.get(self.project['id'],plan['plan_id']),original)
        replay,was_replay=restored.create(self.project['id'],self.payload(enabled=True,acknowledged_read_only=True),actor='another-fixture-owner')
        self.assertTrue(was_replay);self.assertEqual(replay['plan_id'],plan['plan_id'])
        with self.assertRaisesRegex(WorkflowError,'IDEMPOTENCY_CONFLICT'):self.create(interval_hours=2)

    def test_atomic_occurrence_failure_does_not_leave_orphaned_sync_or_increment(self):
        plan=self.create(enabled=True,acknowledged_read_only=True)
        with patch.object(self.refresh,'event',side_effect=RuntimeError('EXPLICIT OCCURRENCE COMMIT FAILURE')):
            with self.assertRaises(RuntimeError):self.refresh.tick()
        self.assertEqual(self.refresh.get(self.project['id'],plan['plan_id'])['run_count'],0)
        self.assertEqual(self.service.page(self.project['id'])['items'],[])
        self.assertEqual(len(self.refresh.tick()['created_sync_ids']),1)

    def test_scope_pages_and_corrupt_policy_fail_closed(self):
        for i in range(3):self.create(request_key='native-recurring-fixture-page-'+str(i))
        first=self.refresh.page(self.project['id'],limit=2);second=self.refresh.page(self.project['id'],limit=2,cursor=first['next_cursor'])
        self.assertEqual(len({r['plan_id'] for r in first['items']+second['items']}),3)
        other=NativeAnalyticsRefresh(NativeAnalytics(self.store,NativePublications(self.store,fixtures.CAPABILITIES,workspace_id='wsp_other_fixture')))
        self.assertEqual(other.page(self.project['id'])['items'],[])
        with self.assertRaisesRegex(WorkflowError,'CURSOR_INVALID'):other.page(self.project['id'],cursor=first['next_cursor'])
        with self.assertRaisesRegex(WorkflowError,'NOT_FOUND'):other.get(self.project['id'],first['items'][0]['plan_id'])
        with self.store.transaction() as con:con.execute("UPDATE native_analytics_refresh_plans SET policy_json='{}' WHERE plan_id=?",(first['items'][0]['plan_id'],))
        with self.assertRaisesRegex(WorkflowError,'EVIDENCE_INVALID'):self.refresh.get(self.project['id'],first['items'][0]['plan_id'])

    def test_binding_change_blocks_future_occurrence_and_does_not_touch_publication(self):
        plan=self.create(enabled=True,acknowledged_read_only=True)
        with self.store.transaction() as con:con.execute("UPDATE native_publications SET status='cancelled' WHERE publication_id=?",(self.pub['publication_id'],))
        self.assertEqual(self.refresh.tick()['created_sync_ids'],[])
        self.assertEqual(self.refresh.get(self.project['id'],plan['plan_id'])['status'],'needs_attention')
        self.assertEqual(self.service.page(self.project['id'])['items'],[])

    def test_occurrence_tamper_blocks_collection_without_inventing_a_snapshot(self):
        plan=self.create(enabled=True,acknowledged_read_only=True);sync=self.refresh.tick()['created_sync_ids'][0]
        with self.store.transaction() as con:con.execute("UPDATE native_analytics_refresh_occurrences SET occurrence_json='{}' WHERE sync_id=?",(sync,))
        with patch.object(self.service.provider,'collect',side_effect=AssertionError('Invalid occurrence cannot collect')):self.service.process()
        done=self.service.get(self.project['id'],sync);self.assertEqual(done['status'],'failed');self.assertIsNone(done['snapshot'])
        self.assertEqual(done['failure_code'],'NATIVE_ANALYTICS_REFRESH_OCCURRENCE_INVALID')

    def test_strict_policy_rejects_coercion_and_unacknowledged_or_live_intent(self):
        for change in [{'enabled':True},{'enabled':1},{'max_runs':True},{'interval_hours':'1'},{'fixture_acknowledged':False},
            {'first_run_at':1800000000},{'first_run_at':'2026-10-08T00:00:00'},{'provider_mode':'official'},
            {'include_revenue':True},{'actor_ref':'spoofed-owner'},{'publish_enabled':True}]:
            with self.subTest(change=change),self.assertRaises(ValidationError):self.payload(**change)
        official=self.payload(provider_mode='official',fixture_acknowledged=False,query_policy='rolling_complete_days',lookback_days=7)
        self.assertEqual(official.query_at(self.clock[0])['end_date'],(self.clock[0]-timedelta(days=1)).date().isoformat())


if __name__=='__main__':unittest.main()
