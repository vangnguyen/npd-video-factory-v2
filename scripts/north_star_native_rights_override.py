"""Checksum-cloned playable evidence, explicit synthetic Owner exception and recovery.

No uncertain real asset is cleared. No render, provider, post, deployment or Owner UAT.
"""
import argparse,http.client,json,re,subprocess,sys,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from services.windows_native.access import NativeAccess
from services.windows_native.backup import create_backup,restore_backup
from services.windows_native.contracts import file_sha
from services.windows_native.server import LocalServer
from services.windows_native.rights import NativeRights
from services.windows_native.rights_override import NativeRightsOverrides,rights_sha
from services.windows_native.source_assets import canonical_assets
from services.windows_native.tests.test_human_identity import fixture
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
from north_star_native_bridge import read_state,config,WORKSPACE


class NoProvider:
    def run(self,*_):raise AssertionError('No provider/media dispatch in exception rehearsal')


def state(root):
    result=read_state(root)
    from services.windows_native.store import Store
    store=Store(root);service=NativeRightsOverrides(store,workspace_id=WORKSPACE)
    result['rights_overrides']={row['id']:service.page(row['id']) for row in result['projects']}
    with store.transaction() as con:
        result['override_receipts']=[dict(row) for row in con.execute('SELECT * FROM native_rights_override_requests ORDER BY project_id,key_sha256')]
    return result


