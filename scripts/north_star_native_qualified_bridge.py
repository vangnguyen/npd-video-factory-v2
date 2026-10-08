"""Owned signed qualified source events and offline restore, never actual Hub."""
import argparse,json,re,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.north_star_native_official_learning import rows,settings,write
from scripts.north_star_native_qualified_learning import services,intelligence_rows
from services.windows_native.tests.test_qualified_bridge_http import QualifiedBridgeHTTPTests,KEY
from services.windows_native.bridge import NativeBridge
from services.windows_native.bridge_transport import FixtureWebhookTransport,BridgeResponse
from services.windows_native.qualified_bridge_sources import CONTRACT
from services.windows_native.contracts import digest,file_sha
from services.windows_native.backup import create_backup,restore_backup,database_status
from app.bridge_auth import SigningKeyring

BRIDGE_TABLES=('native_bridge_bindings','native_bridge_nonces','native_bridge_requests','native_bridge_events','native_bridge_deliveries','native_bridge_attempts','native_bridge_cursors','native_bridge_selections')
def bridge_rows(store):
    with store.transaction() as con:return {name:[dict(r) for r in con.execute('SELECT * FROM '+name+' ORDER BY rowid')] for name in BRIDGE_TABLES}
def source_rows(store):
    value=intelligence_rows(store)
    with store.transaction() as con:value['native_bridge_source_events']=[dict(r) for r in con.execute('SELECT * FROM native_bridge_source_events ORDER BY sequence')]
    return value
def owned(path,fresh=False):
    path=path.resolve()
    if path.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-qualified-bridge-[a-z0-9-]+',path.name) or fresh and path.exists():raise ValueError('Fresh owned qualified Bridge root required')
    return path
def reopen(args):
    root,out=owned(args.restore_root),args.output.resolve();parts=services(root,out)
    store,journal,queue,analytics,winners,learning,intelligence,radar,feedback,planner=parts
    try:
        bridge=NativeBridge(store,workspace_id=learning.workspace);bridge.attach_intelligence(intelligence.store)
        bridge.bind_qualified_sources(analytics=analytics,winner=winners,learning=learning,projection=feedback)
        assert rows(store)==json.loads((out/'expected-journals.json').read_bytes()) and bridge_rows(store)==json.loads((out/'expected-bridge-journals.json').read_bytes())
        assert source_rows(intelligence.store)==json.loads((out/'expected-intelligence-journals.json').read_bytes())
        assert bridge.page(limit=100)==json.loads((out/'expected-bridge-page.json').read_bytes())
        assert bridge.audit(json.loads((out/'expected-delivery-audit.json').read_bytes())['event_id'])==json.loads((out/'expected-delivery-audit.json').read_bytes())
        for name,service,field in [('publications',journal,'publication_id'),('analytics-history',analytics,'sync_id'),('winner-history',winners,'assessment_id'),('learning-history',learning,'learning_id')]:
            values=json.loads((out/('expected-'+name+'.json')).read_bytes());assert len(values)==1
            for value in values:assert service.get(value['project_id'],value[field])==value
        record=json.loads((out/'expected-projection.json').read_bytes());assert feedback.get(record['id'])==record
        for value in json.loads((out/'expected-projects.json').read_bytes()):assert store.get(value['id'])==value
        for value in json.loads((out/'expected-jobs.json').read_bytes()):assert store.get_job(value['id'])==value
        physical=json.loads((out/'physical-fixture-artifacts.json').read_bytes());assert physical=={name:file_sha(root/name) for name in physical}
        assert database_status(store.db)['active_operations']==0 and not queue.configured() and queue.process() is None
        assert not analytics.states()['enabled'] and analytics.states()['accounts']==[] and analytics.process() is None and journal.states()['profiles']==[]
        assert not bridge.delivery_enabled and bridge.verifier is None and bridge.process() is None and bridge.harvest()==0
        write(out/('new-process-replay.json' if args.new_process else 'restored-in-process.json'),{
            'one_receipt_observation_assessment_learning_projection_four_qualified_events_24_workflow_eight_bridge_five_intelligence_journals_exact':True,
            'original_project_job_files_hashes_and_signed_delivery_audit_exact':True,'providers_queue_credentials_service_auth_and_webhook_delivery_enabled':False,
            'new_media_provider_or_network_operations':0,'real_audience_observations':0,'explicit_nonplayable_fixture':True})
    finally:radar.close()
