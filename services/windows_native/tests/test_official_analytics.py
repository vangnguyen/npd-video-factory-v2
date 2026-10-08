"""Owned nonplayable publication/protocol fixtures; no real audience or Owner UAT."""
import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
import subprocess
import sys
import unittest
from unittest.mock import patch
import httpx
from pydantic import ValidationError
from services.windows_native.tests.test_official_publication_dispatch import OfficialDispatchFixture
from services.windows_native.tests import test_official_publication_worker as worker_fixture
from services.windows_native.official_publication_worker import NativeOfficialPublicationWorker
from services.windows_native.official_analytics import NativeOfficialAnalytics, TABLES
from services.windows_native.official_analytics_models import Collect, Cancel
from services.windows_native.official_account_registry import AccountFactory
from services.windows_native.contracts import WorkflowError, digest
from services.windows_native.backup import database_status
from app.analytics_official import YT_METRICS, YT_READ, YT_ANALYTICS, YT_MONEY, AnalyticsOAuthCredential
from app.human_identity import HumanAuthRegistry, HumanAuthVerifier


class OfficialAnalyticsFixture(OfficialDispatchFixture):
    def setUp(self):
        super().setUp();self.wire=[];self.ack=0;self.processing='processed';self.privacy='private';self.mode=None
        self.client.transport.handler=lambda request:worker_fixture.OfficialWorkerTests.response(self,request)
        worker=NativeOfficialPublicationWorker(self.service,self.vault)
        for _ in range(4):worker.step(self.project['id'],self.value['publication_id'],self.state()['version'])
        self.completed=worker.poll_processing(self.project['id'],self.value['publication_id'],self.state()['version'])
        self.read_wire=[];self.read_mode=None;self.metric_values=[0,2.5,1.2,0,0,0,0];self.rows=True
        self.read_credential=AnalyticsOAuthCredential(self.target,self.clock[0]+timedelta(hours=1),frozenset({YT_READ,YT_ANALYTICS}),'EXPLICIT-ANALYTICS-READ-TOKEN-FIXTURE-0123456789')
        account=self.account_factory.account
        self.reader=AccountFactory(account,self.root,self.workspace,owner_read_enabled=True,
            transport=httpx.MockTransport(self.read_response),resolver=lambda _:self.read_credential)
        self.accounts.factories[account.account_ref]=self.reader
        self.analytics=NativeOfficialAnalytics(self.service,enabled=True)

    def read_response(self,request):
        self.read_wire.append({'method':request.method,'host':request.url.host,'path':request.url.path,'query':str(request.url.query)})
        mode=self.read_mode
        if mode=='timeout':raise httpx.ReadTimeout('EXPLICIT-SECRET-NEVER-LEAK',request=request)
        if mode=='rate-limit':return httpx.Response(429,headers={'Retry-After':'45'})
        if mode=='server-error':return httpx.Response(503)
        if mode=='unauthorized':return httpx.Response(401)
        if mode=='expire-after-response':self.clock[0]+=timedelta(seconds=901)
        if mode=='revoke-after-response':
            raw=copy.deepcopy(self.verifier.registry.model_dump(mode='json'));raw['tokens'][self.principal.token_id]['enabled']=False
            self.verifier=HumanAuthVerifier(HumanAuthRegistry.model_validate(raw),max_token_ttl_seconds=86400)
        if mode=='cancel-after-response':self.analytics.cancel(self.project['id'],self.sync['sync_id'],Cancel(expected_snapshot_sha256=self.sync['snapshot_sha256']),principal=self.principal)
        if request.url.path=='/youtube/v3/channels':return httpx.Response(200,json={'items':[{'id':'FOREIGN' if mode=='foreign-channel' else self.target.target_account_id}]})
        if request.url.path=='/youtube/v3/videos':return httpx.Response(200,json={'items':[{'id':'FIXTURE0001','snippet':{'channelId':'FOREIGN' if mode=='foreign-video' else self.target.target_account_id}}]})
        if request.url.path=='/v2/reports':
            names=(*YT_METRICS,'estimatedRevenue') if 'estimatedRevenue' in str(request.url) else YT_METRICS
            headers=[{'name':name,'columnType':'METRIC','dataType':'INTEGER' if name in ('views','likes','comments','shares','subscribersGained') else 'FLOAT'} for name in names]
            if mode=='wrong-headers':headers[0]['name']='inventedViews'
            return httpx.Response(200,json={'columnHeaders':headers,'rows':[self.metric_values] if self.rows else []})
        raise AssertionError('Unexpected read endpoint')

    def collection(self,**changes):
        return Collect.model_validate({'publication_id':self.completed['publication_id'],'expected_publication_snapshot_sha256':self.completed['snapshot_sha256'],
            'expected_receipt_sha256':digest(self.completed['receipt']),'account_ref':self.reader.account.account_ref,
            'expected_configuration_sha256':self.reader.sha256,'query':{'start_date':'2026-10-01','end_date':'2026-10-07'},
            'acknowledged_read_only':True,'acknowledged_protocol_mock':True,'request_key':'explicit-official-analytics-fixture-key',**changes})

    def collect(self,**changes):
        self.sync=self.analytics.create(self.project['id'],self.collection(**changes),principal=self.principal)[0]
        return self.sync

    def run_collection(self,**changes):self.collect(**changes);return self.analytics.process()


