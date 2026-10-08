"""Signed bounded Native refresh/recovery on a copied genuine local media bundle.

The audience observations and clock advances are explicit fixtures. No provider,
render, TTS, real publication or Owner acceptance is performed by this script.
"""
import argparse
from datetime import datetime, timedelta, timezone
import http.client
import json
from pathlib import Path
import re
import sys
import threading
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from services.windows_native.access import NativeAccess
from services.windows_native.backup import create_backup,restore_backup
from services.windows_native.contracts import file_sha
from services.windows_native.pipeline import Config
from services.windows_native.server import LocalServer
from services.windows_native.store import Store
from services.windows_native.tests.test_human_identity import fixture
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
WORKSPACE='wsp_native_storyboard_full_qc_fixture'

def write(path,value):
    with path.open('x',encoding='utf-8',newline='\n') as handle:json.dump(value,handle,ensure_ascii=False,indent=2,allow_nan=False);handle.write('\n')

def settings(root):
    absent=root.parent/(root.name+'-absent-secrets')
    config=Config(data_root=root,secret_file=absent/'absent-openai.env',assemblyai_secret_file=absent/'absent-asr.dpapi')
    assert not config.secret_file.exists() and not config.assemblyai_secret_file.exists()
    return config

def access(role='owner'):
    token,registry=fixture(role,workspace=WORKSPACE)
    auth=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(registry),max_token_ttl_seconds=86400),WORKSPACE)
    cookie,session=auth.login(token)
    return auth,cookie,session

