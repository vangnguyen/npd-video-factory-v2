"""Finite official refresh tests; explicit nonplayable protocol fixtures."""
import copy,json,unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from dataclasses import replace
from unittest.mock import patch
from pydantic import ValidationError
from services.windows_native.tests.test_official_analytics import OfficialAnalyticsFixture
from services.windows_native.official_analytics_refresh import NativeOfficialAnalyticsRefresh,RefreshCreate,RefreshCancel,TABLES
from services.windows_native.official_analytics import NativeOfficialAnalytics
from services.windows_native.official_account_registry import AccountFactory
from services.windows_native.contracts import WorkflowError,digest
from app.human_identity import HumanAuthVerifier,HumanAuthRegistry

class OfficialRefreshFixture(OfficialAnalyticsFixture):
    def setUp(self):
        super().setUp();self.refresh=NativeOfficialAnalyticsRefresh(self.analytics,enabled=True)
    def refresh_payload(self,**changes):
        return RefreshCreate.model_validate({**self.collection().model_dump(mode='json'),
            'schema_version':'native-official-analytics-refresh-request-v1','acknowledged_background_reads':True,
            'max_runs':3,'interval_seconds':60,'start_at':self.clock[0].isoformat(),'deadline':(self.clock[0]+timedelta(seconds=900)).isoformat(),
            'request_key':'explicit-finite-official-refresh-key',**changes})
    def plan(self,**changes):
        self.plan_request=self.refresh_payload(**changes)
        self.saved_plan=self.refresh.create(self.project['id'],self.plan_request,principal=self.principal)[0]
        return self.saved_plan
    def get_plan(self):return self.refresh.get(self.project['id'],self.saved_plan['plan_id'])
    def cancel_plan(self,pending=True):
        value=self.get_plan()
        return self.refresh.cancel(self.project['id'],value['plan_id'],RefreshCancel(expected_policy_sha256=value['policy_sha256'],expected_version=value['version'],cancel_pending_read=pending),principal=self.principal)
    def revoke(self):
        data=copy.deepcopy(self.verifier.registry.model_dump(mode='json'));data['tokens'][self.principal.token_id]['enabled']=False
        self.verifier=HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400)