def run(args):
    out=args.output.resolve();restored=owned(args.restore_root,True)
    if out.exists() or out==ROOT or ROOT in out.parents or out==restored or restored in out.parents:raise ValueError('Fresh external qualified Bridge evidence required')
    out.mkdir(parents=True);fixture=QualifiedBridgeHTTPTests();original=fixture.request;http=[]
    def request(method,path,body=None,headers=None):
        status,value,metadata=original(method,path,body,headers)
        http.append({'method':method,'path':path,'status':status,'request_sha256':digest(body),'response_sha256':digest(value) if isinstance(value,(dict,list)) else None,'cache_control':metadata.get('Cache-Control')})
        return status,value,metadata
    fixture.request=request;fixture.setUp()
    try:
        store=fixture.server.store;bridge=fixture.bridge;project=fixture.project['id'];before=store.get(project);job=store.get_job(fixture.job['id']);receipt=fixture.completed
        assert len(fixture.read_wire)==3 and len(fixture.wire)==10;value=fixture.project_feedback();record=value['record']
        assert bridge.harvest()==1 and bridge.harvest()==0;assert fixture.service_read('/v1/contract')[0]==200
        status,page,_=fixture.service_read('/v1/events?limit=25');assert status==200 and len(page['items'])==4
        assert all(e['envelope']['contract_version']==CONTRACT and e['envelope']['payload']['mock'] and not e['envelope']['payload']['real_audience_observation'] for e in page['items'])
        assert all(e['envelope']['event_type']!='video.winner.detected' for e in page['items']);wire=[];signing=SigningKeyring('fixture-v1',{'fixture-v1':KEY});stamp=[1791410400.0];bridge.clock=lambda:stamp[0]
        def receiver(body,headers):
            event=json.loads(body);assert signing.verify(body,key_id=headers['X-NPD-Key-Id'],timestamp=int(headers['X-NPD-Timestamp']),event_id=event['event_id'],signature=headers['X-NPD-Signature'])
            assert headers['Idempotency-Key']==event['event_id'];wire.append({'event_id':event['event_id'],'body_sha256':digest(event),'signature_verified':True,'mock':True,'actual_hub_call':False})
            if len(wire)==1:raise TimeoutError('EXPLICIT FIXTURE RECEIVER REPLY LOST')
            return BridgeResponse(204)
        bridge.configure_delivery(transport=FixtureWebhookTransport(receiver),signing=signing,enabled=True)
        state=request('GET','/api/bridge/state')[1];selected=next(e for e in page['items'] if e['envelope']['payload']['source_type']=='projection')
        body={'expected_envelope_sha256':selected['envelope_sha256'],'expected_destination_sha256':state['destination_sha256'],'expected_mode':'fixture','fixture_acknowledged':True,'http_acknowledged':False,'request_key':'explicit-qualified-retained-fixture-selection'}
        selection=request('POST','/api/bridge/events/'+selected['envelope']['event_id']+'/enqueue',body)[1];assert selection['selected_status']=='queued'
        bridge.process();stamp[0]+=10;bridge.process();assert len(wire)==2 and wire[0]==wire[1]
        audit=request('GET','/api/bridge/events/'+selected['envelope']['event_id']+'/delivery')[1];assert audit['delivery']['status']=='succeeded' and audit['fixture'] and not audit['real_hub_receipt_verified']
        bridge.configure_delivery(transport=FixtureWebhookTransport(receiver),signing=signing,enabled=False)
        page=request('GET','/api/bridge/events?limit=25')[1];assert not page['delivery_enabled'] and bridge.process() is None
        served={}
        for name in ('native-bridge.mjs','native.html','native.mjs'):
            status,value,_=request('GET','/'+name);assert status==200 and value==(ROOT/'apps/studio-web'/name).read_bytes();served[name]={'sha256':file_sha(ROOT/'apps/studio-web'/name),'bytes':len(value)}
        assert store.get(project)==before and store.get_job(job['id'])==job and len(fixture.read_wire)==3 and len(fixture.wire)==10
        for name,value in [('publications',[receipt]),('analytics-history',[fixture.observation]),('winner-history',[fixture.assessment]),('learning-history',[fixture.learned]),('projects',[before]),('jobs',[job])]:write(out/('expected-'+name+'.json'),value)
        write(out/'expected-projection.json',record);write(out/'expected-bridge-page.json',page);write(out/'expected-delivery-audit.json',audit)
        write(out/'expected-journals.json',rows(store));write(out/'expected-bridge-journals.json',bridge_rows(store));write(out/'expected-intelligence-journals.json',source_rows(fixture.server.intelligence.store))
        write(out/'fixture-capabilities.json',json.loads(fixture.caps.read_bytes()));write(out/'mock-read-wire-summary.json',fixture.read_wire);write(out/'mock-publication-wire-summary.json',fixture.wire);write(out/'signed-fixture-delivery-wire.json',wire);write(out/'served-studio-files.json',served)
        physical={p.relative_to(fixture.root).as_posix():file_sha(p) for p in (fixture.root/'jobs').rglob('*') if p.is_file()};write(out/'physical-fixture-artifacts.json',physical)
        costs=fixture.analytics.costs.summary(project);write(out/'cost-summary.json',costs);assert all(r['actual_cost'] is None and not r['paid'] and not r['external_call'] for r in costs['records'])
        backup=create_backup(settings(fixture.root),out/'owned-qualified-bridge.zip');write(out/'backup.json',backup)
        with zipfile.ZipFile(out/'owned-qualified-bridge.zip') as archive:
            assert all(not n.endswith(('.dpapi','.part')) for n in archive.namelist())
            assert all(fixture.credential.token.encode() not in archive.read(n) and fixture.read_credential.token.encode() not in archive.read(n) and b'upload_id=EXPLICIT-PRIVATE-FIXTURE' not in archive.read(n) for n in archive.namelist())
        write(out/'recovery-restore.json',restore_backup(out/'owned-qualified-bridge.zip',restored,expected_sha256=backup['sha256']));args.restore_root=restored;reopen(args)
        prior=Path('C:/Users/PC/Documents/ChatGPT/Video Factory/recovery/20261007/native-qualified-learning-controls-flow-n2');old=services(Path('C:/vf-native-fixture-qualified-learning-controls-restore-02'),prior)
        try:
            assert rows(old[0])==json.loads((prior/'expected-journals.json').read_bytes()) and intelligence_rows(old[6].store)==json.loads((prior/'expected-intelligence-journals.json').read_bytes())
            for row in json.loads((prior/'expected-projections.json').read_bytes()):assert old[8].get(row['id'])==row
        finally:old[7].close()
        write(out/'legacy-qualified-controls-replay.json',{'prior_24_workflow_four_intelligence_journals_projection_original_sources_exact':True,'external_calls':0})
        write(out/'signed-http-summary.json',http);write(out/'sanitized-operation-logs.json',[json.loads(v) for v in fixture.operation_logs])
        sources=['services/windows_native/'+name for name in ('bridge.py','qualified_bridge_sources.py','server.py','official_analytics.py','official_winners.py','official_learning.py','qualified_learning_feedback.py','tests/test_qualified_bridge.py','tests/test_qualified_bridge_http.py','tests/test_qualified_learning_feedback.py','tests/test_official_analytics_http.py','tests/test_official_winner_http.py','tests/test_official_learning_http.py','tests/test_qualified_learning_feedback_http.py')]+['apps/studio-web/native-bridge.mjs','apps/studio-web/tests/native-bridge.test.mjs','apps/api/tests/test_qualified_feedback_event_contract.py','packages/contracts/agent-hub-qualified-feedback.v1.schema.json','scripts/north_star_native_qualified_bridge.py']
        write(out/'evidence.json',{'schema_version':'native-qualified-bridge-rehearsal-v1','signed_http_requests':len(http),'qualified_events':4,'signed_fixture_delivery_attempts':2,'distinct_fixture_receiver_events':1,'mock_analytics_read_requests':3,'mock_publication_wire_requests':10,'mock_initial_account_lookup_requests':1,
            'legacy_v1_event_contract_unchanged_separate_qualified_contract':True,'all_source_receipt_response_cost_assessment_learning_projection_bindings_verified_on_read_and_delivery':True,'four_sparse_mock_events_no_winner_claim':True,'one_reply_loss_same_signed_body_idempotency_key_and_source_event':True,
            '24_workflow_eight_bridge_five_intelligence_journals_project_job_files_original_sources_and_delivery_audit_restore_exact':True,'prior_qualified_controls_original_sources_exact':True,'explicit_nonplayable_qc_rights_oauth_account_metrics_identity_and_clock_fixtures':True,
            'real_publications':0,'real_audience_observations':0,'actual_hub_calls':0,'external_provider_calls':0,'paid_operations':0,'new_render_or_inference_calls':0,'browser_owner_receiver_provider_or_production_acceptance':False,
            'source_sha256':{name:file_sha(ROOT/name) for name in sources},'exports':{p.name:{'sha256':file_sha(p),'bytes':p.stat().st_size} for p in out.iterdir() if p.is_file()}})
        print(json.dumps({'status':'NATIVE_QUALIFIED_BRIDGE_RECOVERY_PASS','signed_http_requests':len(http),'qualified_events':4,'signed_fixture_attempts':2,'actual_hub_calls':0,'external_calls':0,'explicit_nonplayable_fixture':True}))
    finally:fixture.tearDown()
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--restore-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--reopen',action='store_true');p.add_argument('--new-process',action='store_true')
    args=p.parse_args();reopen(args) if args.reopen else run(args)
