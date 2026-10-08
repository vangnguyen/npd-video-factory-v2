"""Retained signed HTTP and private synthetic custody; no genuine provider access."""
import argparse,json,re,sys,zipfile
from pathlib import Path
from urllib.parse import urlencode
ROOT=Path('C:/vfns01');sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'apps/api'))
from services.windows_native.tests.test_google_oauth_http import GoogleOAuthHTTPTests
from services.windows_native.google_oauth_operations import Slot,NativeGoogleOAuthOperations
from services.windows_native.google_oauth_vault import PrivateClient,NativeGoogleOAuthVault
from services.windows_native.tests.test_google_oauth_protocol import TOKEN,REFRESH,SECRET,CODE
from services.windows_native.google_oauth_registry import load
from services.windows_native.backup import create_backup,restore_backup,database_status
from services.windows_native.contracts import file_sha
from scripts.north_star_google_oauth_operations import services,journals
from scripts.north_star_google_oauth_vault import acl
PRIVATE=[TOKEN,REFRESH,SECRET,CODE]
def write(path,value):
    raw=json.dumps(value,ensure_ascii=False,indent=2)+'\n';assert all(s not in raw for s in PRIVATE)
    with path.open('x',encoding='utf-8',newline='\n') as h:h.write(raw)
def owned(path,kind,fresh=False):
    path=path.resolve()
    if path.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-google-oauth-http-'+kind+r'-[0-9]{2}',path.name) or fresh and path.exists():raise ValueError('Fresh owned OAuth HTTP root required')
    return path
def reopen(args):
    out=args.output.resolve();root=owned(args.restore_root,'restore');private=owned(args.private_root,'secrets');store,vault,service=services(root,private)
    expected=json.loads((out/'expected-journals.json').read_bytes());current=journals(store)
    # Native server constructors retain additive bridge/trend/worker journals;
    # recovery does not activate any of those services.
    assert current==expected
    project=json.loads((out/'expected-project.json').read_bytes());assert store.get(project['id'])==project
    for kind in ('authorization','operation'):
        for value in json.loads((out/('expected-'+kind+'-history.json')).read_bytes()):assert service.get(project['id'],value[kind+'_id'],kind=kind)==value
    assert service.recover()['provider_calls']==0 and not service.configured() and service.states()['slots']==[]
    references=json.loads((out/'expected-private-receipts.json').read_bytes());assert len(references)==8
    for receipt in references:assert file_sha(vault.path(receipt['reference']))==receipt['cipher_sha256']
    for value in json.loads((out/'expected-operation-history.json').read_bytes()):
        if value['result']:
            slot=Slot.model_validate(value['snapshot']['slot']);c=vault.client(slot.client);assert vault.grant(value['result']['grant_receipt']).public(c)==value['result']['grant_proof']
    absent=NativeGoogleOAuthVault(private.with_name(private.name+'-absent'),root,vault.workspace);history=NativeGoogleOAuthOperations(service.publications,absent)
    for value in json.loads((out/'expected-operation-history.json').read_bytes()):assert history.get(project['id'],value['operation_id'])==value
    assert not absent.directory.exists() and database_status(store.db)['active_operations']==0
    write(out/('new-process-replay.json' if args.new_process else 'restored-in-process.json'),{'all_workflow_journals_original_project_four_authorization_four_operation_histories_eight_private_cipher_refs_two_grant_proofs_exact':True,
        'historical_registry_hash_preserved_without_registry_or_private_mount':True,'provider_calls':0,'startup_decryption_background_refresh_or_publish_enabled':False})
