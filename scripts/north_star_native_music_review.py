"""Owned synthetic Source rehearsal: signed music review, revoke/copy and recovery.

All legal/human decisions are fixtures. No real publication or Owner UAT.
"""
import argparse,http.client,json,re,sys,threading
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from services.windows_native.access import NativeAccess
from services.windows_native.backup import create_backup,restore_backup
from services.windows_native.contracts import file_sha
from services.windows_native.pipeline import Config,Pipeline
from services.windows_native.server import LocalServer
from services.windows_native.store import Store
from services.windows_native.tests.test_human_identity import fixture
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
WORKSPACE='wsp_native_music_review_fixture'
def write(path,value):
    with path.open('x',encoding='utf-8',newline='\n') as h:json.dump(value,h,ensure_ascii=False,indent=2,allow_nan=False);h.write('\n')
def snapshot(root):
    store=Store(root);projects=[store.get(p['id']) for p in store.list(include_archived=True)]
    with store.transaction() as con:
        rows={name:[dict(r) for r in con.execute('SELECT * FROM '+name+' ORDER BY rowid')] for name in
            ['events','native_rights_requests','native_rights_override_requests']}
        jobs=[store.job(r,con) for r in con.execute('SELECT * FROM jobs ORDER BY id')]
    return {'projects':projects,'versions':{p['id']:store.versions(p['id']) for p in projects},'jobs':jobs,'rows':rows,
        'files':{str(p.relative_to(root)).replace('\\','/'):file_sha(p) for d in ('assets','originals','jobs','shot-previews') for p in sorted((root/d).rglob('*')) if p.is_file()}}
def config(root):
    absent=root.parent/(root.name+'-absent-secrets')
    return Config(data_root=root,secret_file=absent/'absent-openai.env',assemblyai_secret_file=absent/'absent-asr.dpapi')
