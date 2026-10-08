"""Owned synthetic Owner/one-use OAuth/cost journals and fresh offline recovery."""
import argparse,asyncio,json,re,sys,zipfile
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlencode,parse_qs
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from services.windows_native.google_oauth_operations import NativeGoogleOAuthOperations,Slot,Start,Refresh
from services.windows_native.google_oauth_vault import NativeGoogleOAuthVault,PrivateClient
from services.windows_native.store import Store
from services.windows_native.publications import NativePublications
from services.windows_native.official_accounts import NativeOfficialAccounts
from services.windows_native.official_publications import NativeOfficialPublications
from services.windows_native.tests.test_google_oauth_protocol import client,TOKEN,REFRESH,SECRET,CODE
from services.windows_native.tests.test_human_identity import fixture as human_fixture
from services.windows_native.tests.test_publications import CAPABILITIES
from services.windows_native.contracts import file_sha
from services.windows_native.backup import create_backup,restore_backup,database_status
from scripts.north_star_native_official_learning import settings
from scripts.north_star_google_oauth_vault import acl
from app.google_oauth_protocol import GoogleOAuthTokenClient,TOKEN_URL
from app.human_identity import HumanAuthVerifier,HumanAuthRegistry
import httpx
WORKSPACE='wsp_google_oauth_fixture'
PRIVATE=[TOKEN,REFRESH,SECRET,CODE]
def write(path,value):
    raw=json.dumps(value,ensure_ascii=False,indent=2)+'\n';assert all(secret not in raw for secret in PRIVATE)
    with path.open('x',encoding='utf-8',newline='\n') as h:h.write(raw)
def owned(path,kind,fresh=False):
    path=path.resolve()
    if path.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-google-oauth-operations-'+kind+r'-[0-9]{2}',path.name) or fresh and path.exists():raise ValueError('Fresh owned OAuth operations fixture required')
    return path