class OfficialAnalyticsTests(OfficialAnalyticsFixture,unittest.TestCase):
    def test_receipt_bound_three_reads_null_metrics_and_zero_are_preserved(self):
        before=self.store.get(self.project['id']);done=self.run_collection();self.assertEqual(done['status'],'succeeded')
        result=done['result'];self.assertEqual([r['path'] for r in self.read_wire],['/youtube/v3/channels','/youtube/v3/videos','/v2/reports'])
        self.assertTrue(all(r['method']=='GET' for r in self.read_wire));self.assertEqual(result['metrics']['views'],0);self.assertEqual(result['metrics']['watch_time'],150)
        self.assertEqual(result['metrics']['average_view_duration'],1.2);self.assertIsNone(result['metrics']['completion_rate']);self.assertIsNone(result['metrics']['rpm'])
        self.assertIsNone(result['metrics']['observation_window_hours']);self.assertIsNone(result['publishing_time']);self.assertFalse(result['real_audience_observation'])
        self.assertTrue(result['mock']);self.assertFalse(result['external_call']);self.assertEqual(result['source_kind'],'official_protocol_mock')
        self.assertFalse(result['features']['evidence']['source_is_dry_run']);self.assertTrue(result['features']['evidence']['publication_protocol_mock'])
        self.assertEqual(before,self.store.get(self.project['id']));serialized=json.dumps(done)
        self.assertNotIn(self.read_credential.token,serialized);self.assertNotIn('upload_id',serialized)
        costs=[row for row in self.analytics.costs.summary(self.project['id'])['records'] if row['provider']=='official-youtube-analytics']
        self.assertEqual(len(costs),3);self.assertEqual(len({r['operation'] for r in costs}),3)
        self.assertTrue(all(r['status']=='response_received' and not r['paid'] and not r['external_call'] and r['actual_cost'] is None for r in costs))

    def test_empty_provider_rows_are_all_null_without_synthetic_fallback(self):
        self.rows=False;done=self.run_collection();self.assertTrue(all(v is None for v in done['result']['metrics'].values()))
        self.assertEqual(done['result']['evidence']['row_count'],0)

    def test_separate_refresh_keys_append_snapshots_and_do_not_overwrite_history(self):
        first=self.run_collection();self.metric_values[0]=7
        second=self.run_collection(request_key='explicit-second-official-analytics-key')
        self.assertNotEqual(first['result_snapshot_id'],second['result_snapshot_id']);self.assertEqual(second['result']['metrics']['views'],7)
        self.assertEqual(self.analytics.get(self.project['id'],first['sync_id'])['result'],first['result'])
        with self.store.transaction() as con:self.assertEqual(con.execute('SELECT count(*) FROM native_official_analytics_snapshots').fetchone()[0],2)

    def test_exact_key_replays_without_new_reads_and_conflict_is_rejected(self):
        first=self.run_collection();prior,replay=self.analytics.create(self.project['id'],self.collection(),principal=self.principal)
        self.assertTrue(replay);self.assertEqual(prior['sync_id'],first['sync_id']);self.assertIsNone(self.analytics.process());self.assertEqual(len(self.read_wire),3)
        with self.assertRaisesRegex(WorkflowError,'IDEMPOTENCY_CONFLICT'):self.collect(query={'start_date':'2026-10-02','end_date':'2026-10-07'})

    def test_default_disabled_runtime_has_no_reads_or_startup_decryption(self):
        self.analytics=NativeOfficialAnalytics(self.service);value=self.collect();self.assertEqual(value['status'],'not_configured')
        self.assertIsNone(self.analytics.process());self.assertFalse(self.analytics.states()['enabled']);self.assertEqual(self.read_wire,[])

    def test_mock_requires_raw_explicit_ack_and_cannot_use_real_client(self):
        with self.assertRaisesRegex(WorkflowError,'ACCOUNT_BINDING_CHANGED'):self.collect(acknowledged_protocol_mock=False)
        real=AccountFactory(self.reader.account,self.root,self.workspace,owner_read_enabled=True,resolver=lambda _:self.fail('No token reads'))
        self.accounts.factories[real.account.account_ref]=real
        with self.assertRaisesRegex(WorkflowError,'ACCOUNT_BINDING_CHANGED'):self.collect()
        self.assertEqual(self.read_wire,[])

    def test_request_requires_strict_booleans_dates_and_bounded_retry_consent(self):
        for changes in ({'acknowledged_read_only':1},{'acknowledged_protocol_mock':1},{'max_attempts':True},{'max_attempts':2},
            {'query':{'start_date':True,'end_date':1791388800}},{'query':{'start_date':'2026-10-07','end_date':'2026-10-01'}},
            {'query':{'start_date':'2026-10-01','end_date':'2026-10-07','include_revenue':1}}):
            with self.subTest(changes=changes),self.assertRaises(ValidationError):self.collection(**changes)
        unchecked=self.collection().model_copy(update={'acknowledged_read_only':1})
        with self.assertRaisesRegex(WorkflowError,'FIELDS_INVALID'):self.analytics.create(self.project['id'],unchecked,principal=self.principal)

    def test_unqualified_or_changed_receipt_is_rejected_before_account_reads(self):
        with self.assertRaisesRegex(WorkflowError,'QUALIFIED_RECEIPT_REQUIRED'):self.collect(expected_receipt_sha256='f'*64)
        with self.store.transaction() as con:con.execute("UPDATE native_official_publications SET status='queued' WHERE publication_id=?",(self.completed['publication_id'],))
        with self.assertRaises(WorkflowError):self.collect()
        self.assertEqual(self.read_wire,[])

    def test_foreign_project_scope_is_not_visible(self):
        value=self.collect();other=self.store.create('Other owned fixture','', 'media')
        with self.assertRaisesRegex(WorkflowError,'NOT_FOUND'):self.analytics.get(other['id'],value['sync_id'])
        with self.assertRaises(WorkflowError):self.analytics.create(other['id'],self.collection(request_key='explicit-foreign-project-read-key'),principal=self.principal)
        self.assertEqual(self.read_wire,[])

    def test_foreign_authenticated_channel_blocks_video_and_report(self):
        self.read_mode='foreign-channel';done=self.run_collection();self.assertEqual(done['failure_code'],'ANALYTICS_ACCOUNT_NOT_CONFIRMED')
        self.assertEqual(len(self.read_wire),1);self.assertIsNone(done['result'])

    def test_foreign_video_owner_blocks_report(self):
        self.read_mode='foreign-video';done=self.run_collection();self.assertEqual(done['failure_code'],'ANALYTICS_VIDEO_OWNERSHIP_NOT_CONFIRMED')
        self.assertEqual(len(self.read_wire),2);self.assertIsNone(done['result'])

    def test_changed_current_account_configuration_stops_before_credentials(self):
        self.collect();self.reader.account.read_enabled=False;done=self.analytics.process()
        self.assertEqual(done['status'],'failed');self.assertEqual(self.read_wire,[])

    def test_expired_owner_consent_stops_before_cost_or_network(self):
        self.collect();self.clock[0]+=timedelta(seconds=901);self.assertIsNone(self.analytics.process())
        done=self.analytics.get(self.project['id'],self.sync['sync_id']);self.assertEqual(done['status'],'failed');self.assertEqual(done['attempts'],0)
        self.assertEqual(self.read_wire,[])

    def test_changed_owner_identity_stops_before_network(self):
        self.collect();raw=self.verifier.registry.model_dump(mode='json');raw['tokens'][self.principal.token_id]['enabled']=False
        self.verifier=HumanAuthVerifier(HumanAuthRegistry.model_validate(raw),max_token_ttl_seconds=86400)
        done=self.analytics.process();self.assertEqual(done['status'],'failed');self.assertEqual(self.read_wire,[])

    def test_response_after_consent_expiry_is_not_an_audience_snapshot(self):
        self.read_mode='expire-after-response';done=self.run_collection();self.assertEqual(done['status'],'failed');self.assertEqual(len(self.read_wire),1)
        self.assertIsNone(done['result']);self.assertEqual(self.analytics.page(self.project['id'])['items'][0]['status'],'failed')

    def test_response_after_owner_revocation_stops_remaining_reads(self):
        self.read_mode='revoke-after-response';done=self.run_collection();self.assertEqual(done['status'],'failed');self.assertEqual(len(self.read_wire),1)
        self.assertIsNone(done['result'])

    def test_cancel_during_response_blocks_remaining_reads_and_snapshot(self):
        self.read_mode='cancel-after-response';done=self.run_collection();self.assertEqual(done['status'],'cancelled');self.assertEqual(len(self.read_wire),1)
        self.assertIsNone(done['result']);self.assertIsNone(self.analytics.process())

    def test_rate_limit_is_durable_backoff_with_distinct_attempt_costs(self):
        self.read_mode='rate-limit';first=self.run_collection(max_attempts=2,acknowledged_bounded_retries=True)
        self.assertEqual(first['status'],'retry_scheduled');self.assertIsNone(self.analytics.process());self.assertEqual(len(self.read_wire),1)
        restarted=NativeOfficialAnalytics(self.service,enabled=True);self.assertIsNone(restarted.process())
        self.clock[0]+=timedelta(seconds=45);self.read_mode=None;done=restarted.process();self.assertEqual(done['status'],'succeeded');self.assertEqual(done['attempts'],2)
        costs=[r for r in restarted.costs.summary(self.project['id'])['records'] if r['provider']=='official-youtube-analytics']
        self.assertEqual(len(costs),4);self.assertEqual(len({r['operation'] for r in costs}),4)

    def test_default_single_attempt_never_retries_rate_limit(self):
        self.read_mode='rate-limit';done=self.run_collection();self.assertEqual(done['status'],'failed');self.clock[0]+=timedelta(seconds=90)
        self.assertIsNone(self.analytics.process());self.assertEqual(len(self.read_wire),1)

    def test_retry_attempt_limit_remains_finite(self):
        self.read_mode='server-error';first=self.run_collection(max_attempts=2,acknowledged_bounded_retries=True)
        self.assertEqual(first['status'],'retry_scheduled');self.clock[0]+=timedelta(seconds=30);done=self.analytics.process()
        self.assertEqual(done['status'],'failed');self.assertEqual(done['attempts'],2);self.assertIsNone(self.analytics.process());self.assertEqual(len(self.read_wire),2)

    def test_unknown_read_outcome_has_no_automatic_retry_or_secret_leak(self):
        self.read_mode='timeout';done=self.run_collection(max_attempts=3,acknowledged_bounded_retries=True)
        self.assertEqual(done['status'],'outcome_unknown');self.assertIsNone(self.analytics.process());self.assertEqual(len(self.read_wire),1)
        self.assertNotIn('EXPLICIT-SECRET',json.dumps(done))

    def test_revenue_requires_monetary_scope_and_keeps_estimates_in_vnd(self):
        self.collect(query={'start_date':'2026-10-01','end_date':'2026-10-07','include_revenue':True})
        done=self.analytics.process();self.assertEqual(done['failure_code'],'ANALYTICS_OAUTH_SCOPES_REQUIRED');self.assertEqual(self.read_wire,[])
        self.read_credential=AnalyticsOAuthCredential(self.target,self.clock[0]+timedelta(hours=1),frozenset({YT_READ,YT_ANALYTICS,YT_MONEY}),'EXPLICIT-ANALYTICS-READ-TOKEN-FIXTURE-0123456789')
        self.metric_values.append(1200.5)
        done=self.run_collection(query={'start_date':'2026-10-01','end_date':'2026-10-07','include_revenue':True},request_key='explicit-monetary-second-fixture-key')
        self.assertEqual(done['status'],'succeeded');self.assertEqual(done['result']['metrics']['revenue'],1200.5)
        self.assertEqual(done['result']['evidence']['currency'],'VND');self.assertIsNone(done['result']['metrics']['rpm'])

    def test_malformed_provider_metrics_never_become_a_snapshot(self):
        self.metric_values[0]=True;done=self.run_collection();self.assertEqual(done['failure_code'],'ANALYTICS_METRIC_INVALID');self.assertIsNone(done['result'])

    def test_unknown_report_header_is_rejected(self):
        self.read_mode='wrong-headers';done=self.run_collection();self.assertEqual(done['failure_code'],'ANALYTICS_REPORT_SHAPE_INVALID');self.assertIsNone(done['result'])

    def test_project_edits_and_expired_publishing_grant_do_not_rewrite_published_features(self):
        with self.store.transaction() as con:
            row=con.execute('SELECT document FROM projects WHERE id=?',(self.project['id'],)).fetchone();document=json.loads(row[0]);document['analytics_features']={'hook_type':'LATER UNPUBLISHED EDIT'}
            con.execute('UPDATE projects SET revision=revision+1,document=? WHERE id=?',(json.dumps(document),self.project['id']));self.store.version(con,self.project['id'])
        self.clock[0]+=timedelta(seconds=901);done=self.run_collection();self.assertEqual(done['status'],'succeeded')
        self.assertIsNone(done['result']['features']['hook_type']);self.assertFalse(done['result']['features']['evidence']['current_project_metadata_used'])

    def test_published_job_metadata_change_stops_new_reads(self):
        self.collect()
        with self.store.transaction() as con:
            row=con.execute('SELECT result FROM jobs WHERE id=?',(self.job['id'],)).fetchone();changed=json.loads(row[0]);changed['qc']['duration_seconds']=900
            con.execute('UPDATE jobs SET result=? WHERE id=?',(json.dumps(changed),self.job['id']))
        done=self.analytics.process();self.assertEqual(done['status'],'failed');self.assertEqual(self.read_wire,[])

    def test_atomic_claim_allows_only_one_active_worker(self):
        self.collect()
        with ThreadPoolExecutor(max_workers=2) as pool:claimed=list(pool.map(lambda _:self.analytics.claim(),range(2)))
        self.assertEqual(sum(v is not None for v in claimed),1);self.assertEqual(self.read_wire,[])
        with self.store.transaction() as con:self.assertEqual(con.execute('SELECT count(*) FROM native_official_analytics_attempts').fetchone()[0],1)

    def test_restart_unknown_claim_never_decrypts_or_replays(self):
        self.collect();self.analytics.claim();restarted=NativeOfficialAnalytics(self.service)
        self.assertEqual(restarted.recover()['recovered'],1);self.assertEqual(restarted.recover()['recovered'],0)
        done=restarted.get(self.project['id'],self.sync['sync_id']);self.assertEqual(done['status'],'outcome_unknown');self.assertIsNone(restarted.process())
        self.assertEqual(self.read_wire,[])

    def test_restart_settles_only_owned_unfinished_read_costs_even_after_journal_recovery(self):
        self.collect();project,identity,claim=self.analytics.claim()
        cost=self.analytics.costs.begin(project_id=project,provider='official-youtube-analytics',model=None,
            operation='analytics_read.'+claim+'.account_lookup',request_sha256='a'*64,estimated_cost=None,external_call=False,paid=False)
        unrelated=self.analytics.costs.begin(project_id=project,provider='official-youtube-analytics',model=None,
            operation='unrelated-operation',request_sha256='b'*64,estimated_cost=None,external_call=False,paid=False)
        with self.store.transaction() as con:
            con.execute("UPDATE native_official_analytics_attempts SET status='outcome_unknown' WHERE attempt_id=?",(claim,))
            con.execute("UPDATE native_official_analytics_syncs SET status='outcome_unknown',claim_id=NULL WHERE sync_id=?",(identity,))
        restored=NativeOfficialAnalytics(self.service);result=restored.recover();self.assertEqual(result['recovered'],0)
        self.assertEqual(result['unfinished_costs_marked_unknown'],1)
        costs={r['id']:r for r in restored.costs.summary(project)['records']};self.assertEqual(costs[cost]['status'],'outcome_unknown')
        self.assertEqual(costs[unrelated]['status'],'dispatch_intent');self.assertEqual(restored.recover()['unfinished_costs_marked_unknown'],0)
        self.assertEqual(self.read_wire,[])

    def test_cancelled_interrupted_claim_cost_is_recovered_without_resuming_reads(self):
        value=self.collect();project,identity,claim=self.analytics.claim()
        cost=self.analytics.costs.begin(project_id=project,provider='official-youtube-analytics',model=None,
            operation='analytics_read.'+claim+'.account_lookup',request_sha256='a'*64,estimated_cost=None,external_call=False,paid=False)
        self.analytics.cancel(project,identity,Cancel(expected_snapshot_sha256=value['snapshot_sha256']),principal=self.principal)
        restored=NativeOfficialAnalytics(self.service);self.assertEqual(restored.recover()['unfinished_costs_marked_unknown'],1)
        self.assertEqual(restored.get(project,identity)['status'],'cancelled');self.assertIsNone(restored.process())
        record=next(r for r in restored.costs.summary(project)['records'] if r['id']==cost);self.assertEqual(record['status'],'outcome_unknown')
        self.assertEqual(self.read_wire,[])

    def test_source_change_between_response_admission_and_write_fails_transaction_fence(self):
        original=self.analytics.admission;changed=[False]
        def admission(*args):
            value=original(*args)
            if len(self.read_wire)==3 and not changed[0]:
                changed[0]=True
                with self.store.transaction() as con:
                    result=json.loads(con.execute('SELECT result FROM jobs WHERE id=?',(self.job['id'],)).fetchone()[0]);result['qc']['duration_seconds']=999
                    con.execute('UPDATE jobs SET result=? WHERE id=?',(json.dumps(result),self.job['id']))
            return value
        with patch.object(self.analytics,'admission',side_effect=admission):done=self.run_collection()
        self.assertEqual(done['status'],'failed');self.assertEqual(done['failure_code'],'NATIVE_OFFICIAL_ANALYTICS_PUBLISHED_SOURCE_CHANGED')
        self.assertIsNone(done['result']);self.assertEqual(len(self.read_wire),3)

    def test_cancel_is_local_idempotent_and_completed_snapshot_is_unchanged(self):
        value=self.collect();payload=Cancel(expected_snapshot_sha256=value['snapshot_sha256'])
        first=self.analytics.cancel(self.project['id'],value['sync_id'],payload,principal=self.principal)
        self.assertEqual(first,self.analytics.cancel(self.project['id'],value['sync_id'],payload,principal=self.principal));self.assertIsNone(self.analytics.process())
        done=self.run_collection(request_key='explicit-after-cancel-analytics-key');result=done['result']
        self.analytics.cancel(self.project['id'],done['sync_id'],Cancel(expected_snapshot_sha256=done['snapshot_sha256']),principal=self.principal)
        self.assertEqual(self.analytics.get(self.project['id'],done['sync_id'])['result'],result)

    def test_rehashed_mock_relabel_or_inferred_metric_is_rejected(self):
        done=self.run_collection();original=done['result']
        for changes in ({'mock':1},{'mock':False,'external_call':True,'real_audience_observation':True,'source_kind':'official_provider'},
            {'metrics':{**original['metrics'],'completion_rate':0.4}},{'remote_post_id':'OTHERID0001'}):
            altered={**original,**changes}
            with self.store.transaction() as con:con.execute('UPDATE native_official_analytics_snapshots SET result_json=?,result_sha256=?',(json.dumps(altered),digest(altered)))
            with self.assertRaisesRegex(WorkflowError,'RESULT_CHANGED'):self.analytics.get(self.project['id'],done['sync_id'])
        with self.store.transaction() as con:con.execute('UPDATE native_official_analytics_snapshots SET result_json=?,result_sha256=?',(json.dumps(original),digest(original)))
        self.assertEqual(self.analytics.get(self.project['id'],done['sync_id'])['result'],original)

    def test_missing_response_or_wrong_cost_scope_invalidates_snapshot(self):
        done=self.run_collection()
        with self.store.transaction() as con:con.execute("UPDATE native_cost_operations SET paid=1 WHERE provider='official-youtube-analytics'")
        with self.assertRaisesRegex(WorkflowError,'RESULT_CHANGED'):self.analytics.get(self.project['id'],done['sync_id'])

    def test_scoped_pagination_and_backup_cover_all_five_journals(self):
        for i in range(3):self.run_collection(request_key='explicit-page-analytics-key-'+str(i))
        first=self.analytics.page(self.project['id'],publication=self.completed['publication_id'],limit=2)
        self.assertTrue(first['truncated']);second=self.analytics.page(self.project['id'],publication=self.completed['publication_id'],limit=2,cursor=first['next_cursor'])
        self.assertEqual(len(second['items']),1);self.assertFalse(second['truncated'])
        with self.assertRaises(WorkflowError):self.analytics.page(self.project['id'],cursor=first['next_cursor'])
        status=database_status(self.root/'workflow.sqlite3');self.assertTrue(all(name in status['counts'] for name in TABLES));self.assertEqual(status['active_operations'],0)

    def test_cold_import_needs_no_api_framework_gpu_or_network(self):
        subprocess.run([sys.executable,'-c',"from services.windows_native.official_analytics import NativeOfficialAnalytics; import sys; assert not any(n.startswith(('fastapi','sqlalchemy','torch','vieneu')) for n in sys.modules)"],cwd=__import__('pathlib').Path(__file__).resolve().parents[3],capture_output=True,check=True,timeout=15)


if __name__=='__main__':unittest.main()
