"""Preserved playable Native dry-run publications -> explicit analytics fixtures -> restore."""
import argparse
import http.client
import json
from pathlib import Path
import subprocess
import sys
import threading

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from services.windows_native.access import NativeAccess
from services.windows_native.analytics import NativeAnalytics
from services.windows_native.contracts import file_sha
from services.windows_native.pipeline import Config
from services.windows_native.publications import NativePublications
from services.windows_native.server import LocalServer
from services.windows_native.store import Store
from services.windows_native.tests.test_human_identity import fixture
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier


WORKSPACE='wsp_native_publication_fixture'
def read(root,project):
    store=Store(root);pubs=NativePublications(store,ROOT/'packages/contracts/publishing-capabilities.json',workspace_id=WORKSPACE)
    analytics=NativeAnalytics(store,pubs);page=analytics.page(project,limit=100)
    return {'project':store.get(project),'publications':pubs.page(project,limit=100),'history':page,
        'details':[analytics.get(project,row['sync_id']) for row in page['items']],'overview':analytics.overview(limit=100)}


class NoProvider:
    def run(self,*_):raise AssertionError('No content/provider dispatch in analytics rehearsal')


def run(args):
    root=Path(args.data_root).resolve();out=Path(args.output).resolve();media=Path(args.media_evidence).resolve()
    if root.parent!=Path('C:/') or not root.name.startswith('vf-native-fixture-publication-') or not root.is_dir():raise ValueError('Owned fixture required')
    proof=json.loads((media/'evidence.json').read_text(encoding='utf-8'))
    if not proof.get('local_real_full_qc') or not proof.get('explicit_fixture_owned_provenance') or proof.get('owner_uat'):raise ValueError('Synthetic playable proof required')
    out.mkdir(parents=True,exist_ok=False);project=proof['project_id'];store=Store(root)
    pubs=NativePublications(store,ROOT/'packages/contracts/publishing-capabilities.json',workspace_id=WORKSPACE)
    existing=pubs.page(project,limit=100);assert len(existing['items'])==4 and all(row['status']=='dry_run_succeeded' for row in existing['items'])
    before_project=store.get(project);files={path.relative_to(root).as_posix():file_sha(path) for folder in ['assets','originals','jobs/'+proof['job_id']] for path in (root/folder).rglob('*') if path.is_file()}
    absent=root.parent/(root.name+'-absent-secrets');config=Config(data_root=root,secret_file=absent/'absent-openai.env',assemblyai_secret_file=absent/'absent-asr.dpapi')
    raw,registry=fixture('owner',workspace=WORKSPACE);access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(registry),max_token_ttl_seconds=86400),WORKSPACE)
    server=LocalServer(0,config,pipeline=NoProvider(),start_worker=False,access=access);cookie,session=access.login(raw)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();calls=[];results=[]
    def request(method,path,body=None):
        connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=20)
        connection.request(method,path,body=json.dumps(body) if body is not None else None,headers={'Content-Type':'application/json',
            'Cookie':'vf_native_session='+cookie,'X-VF-CSRF':session.csrf})
        response=connection.getresponse();headers=dict(response.getheaders());value=json.loads(response.read());connection.close()
        calls.append({'method':method,'path':path,'status':response.status});assert response.status==200,(response.status,value)
        assert headers['Cache-Control']=='no-store';return value
    try:
        base=f'/api/projects/{project}/analytics'
        provider_state=request('GET','/api/analytics/providers');assert not provider_state['external_calls_enabled']
        for pub in existing['items']:
            body={'publication_id':pub['publication_id'],'provider_mode':'fixture','fixture_acknowledged':True,
                'fixture_profile':'insufficient_data','request_key':'native-playable-analytics-fixture-'+pub['snapshot']['request']['platform']}
            value=request('POST',base,body);assert value['status']=='queued'
            duplicate=request('POST',base,body);assert duplicate['idempotent_replay'] and duplicate['sync_id']==value['sync_id']
            route=base+'/'+value['sync_id'];done=request('POST',route+'/process',{'expected_fingerprint':value['request_fingerprint']})
            assert done['status']=='succeeded' and done['snapshot']['mock'] and not done['snapshot']['external_call']
            assert done['snapshot']['metrics']['completion_rate'] is None and done['snapshot']['metrics']['revenue'] is None
            assert done['snapshot']['assessment']['state']=='insufficient_data' and done['snapshot']['features']['publishing_time'] is None
            repeat=request('POST',route+'/process',{'expected_fingerprint':value['request_fingerprint']});assert repeat==done;results.append(done)
        first=results[0];pub=first['publication_id']
        refresh=request('POST',base,{'publication_id':pub,'provider_mode':'fixture','fixture_acknowledged':True,'fixture_profile':'normal',
            'trigger':'manual_refresh','request_key':'native-playable-analytics-new-refresh-key'})
        refreshed=request('POST',base+'/'+refresh['sync_id']+'/process',{'expected_fingerprint':refresh['request_fingerprint']})
        assert refreshed['snapshot']['snapshot_id']!=first['snapshot_id'] and request('GET',base+'/'+first['sync_id'])==first
        official=request('POST',base,{'publication_id':pub,'provider_mode':'official','request_key':'native-official-acceptance-not-configured-key'})
        official_done=request('POST',base+'/'+official['sync_id']+'/process',{'expected_fingerprint':official['request_fingerprint']})
        assert official_done['status']=='not_configured' and official_done['snapshot'] is None
        history=request('GET',base+'?limit=3');assert len(history['items'])==3 and history['next_cursor']
        from urllib.parse import quote
        second=request('GET',base+'?limit=3&cursor='+quote(history['next_cursor']));assert len(second['items'])==3 and second['next_cursor'] is None
        overview=request('GET','/api/analytics/overview?limit=2');assert len(overview['items'])==2 and overview['next_cursor']
        overview_next=request('GET','/api/analytics/overview?limit=2&cursor='+quote(overview['next_cursor']))
        assert len({row['publication_id'] for row in overview['items']+overview_next['items']})==4 and overview_next['next_cursor'] is None
        assert overview['account_totals'] is None and not overview['channel_account_verified']
        assert server.store.get(project)==before_project and server.publications.page(project,limit=100)==existing
        assert all(file_sha(root/name)==sha for name,sha in files.items())
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)
    expected=read(root,project)
    restored=json.loads(subprocess.check_output([sys.executable,str(Path(__file__).resolve()),'--read-root',str(root),'--project',project],timeout=60));assert restored==expected
    def write(name,value):
        with (out/name).open('x',encoding='utf-8') as file:json.dump(value,file,ensure_ascii=False,indent=2)
    write('initial-observations.json',results);write('refresh-observation.json',refreshed);write('official-unavailable.json',official_done)
    write('provider-states.json',provider_state);write('history-pages.json',[history,second]);write('overview-pages.json',[overview,overview_next])
    write('restored-state.json',restored);write('requests.json',{'authenticated_native_requests':calls,'actual_external_calls':0})
    summary={'status':'PASS','authenticated_native_requests':len(calls),'mock_collections':5,'historical_snapshots':5,'platforms':4,
        'fresh_process_exact_restore':True,'missing_metrics_preserved_as_null':True,'old_history_after_refresh_unchanged':True,
        'frozen_published_render_features':True,'publication_history_unchanged':True,'canonical_project_and_media_unchanged':True,
        'provider_posted_time':None,'account_totals':None,'channel_account_verified':False,'official_state':'NOT_CONFIGURED',
        'final_sha256':files['jobs/'+proof['job_id']+'/final.mp4'],'prior_playable_media_evidence':str(media),
        'media_local_real_full_qc':True,'source_is_synthetic_testsrc_and_tone':True,'saved_asr_fixture':True,
        'real_provider_calls':0,'actual_external_calls':0,'real_credentials_read':0,'paid_calls':0,
        'owner_uat_accepted':False,'real_audience_observation':False,'real_channel_baseline_verified':False,
        'analytics_ready':False,'winner_detection_ready':False,'learning_loop_ready':False,'implementation_complete':False,'production_deployed':False}
    write('contract.json',summary);print(json.dumps({'status':'PASS','output':str(out),'mock_collections':5,'requests':len(calls),'fresh_process_restore':True}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data-root');parser.add_argument('--media-evidence');parser.add_argument('--output');parser.add_argument('--read-root');parser.add_argument('--project');args=parser.parse_args()
    if args.read_root:print(json.dumps(read(args.read_root,args.project),ensure_ascii=True))
    elif args.output:run(args)
    else:parser.error('--output or --read-root required')