def journals(store):
    with store.transaction() as con:
        names=[r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        return {name:[dict(r) for r in con.execute('SELECT * FROM "'+name+'" ORDER BY rowid')] for name in names}
def services(root,private,*,verifier=None,clock=None,slots=None,wire=None,enabled=False):
    store=Store(root);clock=clock or (lambda:datetime.now(timezone.utc));publications=NativePublications(store,CAPABILITIES,workspace_id=WORKSPACE,clock=clock)
    accounts=NativeOfficialAccounts(store,workspace_id=WORKSPACE,clock=clock);review=NativeOfficialPublications(store,publications,accounts,identity_provider=verifier,clock=clock)
    vault=NativeGoogleOAuthVault(private,root,WORKSPACE);service=NativeGoogleOAuthOperations(review,vault,slots=slots,client=wire,enabled=enabled)
    return store,vault,service
def reopen(args):
    out=args.output.resolve();restored=owned(args.restore_root,'restore');private=owned(args.private_root,'secrets');store,vault,service=services(restored,private)
    assert journals(store)==json.loads((out/'expected-journals.json').read_bytes())
    project=json.loads((out/'expected-project.json').read_bytes());assert store.get(project['id'])==project
    for kind in ('authorization','operation'):
        for value in json.loads((out/('expected-'+kind+'-history.json')).read_bytes()):assert service.get(project['id'],value[kind+'_id'],kind=kind)==value
    assert service.states()['enabled'] is False and service.states()['slots']==[] and service.recover()['provider_calls']==0
    references=json.loads((out/'expected-private-receipts.json').read_bytes())
    for receipt in references:assert file_sha(vault.path(receipt['reference']))==receipt['cipher_sha256']
    for value in json.loads((out/'expected-operation-history.json').read_bytes()):
        if value['result']:
            slot=Slot.model_validate(value['snapshot']['slot']);c=vault.client(slot.client);assert vault.grant(value['result']['grant_receipt']).public(c)==value['result']['grant_proof']
    absent=NativeGoogleOAuthVault(private.with_name(private.name+'-absent'),restored,WORKSPACE)
    assert not absent.directory.exists();service=NativeGoogleOAuthOperations(service.publications,absent)
    for value in json.loads((out/'expected-operation-history.json').read_bytes()):assert service.get(project['id'],value['operation_id'])==value
    assert database_status(store.db)['active_operations']==0
    write(out/('new-process-replay.json' if args.new_process else 'restored-in-process.json'),{'original_journals_project_four_operation_three_authorization_histories_and_seven_private_cipher_receipts_exact':True,
        'explicit_private_mount_grant_proofs_exact':True,'unmounted_history_reads_do_not_resolve_credentials':True,'startup_decryption_background_refresh_publish_account_or_provider_enabled':False,'provider_calls':0})
async def run(args):
    out=args.output.resolve();state=owned(args.state_root,'state',True);private=owned(args.private_root,'secrets',True);restored=owned(args.restore_root,'restore',True)
    if out.exists() or out==ROOT or ROOT in out.parents:raise ValueError('Fresh external OAuth evidence required')
    out.mkdir(parents=True);state.mkdir();(state/'.vf-auth-workspace.json').write_text(json.dumps({'schema':'vf-native-workspace-binding-v1','workspace_id':WORKSPACE}),encoding='utf-8')
    stamp=datetime.now(timezone.utc);raw,data=human_fixture('owner',workspace=WORKSPACE);PRIVATE.append(raw);verifier=HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400);principal=verifier.verify('Bearer '+raw)
    store,vault,base=services(state,private,verifier=lambda:verifier,clock=lambda:stamp);project=store.create('Explicit synthetic OAuth operation recovery','','media');slots={};refs=[];calls=[]
    for purpose,char in (('analytics','a'),('publishing','b')):
        c=client(purpose);receipt=vault.save_client(PrivateClient(target=c.target,purpose=purpose,credential_alias='explicit-google-'+purpose,client_id=c.client_id,scopes=sorted(c.scopes),client_secret=c.client_secret));refs.append(receipt)
        slot=Slot(slot_id='ngos_'+char*32,target=c.target,client=receipt,client_id=c.client_id,scopes=sorted(c.scopes));slots[slot.slot_id]=slot
    mode=['success'];purpose=['analytics']
    def response(request):
        assert request.method=='POST' and str(request.url)==TOKEN_URL;fields=parse_qs(request.content.decode());calls.append({'method':request.method,'host':request.url.host,'path':request.url.path,'operation':fields['grant_type'][0],'mock':True})
        if mode[0]=='timeout':raise httpx.ReadTimeout('EXPLICIT SYNTHETIC UNKNOWN OAUTH; NO RETRY',request=request)
        c=client(purpose[0]);return httpx.Response(200,json={'access_token':TOKEN+str(len(calls)),'refresh_token':REFRESH+str(len(calls)),'token_type':'Bearer','expires_in':3600,'scope':' '.join(sorted(c.scopes))})
    wire=GoogleOAuthTokenClient(transport=httpx.MockTransport(response));service=NativeGoogleOAuthOperations(base.publications,vault,slots=slots,client=wire,enabled=True)
    async def start_and_exchange(name,selected='analytics',deny=False):
        purpose[0]=selected;slot=slots['ngos_'+('a' if selected=='analytics' else 'b')*32]
        payload=Start(revision=1,slot_id=slot.slot_id,expected_configuration_sha256=slot.client.configuration_sha256,acknowledged_credential_operation=True,acknowledged_protocol_mock=True,
            redirect_uri='http://127.0.0.1:18047/oauth/google/callback',request_key=name)
        prepared,_found=service.start(project['id'],payload,principal=principal);flow=vault.authorization(prepared['snapshot']['authorization_receipt']);PRIVATE.extend([flow.state,flow.verifier]);refs.append(prepared['snapshot']['authorization_receipt'])
        query=urlencode({'state':flow.state,'error':'access_denied','error_description':SECRET} if deny else {'state':flow.state,'code':CODE})
        result=await service.exchange(project['id'],prepared['authorization_id'],query,principal=principal,expected_snapshot_sha256=prepared['snapshot_sha256'])
        return prepared,result
    first,original=await start_and_exchange('explicit-retained-google-initial-key');assert original['status']=='succeeded';refs.append(original['result']['grant_receipt'])
    slot=slots[first['snapshot']['request']['slot_id']];refresh=Refresh(revision=1,slot_id=slot.slot_id,expected_configuration_sha256=slot.client.configuration_sha256,acknowledged_credential_operation=True,acknowledged_protocol_mock=True,
        source_operation_id=original['operation_id'],expected_result_sha256=original['result_sha256'],request_key='explicit-retained-google-refresh-key')
    new=await service.refresh(project['id'],refresh,principal=principal);assert new['status']=='succeeded' and new['result']['grant_receipt']['reference']!=original['result']['grant_receipt']['reference'];refs.append(new['result']['grant_receipt'])
    assert await service.refresh(project['id'],refresh,principal=principal)==new
    mode[0]='timeout';pending,unknown=await start_and_exchange('explicit-retained-google-unknown-key','publishing');assert unknown['status']=='outcome_unknown';service.recover()
    mode[0]='success';denied,denial=await start_and_exchange('explicit-retained-google-denial-key','publishing',True);assert denial['status']=='failed' and denial['cost_operation_id'] is None
    assert len(calls)==3 and len(refs)==7 and all(acl(p) for p in private.glob('*.dpapi')) and store.get(project['id'])==project
    assert all(file_sha(vault.path(r['reference']))==r['cipher_sha256'] for r in refs)
    histories={kind:service.page(project['id'],kind=kind)['items'] for kind in ('authorization','operation')};assert len(histories['authorization'])==3 and len(histories['operation'])==4
    costs=service.costs.summary(project['id']);assert costs['attempted_operations']==3 and all(r['actual_cost'] is None and not r['paid'] and not r['external_call'] for r in costs['records'])
    for kind,values in histories.items():write(out/('expected-'+kind+'-history.json'),values)
    write(out/'expected-private-receipts.json',refs);write(out/'expected-project.json',project);write(out/'expected-journals.json',journals(store));write(out/'mock-wire-summary.json',calls);write(out/'cost.json',costs)
    backup=create_backup(settings(state),out/'public-oauth-operations.zip');write(out/'backup.json',backup)
    with zipfile.ZipFile(out/'public-oauth-operations.zip') as archive:
        assert not any(n.endswith(('.dpapi','.part')) for n in archive.namelist())
        assert all(secret.encode() not in archive.read(n) for n in archive.namelist() for secret in PRIVATE)
    write(out/'recovery-restore.json',restore_backup(out/'public-oauth-operations.zip',restored,expected_sha256=backup['sha256']));reopen(args)
    sources=('services/windows_native/google_oauth_operations.py','services/windows_native/tests/test_google_oauth_operations.py','services/windows_native/google_oauth_vault.py','apps/api/app/google_oauth_protocol.py','services/windows_native/backup.py','scripts/north_star_google_oauth_operations.py')
    write(out/'evidence.json',{'schema_version':'native-google-oauth-operations-rehearsal-v1','mock_token_requests':3,'authorization_histories':3,'operation_histories':4,'grant_generations':2,'private_synthetic_cipher_files':7,
        'private_acl_verified':True,'one_use_code_and_explicit_refresh_generation_no_automatic_retries':True,'current_owner_consent_and_separate_cost_audit':True,'original_generation_bytes_and_unknown_expiry_null':True,
        'known_denial_no_provider_or_cost':True,'timeout_unknown_no_retry':True,'journal_count':len(journals(store)),'public_only_backup_and_fresh_recovery_exact':True,
        'signed_routes_studio_account_confirmation_or_credential_resolver_integrated':False,'real_secret_reads':0,'external_provider_calls':0,'paid_operations':0,'real_publications':0,'real_audience_observations':0,'new_media_operations':0,
        'browser_owner_provider_production_acceptance':False,'source_sha256':{name:file_sha(ROOT/name) for name in sources},'exports':{p.name:{'sha256':file_sha(p),'bytes':p.stat().st_size} for p in out.iterdir() if p.is_file()}})
    print(json.dumps({'status':'PASS','mock_token_requests':3,'private_synthetic_files':7,'histories':[3,4],'fresh_restore_exact':True,'external_calls':0}))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--state-root',type=Path);p.add_argument('--private-root',type=Path,required=True);p.add_argument('--restore-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--reopen',action='store_true');p.add_argument('--new-process',action='store_true');args=p.parse_args();reopen(args) if args.reopen else asyncio.run(run(args))