def run(args):
    root,destination,out=args.data_root.resolve(),args.restore_root.resolve(),args.output.resolve()
    if root.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-music-crossfade-[a-z0-9-]+',root.name) or not root.is_dir():raise ValueError('Retained owned synthetic music root required')
    if destination.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-music-crossfade-restore-[a-z0-9-]+',destination.name):raise ValueError('Owned restore root required')
    if args.reopen:
        expected=json.loads((out/'offline-snapshot.json').read_bytes());assert snapshot(root)==snapshot(destination)==expected
        for location in [root,destination]:
            with patch('services.windows_native.source_render.command_run',side_effect=AssertionError('Verified historical replay must not rerender')):
                for job in snapshot(location)['jobs']:
                    if job['kind']=='render' and job['status']=='succeeded':assert Pipeline(config(location)).run(job,lambda _:None)==job['result']
        write(out/'new-process-replay.json',{'exact_source_restored_state':True,'exact_historical_render_checkpoint_replay':True,
            'new_render_or_external_provider_calls':0,'owner_uat_accepted':False});print('MUSIC_REVIEW_RESTART_RESTORE_PASS');return
    if destination.exists() or out.exists() or out==ROOT or ROOT in out.parents or out==root or root in out.parents:raise ValueError('Fresh distinct external evidence/restore required')
    out.mkdir(parents=True);settings=config(root);store=Store(root);projects=store.list();assert len(projects)==1
    identifier=projects[0]['id'];raw,registry=fixture('owner',workspace=WORKSPACE)
    access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(registry),max_token_ttl_seconds=86400),WORKSPACE)
    server=LocalServer(0,settings,start_worker=False,access=access,owner_rights_overrides=True);cookie,session=access.login(raw)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();requests=[]
    def send(method,path,body=None):
        connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=30)
        connection.request(method,path,body=json.dumps(body) if body is not None else None,headers={'Content-Type':'application/json',
            'Cookie':'vf_native_session='+cookie,'X-VF-CSRF':session.csrf})
        response=connection.getresponse();value=json.loads(response.read());connection.close()
        requests.append({'method':method,'path':path,'status':response.status});assert response.status==200,(response.status,value);return value
    try:
        base='/api/projects/'+identifier;project=send('GET',base);canonical=project['document']['canonical_timeline'];music=project['document']['music']
        physical={d+'/'+music[k]:file_sha(root/d/music[k]) for d,k in [('assets','id'),('originals','original_id')]}
        declaration={'revision':project['revision'],'asset_sha256':music['sha256'],'claimed_source_type':'user_upload','claimed_rights':'owned',
            'provider':'explicit-owner-fixture','source_reference':'upload://'+music['original_id'],'acknowledged':True,'request_key':'music-review-declaration-fixture'}
        first=send('POST',base+'/rights/'+music['id'],declaration);write(out/'declaration.json',first)
        assert send('POST',base+'/rights/'+music['id'],declaration)['idempotent_replay']
        project=send('GET',base);page=send('GET',base+'/rights-overrides');asset=next(a for a in page['items'] if a['asset_id']==music['id'])
        assert asset['rights_status']=='unknown' and project['approval'] is None and project['document']['canonical_timeline']==canonical
        request={'revision':project['revision'],'asset_sha256':music['sha256'],'expected_rights_sha256':asset['rights_sha256'],'action':'grant',
            'reason':'EXPLICIT SYNTHETIC MUSIC RIGHTS EXCEPTION, NOT LEGAL CLEARANCE','evidence_reference':'document://explicit-music-review-fixture',
            'valid_days':7,'allow_publishing_review':True,'acknowledged':True,'request_key':'music-review-grant-fixture'}
        grant=send('POST',base+'/rights-overrides/'+music['id'],request);write(out/'grant.json',grant)
        assert send('POST',base+'/rights-overrides/'+music['id'],request)['idempotent_replay']
        page=send('GET',base+'/rights-overrides');assert next(a for a in page['items'] if a['asset_id']==music['id'])['active_override']==grant['record']
        project=send('GET',base);copied=send('POST',base+'/duplicate',{'revision':project['revision']});write(out/'duplicate.json',copied)
        assert copied['approval'] is None and 'media_rights_declarations' not in copied['document'] and 'media_rights_overrides' not in copied['document']
        revoke={**request,'revision':project['revision'],'action':'revoke','override_id':grant['record']['override_id'],
            'expected_override_sha256':grant['record']['sha256'],'allow_publishing_review':False,'request_key':'music-review-revoke-fixture'}
        server.rights_overrides.enabled=False
        write(out/'revocation.json',send('POST',base+'/rights-overrides/'+music['id'],revoke));server.rights_overrides.enabled=True
        page=send('GET',base+'/rights-overrides');write(out/'review-history.json',page)
        assert next(a for a in page['items'] if a['asset_id']==music['id'])['active_override'] is None
        project=send('GET',base);assert project['document']['canonical_timeline']==canonical and project['document']['music']['rights_status']=='unknown'
        assert physical=={name:file_sha(root/name) for name in physical}
    finally:server.shutdown();server.server_close();thread.join()
    state=snapshot(root);write(out/'offline-snapshot.json',state)
    backup=create_backup(settings,out/'owned-music-review.zip');write(out/'backup.json',backup)
    write(out/'restore.json',restore_backup(out/'owned-music-review.zip',destination,expected_sha256=backup['sha256']));assert snapshot(destination)==state
    write(out/'http-requests.json',requests)
    names=['services/windows_native/audio_loudness.py','services/windows_native/source_music.py','services/windows_native/source_render.py',
        'services/windows_native/rights.py','services/windows_native/rights_override.py','services/windows_native/server.py',
        'services/windows_native/store.py','scripts/north_star_native_music_review.py']
    write(out/'evidence.json',{'schema':'native-music-review-evidence-v1','explicit_fixture':True,'human_http_requests':len(requests),
        'actual_music_bytes_unchanged':True,'declaration_exception_retries':True,'revoke_after_disable':True,'duplicate_without_authority':True,
        'canonical_timeline_unchanged':True,'raw_rights_unknown':True,'rights_independently_verified':False,'publishing_enabled':False,
        'both_database_backup_restore':True,'owner_uat_accepted':False,'external_provider_calls':0,'paid_operations':0,
        'source_sha256':{name:file_sha(ROOT/name) for name in names},'exports':{p.name:{'sha256':file_sha(p),'bytes':p.stat().st_size} for p in out.iterdir() if p.is_file()}})
    print(json.dumps({'status':'MUSIC_REVIEW_RECOVERY_PASS','human_http_requests':len(requests)}))
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data-root',type=Path,required=True);parser.add_argument('--restore-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--reopen',action='store_true');run(parser.parse_args())