class OfficialRefreshTests(OfficialRefreshFixture,unittest.TestCase):
    def test_three_finite_reads_append_existing_nullable_snapshots_and_preserve_project(self):
        before=self.store.get(self.project['id']);self.plan();snapshots=[]
        for ordinal in range(1,4):
            intent=self.refresh.tick();self.assertEqual(intent['run_count'],ordinal);self.assertEqual(len(self.read_wire),3*(ordinal-1))
            self.assertIsNone(self.refresh.tick());done=self.analytics.process();self.assertEqual(done['status'],'succeeded');snapshots.append(done)
            self.refresh.tick()
            if ordinal<3:self.clock[0]+=timedelta(seconds=60)
        value=self.get_plan();self.assertEqual(value['status'],'completed');self.assertEqual(value['run_count'],3);self.assertEqual(len(value['occurrences']),3)
        self.assertIsNone(self.refresh.tick());self.assertEqual(len(self.read_wire),9);self.assertEqual(self.store.get(self.project['id']),before)
        for item in snapshots:
            self.assertEqual(self.analytics.get(self.project['id'],item['sync_id'])['result'],item['result'])
            self.assertEqual(item['result']['metrics']['views'],0);self.assertIsNone(item['result']['metrics']['completion_rate']);self.assertIsNone(item['result']['publishing_time'])
        self.assertEqual(len({x['result_snapshot_id'] for x in snapshots}),3);self.assertTrue(all(x['mock'] and not x['result']['real_audience_observation'] for x in snapshots))
    def test_default_disabled_plan_has_no_credential_or_background_read(self):
        self.refresh=NativeOfficialAnalyticsRefresh(self.analytics)
        with patch.object(self.reader,'credential',side_effect=AssertionError('NO DEFAULT TOKEN RESOLVE')):
            value=self.plan();self.assertEqual(value['status'],'not_configured');self.assertIsNone(value['policy']['credential_proof'])
            self.assertIsNone(self.refresh.tick());self.refresh.recover();self.refresh.get(self.project['id'],value['plan_id'])
        self.assertEqual(self.read_wire,[]);self.assertFalse(self.refresh.states()['enabled']);self.assertFalse(self.refresh.states()['default_enabled'])
    def test_strict_ack_windows_keys_sample_and_retry_bounds(self):
        for changes in ({'acknowledged_background_reads':1},{'acknowledged_background_reads':False},{'max_runs':True},{'max_runs':101},{'interval_seconds':59},
            {'start_at':'2026-10-01T00:00:00'},{'deadline':1791400000},{'deadline':self.clock[0].isoformat()},{'max_attempts':2},{'request_key':'unsafe key spaces'}):
            with self.subTest(changes=changes),self.assertRaises(ValidationError):self.refresh_payload(**changes)
        unchecked=self.refresh_payload().model_copy(update={'acknowledged_background_reads':1})
        with self.assertRaisesRegex(WorkflowError,'FIELDS_INVALID'):self.refresh.create(self.project['id'],unchecked,principal=self.principal)
    def test_exact_replay_current_owner_and_conflict_no_duplicate_plan(self):
        first=self.plan();replay,found=self.refresh.create(self.project['id'],self.plan_request,principal=self.principal)
        self.assertTrue(found);self.assertEqual(first,replay)
        with self.assertRaisesRegex(WorkflowError,'IDEMPOTENCY_CONFLICT'):
            self.refresh.create(self.project['id'],self.plan_request.model_copy(update={'max_runs':4}),principal=self.principal)
        self.revoke()
        with self.assertRaisesRegex(WorkflowError,'CURRENT_OWNER'):self.refresh.create(self.project['id'],self.plan_request,principal=self.principal)
        self.assertEqual(self.get_plan(),first);self.assertEqual(self.read_wire,[])
    def test_one_active_plan_and_one_atomic_concurrent_occurrence(self):
        self.plan()
        with self.assertRaisesRegex(WorkflowError,'ALREADY_ACTIVE'):self.plan(request_key='explicit-different-finite-refresh-key')
        with ThreadPoolExecutor(2) as pool:values=list(pool.map(lambda _:self.refresh.tick(),range(2)))
        self.assertEqual(sum(v is not None for v in values),1);self.assertEqual(self.get_plan()['run_count'],1)
        with self.store.transaction() as con:
            self.assertEqual(con.execute('SELECT count(*) FROM native_official_analytics_syncs').fetchone()[0],1)
            self.assertEqual(con.execute('SELECT count(*) FROM native_official_analytics_refresh_occurrences').fetchone()[0],1)
        self.assertEqual(self.read_wire,[])
    def test_failed_occurrence_capture_rolls_back_collector_plan_count_and_event(self):
        self.plan();original=self.get_plan();original_event=self.refresh.event
        def fail(con,row,action,actor,**evidence):
            if action=='analytics.official.refresh.admitted':raise WorkflowError('EXPLICIT ATOMIC OCCURRENCE FAILURE')
            return original_event(con,row,action,actor,**evidence)
        with patch.object(self.refresh,'event',side_effect=fail):
            with self.assertRaisesRegex(WorkflowError,'EXPLICIT'):self.refresh.tick()
        self.assertEqual(self.get_plan(),original)
        with self.store.transaction() as con:self.assertEqual(con.execute('SELECT count(*) FROM native_official_analytics_syncs').fetchone()[0],0)
    def test_no_catchup_burst_and_one_pending_manual_read(self):
        self.plan();self.collect(request_key='explicit-manual-read-before-refresh-key');self.assertIsNone(self.refresh.tick());self.analytics.process()
        self.clock[0]+=timedelta(seconds=300);first=self.refresh.tick();self.assertEqual(first['run_count'],1)
        self.analytics.process();self.assertIsNone(self.refresh.tick());self.assertEqual(len(self.read_wire),6)
        self.assertEqual(first['next_due_at'],(self.clock[0]+timedelta(seconds=60)).isoformat())
        self.clock[0]+=timedelta(seconds=60);second=self.refresh.tick();self.assertEqual(second['run_count'],2)
    def test_known_retry_is_same_occurrence_and_unknown_stops_future_reads(self):
        self.plan(max_attempts=2,acknowledged_bounded_retries=True);first=self.refresh.tick();self.read_mode='rate-limit'
        failed=self.analytics.process();self.assertEqual(failed['status'],'retry_scheduled');self.assertIsNone(self.refresh.tick());self.assertIsNone(self.analytics.process())
        self.clock[0]+=timedelta(seconds=45);self.read_mode=None;done=self.analytics.process();self.assertEqual(done['attempts'],2);self.assertEqual(done['sync_id'],first['pending_sync_id'])
        self.refresh.tick();self.assertEqual(self.get_plan()['run_count'],1);self.clock[0]+=timedelta(seconds=15);self.refresh.tick()
        self.read_mode='timeout';unknown=self.analytics.process();self.assertEqual(unknown['status'],'outcome_unknown');stopped=self.refresh.tick()
        self.assertEqual(stopped['status'],'needs_attention');self.clock[0]+=timedelta(seconds=180);self.assertIsNone(self.refresh.tick());self.assertIsNone(self.analytics.process())
    def test_cancel_choice_preserves_or_stops_already_admitted_read_explicitly(self):
        self.plan();self.refresh.tick();cancelled=self.cancel_plan(pending=False);self.assertEqual(cancelled['status'],'cancelled')
        done=self.analytics.process();self.assertEqual(done['status'],'succeeded');self.assertIsNone(self.refresh.tick());self.assertEqual(len(self.read_wire),3)
        self.clock[0]+=timedelta(seconds=1);self.plan(request_key='explicit-cancel-pending-refresh-key');self.refresh.tick();self.cancel_plan(pending=True)
        self.assertIsNone(self.analytics.process());self.assertEqual(len(self.read_wire),3);self.assertEqual(self.get_plan()['occurrences'][-1]['sync']['status'],'cancelled')
    def test_cancel_requires_current_owner_exact_hash_and_version(self):
        value=self.plan();payload=RefreshCancel(expected_policy_sha256='f'*64,expected_version=value['version'],cancel_pending_read=True)
        with self.assertRaisesRegex(WorkflowError,'REVIEW_BINDING'):self.refresh.cancel(self.project['id'],value['plan_id'],payload,principal=self.principal)
        self.refresh.tick()
        with self.assertRaisesRegex(WorkflowError,'REVIEW_BINDING'):self.refresh.cancel(self.project['id'],value['plan_id'],payload.model_copy(update={'expected_policy_sha256':value['policy_sha256']}),principal=self.principal)
        self.revoke()
        with self.assertRaisesRegex(WorkflowError,'CURRENT_OWNER'):self.cancel_plan()
    def test_revocation_before_admission_prevents_all_wire_calls(self):
        self.plan();self.revoke();stopped=self.refresh.tick();self.assertEqual(stopped['status'],'needs_attention');self.assertEqual(stopped['run_count'],0);self.assertEqual(self.read_wire,[])
    def test_revocation_after_admitted_read_reuses_original_dispatch_fence(self):
        self.plan();self.refresh.tick();self.revoke();done=self.analytics.process()
        self.assertEqual(done['status'],'failed');self.assertEqual(self.refresh.tick()['status'],'needs_attention')
        self.assertEqual(self.get_plan()['run_count'],1);self.assertEqual(self.read_wire,[]);self.assertIsNone(self.refresh.tick())
    def test_owner_revoked_after_child_creation_rolls_back_occurrence_and_collector(self):
        self.plan();original_event=self.analytics.event
        def revoke_after_write(con,row,action,actor,**evidence):
            original_event(con,row,action,actor,**evidence)
            if action=='analytics.official.read.created':self.revoke()
        with patch.object(self.analytics,'event',side_effect=revoke_after_write):
            with self.assertRaisesRegex(WorkflowError,'CURRENT_OWNER'):self.refresh.tick()
        with self.store.transaction() as con:
            self.assertEqual(con.execute('SELECT count(*) FROM native_official_analytics_syncs').fetchone()[0],0)
            self.assertEqual(con.execute('SELECT count(*) FROM native_official_analytics_refresh_occurrences').fetchone()[0],0)
        self.assertEqual(self.get_plan()['run_count'],0);self.assertEqual(self.refresh.tick()['status'],'needs_attention');self.assertEqual(self.read_wire,[])
    def test_account_drift_prevents_credentials_and_no_new_snapshot(self):
        self.plan();self.reader.account.read_enabled=False
        with patch.object(self.reader,'credential',side_effect=AssertionError('NO CREDENTIAL AFTER CONFIG DRIFT')):
            stopped=self.refresh.tick();self.assertEqual(stopped['status'],'needs_attention')
        self.assertEqual(self.read_wire,[])
    def test_credential_expiry_and_exact_proof_change_stop_without_renewal(self):
        self.plan();self.read_credential=replace(self.read_credential,expires_at=self.read_credential.expires_at+timedelta(seconds=1))
        stopped=self.refresh.tick();self.assertEqual(stopped['failure_code'],'NATIVE_OFFICIAL_REFRESH_CREDENTIAL_CHANGED');self.assertEqual(self.read_wire,[])
    def test_plan_window_cannot_outlive_owner_or_resolved_credential(self):
        with self.assertRaisesRegex(WorkflowError,'WINDOW_OUTSIDE_CONSENT'):self.plan(deadline=(self.principal.expires_at+timedelta(seconds=1)).isoformat())
        self.read_credential=replace(self.read_credential,expires_at=self.clock[0]+timedelta(seconds=120))
        with self.assertRaisesRegex(WorkflowError,'WINDOW_OUTSIDE_CREDENTIAL'):self.plan()
        self.assertEqual(self.read_wire,[])
    def test_owner_revoked_during_explicit_credential_check_rolls_back_plan(self):
        factory=AccountFactory(self.reader.account,self.root,self.workspace,owner_read_enabled=True,transport=self.reader.client.wire.transport,resolver=lambda _:self.revoke() or self.read_credential)
        self.accounts.factories[factory.account.account_ref]=factory
        with self.assertRaisesRegex(WorkflowError,'CURRENT_OWNER'):self.plan(expected_configuration_sha256=factory.sha256)
        with self.store.transaction() as con:self.assertEqual(con.execute('SELECT count(*) FROM native_official_analytics_refresh_plans').fetchone()[0],0)
    def test_deadline_caps_individual_consent_and_no_read_near_end(self):
        self.plan(deadline=(self.clock[0]+timedelta(seconds=121)).isoformat(),max_runs=3)
        first=self.refresh.tick();sync=first['occurrences'][0]['sync'];self.assertEqual(sync['snapshot']['request']['valid_for_seconds'],121)
        self.analytics.process();self.refresh.tick();self.clock[0]+=timedelta(seconds=62);stopped=self.refresh.tick()
        self.assertEqual(stopped['status'],'expired');self.assertEqual(stopped['run_count'],1);self.assertEqual(len(self.read_wire),3)
    def test_restart_unknown_is_reviewed_without_resolving_credentials_or_reissue(self):
        self.plan();intent=self.refresh.tick();self.analytics.claim();self.analytics.recover()
        restarted=NativeOfficialAnalyticsRefresh(self.analytics)
        with patch.object(self.reader,'credential',side_effect=AssertionError('NO RESTART DECRYPT')):
            self.assertEqual(restarted.recover()['plans_needing_attention'],1);self.assertEqual(restarted.recover()['plans_needing_attention'],0)
            saved=restarted.get(self.project['id'],intent['plan_id']);self.assertEqual(saved['status'],'needs_attention');self.assertIsNone(restarted.tick())
        self.assertEqual(self.read_wire,[])
    def test_original_history_after_archive_expiry_and_factory_removal_stays_exact(self):
        self.plan(max_runs=1);self.refresh.tick();self.analytics.process();self.refresh.tick();original=self.get_plan()
        self.accounts.factories.clear();self.clock[0]+=timedelta(days=2);current=self.store.get(self.project['id']);self.store.archive(current['id'],current['revision'],True)
        self.assertEqual(self.get_plan(),original);self.assertEqual(len(self.read_wire),3)
    def test_rehashed_policy_and_occurrence_relabels_reject_original_source(self):
        self.plan();self.refresh.tick()
        with self.store.transaction() as con:
            row=con.execute('SELECT policy_json,policy_sha256 FROM native_official_analytics_refresh_plans WHERE plan_id=?',(self.saved_plan['plan_id'],)).fetchone();original=tuple(row)
        for change in (lambda p:p.update(mock=1),lambda p:p.update(publishing_enabled=0),lambda p:p['request'].update(acknowledged_background_reads=1),lambda p:p['source'].update(receipt_sha256='f'*64)):
            policy=json.loads(original[0]);change(policy)
            with self.store.transaction() as con:con.execute('UPDATE native_official_analytics_refresh_plans SET policy_json=?,policy_sha256=? WHERE plan_id=?',(json.dumps(policy),digest(policy),self.saved_plan['plan_id']))
            with self.assertRaises(WorkflowError):self.get_plan()
        with self.store.transaction() as con:
            con.execute('UPDATE native_official_analytics_refresh_plans SET policy_json=?,policy_sha256=? WHERE plan_id=?',(*original,self.saved_plan['plan_id']))
            row=con.execute('SELECT occurrence_id,occurrence_json FROM native_official_analytics_refresh_occurrences').fetchone();value=json.loads(row[1]);value['ordinal']=True
            con.execute('UPDATE native_official_analytics_refresh_occurrences SET occurrence_json=?,occurrence_sha256=? WHERE occurrence_id=?',(json.dumps(value),digest(value),row[0]))
        with self.assertRaisesRegex(WorkflowError,'OCCURRENCE_CHANGED'):self.get_plan()
    def test_cursor_is_bounded_workspace_project_publication_scoped(self):
        self.plan(max_runs=1);self.refresh.tick();self.analytics.process();self.refresh.tick();self.clock[0]+=timedelta(seconds=1)
        self.plan(request_key='explicit-second-page-refresh-key');page=self.refresh.page(self.project['id'],limit=1);self.assertTrue(page['truncated']);self.assertTrue(page['next_cursor'])
        other=self.store.create('Other scoped fixture','','media')
        with self.assertRaisesRegex(WorkflowError,'PAGE_INVALID'):self.refresh.page(other['id'],limit=1,cursor=page['next_cursor'])
        with self.assertRaisesRegex(WorkflowError,'PAGE_INVALID'):self.refresh.page(self.project['id'],cursor='x'*2049)
        with self.assertRaisesRegex(WorkflowError,'NOT_FOUND'):self.refresh.get(other['id'],self.saved_plan['plan_id'])
        self.assertEqual(len(self.refresh.page(self.project['id'],limit=1,cursor=page['next_cursor'])['items']),1)
