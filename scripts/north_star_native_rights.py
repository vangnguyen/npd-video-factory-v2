"""Actual owned playable clone, unverified rights review/gates and offline recovery.

No media rerender, provider result, external publication, legal override or Owner UAT.
"""
import argparse,http.client,json,re,subprocess,sys,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from services.windows_native.access import NativeAccess
from services.windows_native.backup import create_backup,restore_backup
from services.windows_native.contracts import digest,file_sha
from services.windows_native.server import LocalServer
from services.windows_native.rights import NativeRights
from services.windows_native.source_assets import canonical_assets
from services.windows_native.tests.test_human_identity import fixture
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
from north_star_native_bridge import read_state,config,WORKSPACE


class NoProvider:
    def run(self,*_):raise AssertionError('No provider/media dispatch in rights rehearsal')


def state(root):
    result=read_state(root)
    from services.windows_native.store import Store
    store=Store(root);service=NativeRights(store,workspace_id=WORKSPACE)
    result['rights']={row['id']:service.page(row['id']) for row in result['projects']}
    with store.transaction() as con:
        result['rights_receipts']=[dict(row) for row in con.execute('SELECT * FROM native_rights_requests ORDER BY project_id,key_sha256')]
        result['publications']=[dict(row) for row in con.execute('SELECT * FROM native_publications ORDER BY publication_id')]
    return result


