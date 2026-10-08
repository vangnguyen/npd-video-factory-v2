"""Signed historical fixture observations on an isolated restored narrated bundle.

Append-only test scenarios, never actual audience, external sync or publication.
"""
import argparse,http.client,json,re,sys,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from services.windows_native.access import NativeAccess
from services.windows_native.backup import restore_backup,create_backup
from services.windows_native.contracts import file_sha
from services.windows_native.pipeline import Config
from services.windows_native.server import LocalServer
from services.windows_native.store import Store
from services.windows_native.tests.test_human_identity import fixture
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
WORKSPACE='wsp_native_storyboard_full_qc_fixture'
def write(path,value):
    with path.open('x',encoding='utf-8',newline='\n') as h:json.dump(value,h,ensure_ascii=False,indent=2,allow_nan=False);h.write('\n')
def run(args):
    root,out=args.data_root.resolve(),args.output.resolve()
    if root.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-analytics-visuals-[a-z0-9-]+',root.name) or root.exists():raise ValueError('Fresh owned analytics root required')
    if out.exists() or out==ROOT or ROOT in out.parents or out==root or root in out.parents:raise ValueError('Fresh distinct evidence required')
    if not re.fullmatch(r'[a-f0-9]{32}',args.project_id):raise ValueError('Exact project required')
    out.mkdir(parents=True);write(out/'initial-restore.json',restore_backup(args.backup,root,expected_sha256=args.expected_sha256))
    absent=root.parent/(root.name+'-absent-secrets');settings=Config(data_root=root,secret_file=absent/'absent-openai.env',assemblyai_secret_file=absent/'absent-asr.dpapi')
    assert not settings.secret_file.exists() and not settings.assemblyai_secret_file.exists()
    raw,registry=fixture('owner',workspace=WORKSPACE);access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(registry),max_token_ttl_seconds=86400),WORKSPACE)
    server=LocalServer(0,settings,start_worker=False,access=access);cookie,session=access.login(raw)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();requests=[]
    def send(method,path,body=None):
        connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=30)
        connection.request(method,path,body=json.dumps(body) if body is not None else None,headers={'Content-Type':'application/json','Cookie':'vf_native_session='+cookie,'X-VF-CSRF':session.csrf})
        response=connection.getresponse();value=json.loads(response.read());connection.close();requests.append({'method':method,'path':path,'status':response.status})
        assert response.status==200,(response.status,value);return value
    try:
        base='/api/projects/'+args.project_id;original=server.store.get(args.project_id);jobs=original['jobs']
        physical={str(p.relative_to(root)).replace('\\','/'):file_sha(p) for d in ('assets','originals','jobs','shot-previews') for p in (root/d).rglob('*') if p.is_file()}
        before=send('GET',base+'/analytics?limit=100');write(out/'history-before.json',before)
        publications=send('GET',base+'/publications?limit=100');complete=next(p for p in publications['items'] if p['status']=='dry_run_succeeded');publication=complete['publication_id']
        for profile in ['winner_candidate','insufficient_data','underperforming']:
            request={'publication_id':publication,'provider_mode':'fixture','fixture_acknowledged':True,'fixture_profile':profile,'trigger':'manual_refresh','request_key':'analytics-visuals-'+profile+'-fixture'}
            row=send('POST',base+'/analytics',request);result=send('POST',base+'/analytics/'+row['sync_id']+'/process',{'expected_fingerprint':row['request_fingerprint']})
            assert result['status']=='succeeded' and result['snapshot']['mock'] and not result['snapshot']['evidence']['real_audience_observation']
            write(out/(profile+'-snapshot.json'),result['snapshot'])
            assert send('POST',base+'/analytics',request)['idempotent_replay']
        official=send('POST',base+'/analytics',{'publication_id':publication,'provider_mode':'official','trigger':'manual_refresh','request_key':'analytics-visuals-official-not-configured-fixture'})
        assert official['status']=='not_configured' and official['attempts']==0 and official.get('snapshot') is None;write(out/'official-not-configured.json',official)
        page=send('GET',base+'/analytics?limit=100&publication_id='+publication);write(out/'analytics-page.json',page)
        overview=send('GET','/api/analytics/overview?limit=100');write(out/'workspace-overview.json',overview)
        assert len([r for r in page['items'] if r['snapshot']])==4
        old={r['snapshot']['snapshot_id']:r['snapshot'] for r in before['items'] if r['snapshot']};current={r['snapshot']['snapshot_id']:r['snapshot'] for r in page['items'] if r['snapshot']}
        assert all(current[k]==v for k,v in old.items());assert server.store.get(args.project_id)==original
        assert physical=={name:file_sha(root/name) for name in physical};assert overview['account_totals'] is None and overview['channel_account_verified'] is False
        write(out/'http-requests.json',requests)
    finally:server.shutdown();server.server_close();thread.join()
    write(out/'backup.json',create_backup(settings,out/'owned-analytics-visuals.zip'))
    with Store(root).transaction() as con:write(out/'historical-snapshot-rows.json',[dict(r) for r in con.execute('SELECT * FROM native_analytics_snapshots ORDER BY collected_at,snapshot_id')])
    names=['apps/studio-web/native-analytics.mjs','apps/studio-web/native.html','apps/studio-web/native.css',
        'apps/studio-web/tests/native-analytics-visuals.test.mjs','scripts/north_star_native_analytics_visuals.py']
    write(out/'evidence.json',{'schema':'native-analytics-visuals-rehearsal-v1','explicit_fixture':True,'human_http_requests':len(requests),
        'historical_snapshots':4,'new_fixture_scenarios':3,'existing_history_unchanged':True,'project_jobs_media_unchanged':True,
        'fixture_profiles_are_distinct_test_scenarios_not_audience_trajectory':True,'official_status':'NOT_CONFIGURED','official_attempts':0,
        'actual_audience_observed':False,'new_tts_render_or_external_provider_calls':0,'paid_operations':0,'publishing_enabled':False,'owner_uat_accepted':False,
        'source_sha256':{name:file_sha(ROOT/name) for name in names},'exports':{p.name:{'sha256':file_sha(p),'bytes':p.stat().st_size} for p in out.iterdir() if p.is_file()}})
    print(json.dumps({'status':'ANALYTICS_VISUAL_HISTORY_PASS','requests':len(requests),'snapshots':4,'real_audience':False}))
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--backup',type=Path,required=True);parser.add_argument('--expected-sha256',required=True)
    parser.add_argument('--data-root',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--project-id',required=True);run(parser.parse_args())