def run(args):
    root,out=args.data_root.resolve(),args.output.resolve();restored=args.restore_root.resolve()
    for path in [root,restored]:
        if path.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-analytics-refresh-[a-z0-9-]+',path.name) or path.exists():raise ValueError('Fresh owned refresh roots required')
    if out.exists() or out==ROOT or ROOT in out.parents or out in (root,restored) or root in out.parents or restored in out.parents:raise ValueError('Fresh separate evidence required')
    if not re.fullmatch(r'[a-f0-9]{32}',args.project_id):raise ValueError('Exact project required')
    out.mkdir(parents=True);write(out/'initial-restore.json',restore_backup(args.backup,root,expected_sha256=args.expected_sha256))
    auth,cookie,session=access();server=LocalServer(0,settings(root),start_worker=False,access=auth)
    clock=[datetime.now(timezone.utc)];server.analytics.clock=lambda:clock[0];server.analytics_refresh.clock=lambda:clock[0]
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();requests=[]
    def send(method,path,body=None,expected=200):
        conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=30)
        conn.request(method,path,body=json.dumps(body) if body is not None else None,headers={'Content-Type':'application/json','Cookie':'vf_native_session='+cookie,'X-VF-CSRF':session.csrf})
        response=conn.getresponse();value=json.loads(response.read());conn.close()
        requests.append({'method':method,'path':path,'status':response.status})
        assert response.status==expected,(response.status,value);return value
    try:
        base='/api/projects/'+args.project_id;path=base+'/analytics-refresh';original=server.store.get(args.project_id)
        physical={str(p.relative_to(root)).replace('\\','/'):file_sha(p) for d in ('assets','originals','jobs','shot-previews') for p in (root/d).rglob('*') if p.is_file()}
        before=send('GET',base+'/analytics?limit=100');write(out/'history-before.json',before)
        publications=send('GET',base+'/publications?limit=100');pub=next(p for p in publications['items'] if p['status']=='dry_run_succeeded')['publication_id']
        body={'schema_version':'native-analytics-refresh-plan-v1','publication_id':pub,'provider_mode':'fixture','fixture_profile':'normal',
            'fixture_acknowledged':True,'first_run_at':(clock[0]-timedelta(seconds=1)).isoformat(),'interval_hours':1,'max_runs':2,
            'enabled':True,'acknowledged_read_only':True,'request_key':'native-owned-recurring-normal-fixture-policy'}
        plan=send('POST',path,body);write(out/'created-normal-policy.json',plan)
        assert plan['analytics_profile']['channel_profile_ref']=='ai-education-reference@1'
        assert plan['analytics_profile']['channel_analytics_profile']['enabled'] is False
        assert send('POST',path,body)['idempotent_replay']
        first=send('POST',path+'/tick',{});assert len(first['created_sync_ids'])==1
        assert not send('POST',path+'/tick',{})['created_sync_ids'];assert server.runner.run_one()
        first_sync=send('GET',base+'/analytics/'+first['created_sync_ids'][0]);write(out/'first-recurring-sync.json',first_sync)
        assert first_sync['status']=='succeeded' and first_sync['snapshot']['evidence']['refresh_occurrence']['ordinal']==1
        clock[0]+=timedelta(hours=9)
        second=send('POST',path+'/tick',{});assert len(second['created_sync_ids'])==1;assert server.runner.run_one()
        final_plan=send('GET',path+'/'+plan['plan_id']);write(out/'exhausted-normal-policy.json',final_plan)
        assert final_plan['status']=='exhausted' and final_plan['run_count']==2 and final_plan['occurrences'][0]['skipped_slots']==8
        assert not send('POST',path+'/tick',{})['created_sync_ids']
        rate_body={**body,'fixture_profile':'rate_limited','first_run_at':clock[0].isoformat(),'request_key':'native-owned-recurring-rate-fixture-policy'}
        rate=send('POST',path,rate_body);queued=send('POST',path+'/tick',{})['created_sync_ids'][0];assert server.runner.run_one()
        pending=send('GET',base+'/analytics/'+queued);assert pending['status']=='retry_scheduled';write(out/'rate-limited-sync.json',pending)
        state_path=path+'/'+rate['plan_id']+'/state'
        paused=send('POST',state_path,{'expected_revision':1,'enabled':False});assert paused['revision']==2
        cancelled=send('GET',base+'/analytics/'+queued);assert cancelled['status']=='cancelled';write(out/'cancelled-rate-sync.json',cancelled)
        send('POST',state_path,{'expected_revision':1,'enabled':False},expected=409)
        enabled=send('POST',state_path,{'expected_revision':2,'enabled':True,'acknowledged_read_only':True,'fixture_acknowledged':True});assert enabled['revision']==3
        clock[0]+=timedelta(hours=2);retry=send('POST',path+'/tick',{})['created_sync_ids'][0];assert server.runner.run_one()
        clock[0]+=timedelta(seconds=30);assert server.runner.run_one();clock[0]+=timedelta(seconds=60);assert server.runner.run_one()
        failed=send('GET',base+'/analytics/'+retry);assert failed['status']=='failed' and failed['attempts']==3 and failed['snapshot'] is None
        write(out/'exhausted-rate-sync.json',failed);write(out/'exhausted-rate-policy.json',send('GET',path+'/'+rate['plan_id']))
        official=send('POST',path,{**body,'provider_mode':'official','fixture_acknowledged':False,'enabled':False,'query_policy':'rolling_complete_days','lookback_days':7,
            'first_run_at':clock[0].isoformat(),'request_key':'native-owned-official-recurring-not-configured-policy'})
        assert official['status']=='not_configured';write(out/'official-not-configured-policy.json',official)
        send('POST',path+'/'+official['plan_id']+'/state',{'expected_revision':1,'enabled':True,'acknowledged_read_only':True},expected=409)
        auth,cookie,session=access('viewer');auth.bind_root(root);server.access=auth
        send('GET',path+'?limit=100');send('POST',path+'/tick',{},expected=403)
        auth,cookie,session=access();auth.bind_root(root);server.access=auth
        assert not send('POST',path+'/tick',{})['created_sync_ids']
        history=send('GET',base+'/analytics?limit=100');write(out/'history-after.json',history)
        old={r['snapshot']['snapshot_id']:r['snapshot'] for r in before['items'] if r['snapshot']}
        current={r['snapshot']['snapshot_id']:r['snapshot'] for r in history['items'] if r['snapshot']}
        assert len(current)==len(old)+2 and all(current[k]==v for k,v in old.items())
        assert server.store.get(args.project_id)==original and physical=={name:file_sha(root/name) for name in physical}
        write(out/'project-before-and-after.json',original);write(out/'physical-source-hashes.json',physical)
        expected={p['plan_id']:send('GET',path+'/'+p['plan_id']) for p in [plan,rate,official]};write(out/'expected-policies.json',expected)
        write(out/'http-requests.json',requests)
    finally:server.shutdown();server.server_close();thread.join()
    backup=create_backup(settings(root),out/'owned-analytics-refresh.zip');write(out/'backup.json',backup)
    archive=out/'owned-analytics-refresh.zip';write(out/'recovery-restore.json',restore_backup(archive,restored,expected_sha256=file_sha(archive)))
    args.data_root=restored;args.reopen=True;reopen(args)
    names=['services/windows_native/analytics_refresh.py','services/windows_native/analytics_refresh_models.py','services/windows_native/analytics.py',
        'services/windows_native/analytics_routes.py','services/windows_native/server.py','services/windows_native/access.py','services/windows_native/backup.py',
        'services/windows_native/tests/test_analytics_refresh.py','services/windows_native/tests/test_analytics_refresh_http.py',
        'apps/studio-web/native-analytics-refresh.mjs','apps/studio-web/native-analytics.mjs','apps/studio-web/native.mjs','apps/studio-web/native.html',
        'apps/studio-web/tests/native-analytics-refresh.test.mjs','scripts/north_star_native_analytics_refresh.py']
    write(out/'evidence.json',{'schema_version':'native-analytics-refresh-rehearsal-v1','explicit_fixture':True,'simulated_schedule_clock':True,
        'human_http_requests':len(requests),'refresh_plans':3,'occurrences':4,'new_immutable_snapshots':2,'history_project_jobs_media_unchanged':True,
        'frozen_channel_profile':'ai-education-reference@1','channel_profile_not_enabled_by_runtime_policy':True,'official_status':'NOT_CONFIGURED',
        'official_sync_jobs_created':0,'missed_slots_skipped':8,'backoff_attempts':3,'owner_actor_from_signed_identity':True,
        'actual_audience_observed':False,'new_tts_render_or_external_provider_calls':0,'paid_operations':0,'publishing_enabled':False,'owner_uat_accepted':False,
        'source_sha256':{name:file_sha(ROOT/name) for name in names},'exports':{p.name:{'sha256':file_sha(p),'bytes':p.stat().st_size} for p in out.iterdir() if p.is_file()}})
    print(json.dumps({'status':'NATIVE_RECURRING_ANALYTICS_RECOVERY_PASS','requests':len(requests),'new_snapshots':2,'external_calls':0}))