def run(args):
    root=args.data_root.resolve();destination=args.restore_root.resolve();out=args.output.resolve();parent=args.parent_evidence.resolve()
    for path in [root,destination]:
        if path.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-rights-[a-z0-9-]+',path.name) or path.exists():raise ValueError('Fresh owned rights roots required')
    if root==destination:raise ValueError('Distinct roots required')
    proof=json.loads((parent/'evidence.json').read_bytes());recovery=json.loads((parent/'recovery.json').read_bytes())
    assert proof['actual_hub_calls']==0 and proof['local_real_full_qc'] and proof['explicit_synthetic_owned_provenance_seed'] and not proof['owner_uat']
    out.mkdir(parents=True,exist_ok=False)
    restored=restore_backup(parent/'native-bridge-backup.zip',root,expected_sha256=recovery['backup']['sha256'])
    token,registry=fixture('owner',workspace=WORKSPACE);access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(registry),max_token_ttl_seconds=86400),WORKSPACE)
    server=LocalServer(0,config(root),pipeline=NoProvider(),start_worker=False,access=access);cookie,session=access.login(token)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();calls=[]
    before=state(root);artifacts={p.relative_to(root).as_posix():file_sha(p) for name in ['assets','originals','jobs','shot-previews'] for p in (root/name).rglob('*') if p.is_file()}
    def account(role):
        nonlocal cookie,session
        raw,data=fixture(role,workspace=WORKSPACE);controller=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400),WORKSPACE)
        controller.bind_root(root);server.access=controller;cookie,session=controller.login(raw)
    def request(method,path,body=None,*,status=200):
        connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=10)
        connection.request(method,path,body=json.dumps(body) if body is not None else None,headers={'Content-Type':'application/json','Cookie':'vf_native_session='+cookie,'X-VF-CSRF':session.csrf})
        response=connection.getresponse();value=json.loads(response.read());headers=dict(response.getheaders());connection.close()
        calls.append({'method':method,'path':path,'status':response.status});assert response.status==status,(response.status,value);assert headers['Cache-Control']=='no-store';return value
    try:
        project=next(row for row in before['projects'] if row['id']==proof['project_id']);job=next(row for row in project['jobs'] if row['id']==proof['job_id'])
        assets=canonical_assets(project['document']);asset=next(row for row in assets if row['kind']=='video')
        base='/api/projects/'+project['id'];page=request('GET',base+'/rights');assert page['owner_override_enabled'] is False
        # Known ownership belongs solely to the original locally-generated
        # synthetic pixels. A later human claim is deliberately unverified.
        assert next(row for row in page['items'] if row['asset_id']==asset['id'])['rights_status']=='owned'
        intent=request('POST',base+'/publications',{'revision':job['revision'],'final_job_id':job['id'],'platform':'youtube',
            'metadata':{'title':'EXPLICIT RIGHTS WITHDRAWAL DRY-RUN FIXTURE','privacy':'private'},'request_key':'native-rights-playable-publication-key'})
        assert intent['snapshot']['validation']['status']=='passed'
        approval={'expected_fingerprint':intent['request_fingerprint'],'expected_artifact_sha256':intent['snapshot']['final_sha256'],'acknowledged':True}
        request('POST',base+'/publications/'+intent['publication_id']+'/approve',approval)
        body={'revision':project['revision'],'asset_sha256':asset['sha256'],'claimed_source_type':'user_upload','claimed_rights':'licensed',
            'license':'EXPLICIT HUMAN CLAIM FIXTURE, NOT VERIFIED','provider':'owner-fixture','source_reference':'document://fixture-public-proof',
            'creator':'EXPLICIT SYNTHETIC FIXTURE','acknowledged':True,'request_key':'native-rights-playable-declaration-key'}
        account('viewer');request('GET',base+'/rights');request('POST',base+'/rights/'+asset['id'],body,status=403)
        account('editor');request('POST',base+'/rights/'+asset['id'],body,status=403);account('owner')
        request('POST',base+'/rights/'+asset['id'],{**body,'owner_override':True},status=400)
        declared=request('POST',base+'/rights/'+asset['id'],body);assert not declared['declaration']['verified'] and declared['approval_invalidated']
        replay=request('POST',base+'/rights/'+asset['id'],body);assert replay['idempotent_replay'] and replay['declaration']==declared['declaration']
        request('POST',base+'/rights/'+asset['id'],{**body,'request_key':'native-rights-playable-stale-fixture'},status=409)
        request('POST',base+'/publications/'+intent['publication_id']+'/approve',approval,status=409)
        blocked=request('POST',base+'/publications/'+intent['publication_id']+'/dry-run',{'expected_fingerprint':intent['request_fingerprint']})
        assert blocked['status']=='blocked' and blocked['receipt'] is None and not blocked['external_action']
        current=server.store.get(project['id']);assert current['approval'] is None
        restricted=request('POST',base+'/rights/'+asset['id'],{**body,'revision':current['revision'],'claimed_rights':'restricted','request_key':'native-rights-playable-restricted-key'})
        later=request('POST',base+'/rights/'+asset['id'],body);assert later['idempotent_replay'] and later['declaration']==declared['declaration']
        final_page=request('GET',base+'/rights');row=next(row for row in final_page['items'] if row['asset_id']==asset['id'])
        assert row['rights_status']=='restricted' and not row['declaration']['verified'] and row['license']==asset['license'] and row['provider']==asset.get('provider')
        after=state(root)
        for old in before['projects']:
            current=next(row for row in after['projects'] if row['id']==old['id'])
            if old['id']==project['id']:
                assert current['jobs']==old['jobs'] and current['revision']==old['revision']+2
                assert after['versions'][old['id']][2:]==before['versions'][old['id']]
            else:assert current==old and after['versions'][old['id']]==before['versions'][old['id']]
        assert all(file_sha(root/name)==sha for name,sha in artifacts.items())
        proof_out={'schema_version':'native-rights-contract-v1','project_id':project['id'],'final_job_id':job['id'],
            'parent_final_sha256':proof['final_sha256'],'parent_preview_sha256':proof['preview_sha256'],'authenticated_http_requests':len(calls),
            'human_claim_remains_unverified':True,'owner_override_enabled':False,'existing_approval_invalidated':True,'historical_approved_publish_intent_blocked':True,
            'frozen_idempotent_replay_after_newer_restriction':True,'source_render_job_and_old_versions_unchanged':True,'other_projects_unchanged':True,
            'physical_media_unchanged':True,'actual_media_rerendered':False,'actual_provider_calls':0,'actual_hub_calls':0,'actual_publications':0,
            'real_credentials_read':0,'owner_uat':False,'browser_real_tested':False,'production_deployed':False}
        for name,value in [('contract.json',proof_out),('http-requests.json',calls),('initial-rights.json',page),('declaration.json',declared),
            ('restricted-declaration.json',restricted),('final-rights.json',final_page),('blocked-publication.json',blocked),('events.json',after['events']),('source-restore.json',restored)]:
            (out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    finally:server.shutdown();server.server_close();thread.join(timeout=5)
    frozen=state(root);restart=json.loads(subprocess.check_output([sys.executable,str(Path(__file__).resolve()),'--read-root',str(root)],timeout=60));assert restart==frozen
    backup=create_backup(config(root),out/'native-rights-backup.zip');receipt=restore_backup(out/'native-rights-backup.zip',destination,expected_sha256=backup['sha256'])
    fresh=json.loads(subprocess.check_output([sys.executable,str(Path(__file__).resolve()),'--read-root',str(destination)],timeout=60));assert fresh==frozen
    assert all(file_sha(destination/name)==sha for name,sha in artifacts.items())
    (out/'recovery.json').write_text(json.dumps({'backup':backup,'restore':receipt,'new_process_exact':True,'fresh_root_restore_exact':True,
        'default_disabled_on_restore':True,'parent_media_unchanged':True},indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'rights':'PASS','authenticated_http_requests':len(calls),'historical_publish_intent':'BLOCKED','unverified_claims':2,
        'restart_restore':'PASS','actual_provider_calls':0,'owner_uat':False}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data-root',type=Path);parser.add_argument('--restore-root',type=Path)
    parser.add_argument('--output',type=Path);parser.add_argument('--parent-evidence',type=Path);parser.add_argument('--read-root',type=Path);args=parser.parse_args()
    if args.read_root:print(json.dumps(state(args.read_root),ensure_ascii=True))
    else:run(args)