def run(args):
    root=args.data_root.resolve();destination=args.restore_root.resolve();out=args.output.resolve();parent=args.parent_evidence.resolve()
    for path in [root,destination]:
        if path.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-rights-override-[a-z0-9-]+',path.name) or path.exists():raise ValueError('Fresh owned exception roots required')
    if root==destination:raise ValueError('Distinct roots required')
    proof=json.loads((parent/'evidence.json').read_bytes());recovery=json.loads((parent/'recovery.json').read_bytes())
    assert proof['actual_hub_calls']==0 and proof['local_real_full_qc'] and proof['explicit_synthetic_owned_provenance_seed'] and not proof['owner_uat']
    out.mkdir(parents=True,exist_ok=False)
    restored=restore_backup(parent/'native-bridge-backup.zip',root,expected_sha256=recovery['backup']['sha256'])
    token,registry=fixture('owner',workspace=WORKSPACE);access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(registry),max_token_ttl_seconds=86400),WORKSPACE)
    server=LocalServer(0,config(root),pipeline=NoProvider(),start_worker=False,access=access,owner_rights_overrides=True);cookie,session=access.login(token)
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
        project=next(row for row in before['projects'] if row['id']==proof['project_id']);asset=next(row for row in canonical_assets(project['document']) if row['kind']=='video')
        base='/api/projects/'+project['id'];initial=request('GET',base+'/rights-overrides');assert initial['enabled'] and not initial['publishing_enabled'] and initial['history']==[]
        # The original synthetic bytes have known test ownership. First make a
        # deliberately unverified human claim; this does not clear a real asset.
        declared=request('POST',base+'/rights/'+asset['id'],{'revision':project['revision'],'asset_sha256':asset['sha256'],'claimed_source_type':'user_upload',
            'claimed_rights':'owned','source_reference':'document://explicit-synthetic-fixture','acknowledged':True,'request_key':'native-override-playable-claim-fixture-key'})
        current=server.store.get(project['id']);asset=next(a for a in canonical_assets(current['document']) if a['id']==asset['id']);assert asset['rights_status']=='unknown'
        body={'revision':current['revision'],'asset_sha256':asset['sha256'],'expected_rights_sha256':rights_sha(asset),'action':'grant',
            'reason':'EXPLICIT SYNTHETIC OWNER EXCEPTION, NO REAL LEGAL REVIEW','evidence_reference':'document://explicit-original-generated-fixture',
            'valid_days':7,'allow_publishing_review':True,'acknowledged':True,'request_key':'native-override-playable-grant-fixture-key'}
        account('viewer');request('GET',base+'/rights-overrides');request('POST',base+'/rights-overrides/'+asset['id'],body,status=403)
        account('editor');request('POST',base+'/rights-overrides/'+asset['id'],body,status=403);account('owner')
        request('POST',base+'/rights-overrides/'+asset['id'],{**body,'publishing_authorized':True},status=400)
        granted=request('POST',base+'/rights-overrides/'+asset['id'],body);assert not granted['record']['publishing_authorized'] and granted['approval_invalidated']
        replay=request('POST',base+'/rights-overrides/'+asset['id'],body);assert replay['idempotent_replay'] and replay['record']==granted['record']
        page=request('GET',base+'/rights-overrides');assert next(a for a in page['items'] if a['asset_id']==asset['id'])['active_override']==granted['record']
        current=server.store.get(project['id']);assert canonical_assets(current['document'])==canonical_assets(server.store.versions(project['id'])[1]['document'])
        child=request('POST',base+'/duplicate',{'revision':current['revision']});assert child['approval'] is None
        child_review=request('GET','/api/projects/'+child['id']+'/rights-overrides')
        child_asset=next(a for a in canonical_assets(child['document']) if a['id']==asset['id'])
        assert child_asset['rights_status']=='unknown' and child_asset['rights_review_required'] is True
        assert not child['document'].get('media_rights_declarations') and not child['document'].get('media_rights_overrides')
        assert all(a['active_override'] is None for a in child_review['items'])
        from services.windows_native.source_broll import shared_assets
        support=next(a for a in shared_assets(child,config(root),rights_overrides=server.rights_overrides).values() if a.provenance['native_asset_id']==asset['id'])
        assert support.provenance['rights_status']=='unknown' and support.provenance['owner_rights_override'] is None
        server.rights_overrides.enabled=False
        disabled=request('GET',base+'/rights-overrides');assert not disabled['enabled'] and all(a['active_override'] is None for a in disabled['items'])
        revoked=request('POST',base+'/rights-overrides/'+asset['id'],{**body,'revision':current['revision'],'action':'revoke','allow_publishing_review':False,
            'override_id':granted['record']['override_id'],'expected_override_sha256':granted['record']['sha256'],'request_key':'native-override-playable-revoke-fixture-key'})
        later=request('POST',base+'/rights-overrides/'+asset['id'],body);assert later['idempotent_replay'] and later['record']==granted['record']
        final=request('GET',base+'/rights-overrides');assert len(final['history'])==2 and not final['enabled']
        after=state(root)
        for old in before['projects']:
            saved=next(row for row in after['projects'] if row['id']==old['id'])
            if old['id']==project['id']:
                assert saved['jobs']==old['jobs'] and saved['revision']==old['revision']+3 and saved['approval'] is None
                assert after['versions'][old['id']][3:]==before['versions'][old['id']]
            else:assert saved==old and after['versions'][old['id']]==before['versions'][old['id']]
        assert all(file_sha(root/name)==sha for name,sha in artifacts.items())
        result={'schema_version':'native-owner-rights-contract-v1','project_id':project['id'],'parent_final_sha256':proof['final_sha256'],
            'parent_preview_sha256':proof['preview_sha256'],'authenticated_http_requests':len(calls),'explicit_synthetic_owner_exception':True,
            'independent_rights_verification':False,'publishing_authorized':False,'rights_remain_unknown':True,'revoke_after_disabling':True,
            'frozen_replay_after_revocation':True,'old_jobs_versions_media_unchanged':True,'actual_media_rerendered':False,
            'derived_project_id':child['id'],'derived_review_required_preserved':True,'derived_exception_authority_transferred':False,
            'derived_broll_rights_remain_unknown':True,
            'actual_provider_calls':0,'actual_hub_calls':0,'actual_publications':0,'paid_operations':0,'real_credentials_read':0,
            'owner_uat':False,'browser_real_tested':False,'production_deployed':False}
        for name,value in [('contract.json',result),('http-requests.json',calls),('initial-review.json',initial),('declaration.json',declared),
            ('grant.json',granted),('revocation.json',revoked),('final-review.json',final),('derived-project.json',child),('derived-review.json',child_review),
            ('events.json',after['events']),('source-restore.json',restored)]:
            (out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    finally:server.shutdown();server.server_close();thread.join(timeout=5)
    frozen=state(root);restart=json.loads(subprocess.check_output([sys.executable,str(Path(__file__).resolve()),'--read-root',str(root)],timeout=60));assert restart==frozen
    backup=create_backup(config(root),out/'native-owner-rights-backup.zip');receipt=restore_backup(out/'native-owner-rights-backup.zip',destination,expected_sha256=backup['sha256'])
    fresh=json.loads(subprocess.check_output([sys.executable,str(Path(__file__).resolve()),'--read-root',str(destination)],timeout=60));assert fresh==frozen
    assert all(file_sha(destination/name)==sha for name,sha in artifacts.items())
    (out/'recovery.json').write_text(json.dumps({'backup':backup,'restore':receipt,'new_process_exact':True,'fresh_root_restore_exact':True,
        'default_disabled_on_restore':True,'parent_media_unchanged':True},indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'owner_exception':'PASS','authenticated_http_requests':len(calls),'rights':'UNKNOWN','publishing_authorized':False,'restart_restore':'PASS','actual_provider_calls':0,'owner_uat':False}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data-root',type=Path);parser.add_argument('--restore-root',type=Path)
    parser.add_argument('--output',type=Path);parser.add_argument('--parent-evidence',type=Path);parser.add_argument('--read-root',type=Path);args=parser.parse_args()
    if args.read_root:print(json.dumps(state(args.read_root),ensure_ascii=True))
    else:run(args)