def reopen(args):
    root,out=args.data_root.resolve(),args.output.resolve()
    if root.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-analytics-refresh-[a-z0-9-]+',root.name):raise ValueError('Owned recovery root required')
    auth,_,_=access();server=LocalServer(0,settings(root),start_worker=False,access=auth)
    try:
        expected=json.loads((out/'expected-policies.json').read_text(encoding='utf-8'))
        assert {identity:server.analytics_refresh.get(args.project_id,identity) for identity in expected}==expected
        assert server.store.get(args.project_id)==json.loads((out/'project-before-and-after.json').read_text(encoding='utf-8'))
        physical=json.loads((out/'physical-source-hashes.json').read_text(encoding='utf-8'));assert physical=={name:file_sha(root/name) for name in physical}
        assert server.analytics_refresh.tick()['created_sync_ids']==[] and server.analytics.process() is None
        write(out/('new-process-replay.json' if args.new_process else 'restored-in-process.json'),{'exact_policies':True,'exact_project_jobs_media':True,'new_syncs':0,'new_provider_calls':0,'publishing_enabled':False})
    finally:server.server_close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--backup',type=Path);p.add_argument('--expected-sha256');p.add_argument('--data-root',type=Path,required=True)
    p.add_argument('--restore-root',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--project-id',required=True)
    p.add_argument('--reopen',action='store_true');p.add_argument('--new-process',action='store_true');args=p.parse_args()
    reopen(args) if args.reopen else run(args)