def run(args):
    out=args.output.resolve();private=owned(args.private_root,'secrets',True);restored=owned(args.restore_root,'restore',True)
    if out.exists() or out==ROOT or ROOT in out.parents:raise ValueError('Fresh external signed OAuth evidence required')
    out.mkdir(parents=True);fixture=GoogleOAuthHTTPTests();fixture.setUp();refs=[];exports=[];count=0
    try:
        fixture.vault=NativeGoogleOAuthVault(private,fixture.root,fixture.workspace);slots={}
        for key,slot in fixture.slots.items():
            purpose=slot.client.purpose;c=__import__('services.windows_native.tests.test_google_oauth_protocol',fromlist=['client']).client(purpose)
            receipt=fixture.vault.save_client(PrivateClient(target=c.target,purpose=purpose,credential_alias='explicit-google-'+purpose,client_id=c.client_id,scopes=sorted(c.scopes),client_secret=c.client_secret));refs.append(receipt)
            slots[key]=Slot(slot_id=slot.slot_id,target=slot.target,client=receipt,client_id=slot.client_id,scopes=slot.scopes)
        fixture.slots=slots;path=fixture.registry_file();registry,protected,checksum=load(path,fixture.root,fixture.workspace)
        fixture.operations=NativeGoogleOAuthOperations(fixture.server.official_publications,fixture.vault,slots=slots,client=fixture.wire,enabled=True,registry_file=protected,registry_sha256=checksum)
        fixture.server.google_oauth=fixture.server.runner.google_oauth=fixture.operations
        PRIVATE.append(fixture.raw);original=fixture.store.get(fixture.project['id']);session=fixture.request('GET','/api/session')[1];count+=1
        def request(method,path,body=None):
            nonlocal count
            status,value,headers=fixture.request(method,path,body);assert status==200 and headers['Cache-Control']=='no-store';count+=1;return value
        def start(name,purpose='analytics'):
            saved=fixture.start_http(purpose,request_key=name);fixture.saved=saved
            nonlocal count
            count+=1;flow=fixture.vault.authorization(saved['snapshot']['authorization_receipt']);PRIVATE.extend([flow.state,flow.verifier]);refs.append(saved['snapshot']['authorization_receipt']);return saved
        prepared=start('explicit-retained-signed-google-start-key');binding={'expected_snapshot_sha256':prepared['snapshot_sha256']};base=fixture.base+'/authorizations/'+prepared['authorization_id']
        url=request('POST',base+'/authorization-url',binding);assert url['external_human_browser_required'] and url['authorization_url'].startswith('https://accounts.google.com/o/oauth2/v2/auth?')
        done=request('POST',base+'/exchange',{**binding,'callback_query':fixture.query()});assert done['status']=='succeeded';fixture.done=done;refs.append(done['result']['grant_receipt'])
        new=request('POST',fixture.base+'/refresh',fixture.refresh_payload().model_dump(mode='json'));assert new['status']=='succeeded';refs.append(new['result']['grant_receipt'])
        assert request('POST',fixture.base+'/refresh',fixture.refresh_payload().model_dump(mode='json'))==new
        fixture.mode='timeout';prepared=start('explicit-retained-signed-google-unknown-key','publishing');binding={'expected_snapshot_sha256':prepared['snapshot_sha256']}
        unknown=request('POST',fixture.base+'/authorizations/'+prepared['authorization_id']+'/exchange',{**binding,'callback_query':fixture.query()});assert unknown['status']=='outcome_unknown';fixture.operations.recover()
        fixture.mode=None;prepared=start('explicit-retained-signed-google-denial-key','publishing');flow=fixture.vault.authorization(prepared['snapshot']['authorization_receipt'])
        denial=request('POST',fixture.base+'/authorizations/'+prepared['authorization_id']+'/exchange',{'expected_snapshot_sha256':prepared['snapshot_sha256'],'callback_query':urlencode({'state':flow.state,'error':'access_denied','error_description':SECRET})})
        assert denial['status']=='failed' and denial['cost_operation_id'] is None
        prepared=start('explicit-retained-signed-google-cancel-key');cancelled=request('POST',fixture.base+'/authorizations/'+prepared['authorization_id']+'/cancel',{'expected_snapshot_sha256':prepared['snapshot_sha256']});assert cancelled['status']=='cancelled'
        histories={kind:request('GET',fixture.base+'/'+('authorizations' if kind=='authorization' else 'operations'))['items'] for kind in ('authorization','operation')}
        assert all(len(v)==4 for v in histories.values()) and fixture.store.get(fixture.project['id'])==original and len(fixture.calls)==3 and not fixture.server.runner.run_one()
        assert request('GET','/api/session')==session
        assert len(refs)==8 and all(acl(p) for p in private.glob('*.dpapi')) and all(file_sha(fixture.vault.path(r['reference']))==r['cipher_sha256'] for r in refs)
        for kind,values in histories.items():write(out/('expected-'+kind+'-history.json'),values)
        write(out/'expected-project.json',original);write(out/'expected-private-receipts.json',refs);write(out/'mock-wire-summary.json',fixture.calls);write(out/'http-observations.json',fixture.logs);write(out/'cost.json',fixture.operations.costs.summary(original['id']))
        fixture.server.shutdown();fixture.server.server_close();fixture.thread.join();write(out/'expected-journals.json',journals(fixture.store))
        backup=create_backup(fixture.config,out/'public-signed-oauth.zip');write(out/'backup.json',backup)
        with zipfile.ZipFile(out/'public-signed-oauth.zip') as archive:
            assert not any(n.endswith(('.dpapi','.part')) for n in archive.namelist());assert all(s.encode() not in archive.read(n) for n in archive.namelist() for s in PRIVATE)
        write(out/'recovery-restore.json',restore_backup(out/'public-signed-oauth.zip',restored,expected_sha256=backup['sha256']));reopen(args)
        source=['services/windows_native/google_oauth_registry.py','services/windows_native/google_oauth_routes.py','services/windows_native/google_oauth_operations.py','services/windows_native/server.py','services/windows_native/access.py','services/windows_native/tests/test_google_oauth_http.py']
        write(out/'evidence.json',{'schema_version':'native-google-oauth-http-rehearsal-v1','signed_http_requests':count,'mock_token_requests':3,'grant_generations':2,'authorization_histories':4,'operation_histories':4,
            'private_synthetic_cipher_files':8,'private_acl_verified':True,'public_registry_hash_and_original_source_cost_provenance':True,'private_authorization_url_not_exported':True,'session_fields_project_and_worker_no_automatic_provider_work':True,
            'public_only_backup_fresh_restore_and_unmounted_history_exact':True,'journal_count':len(journals(fixture.store)),'studio_automatic_external_browser_callback_account_or_credential_resolver_integrated':False,
            'real_secret_reads':0,'external_provider_calls':0,'paid_operations':0,'real_publications':0,'real_audience_observations':0,'new_media_operations':0,'browser_owner_provider_production_acceptance':False,
            'source_sha256':{n:file_sha(ROOT/n) for n in source},'exports':{p.name:{'sha256':file_sha(p),'bytes':p.stat().st_size} for p in out.iterdir() if p.is_file()}})
        print(json.dumps({'status':'PASS','signed_http_requests':count,'mock_token_requests':3,'private_synthetic_files':8,'fresh_restore_exact':True,'external_calls':0}))
    finally:
        fixture.tearDown()
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--private-root',type=Path,required=True);p.add_argument('--restore-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--reopen',action='store_true');p.add_argument('--new-process',action='store_true');a=p.parse_args();reopen(a) if a.reopen else run(a)
