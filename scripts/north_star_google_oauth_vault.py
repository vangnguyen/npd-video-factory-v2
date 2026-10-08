"""Synthetic DPAPI custody, public metadata backup and explicit fresh recovery."""
import argparse,asyncio,hashlib,json,os,re,subprocess,sys,zipfile
from pathlib import Path
from datetime import timedelta
from urllib.parse import urlencode,parse_qs
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from services.windows_native.google_oauth_vault import NativeGoogleOAuthVault,PrivateClient
from services.windows_native.tests.test_google_oauth_protocol import client,NOW,TOKEN,REFRESH,SECRET,CODE
from app.google_oauth_protocol import authorization,exchange_request,refresh_request,parse_tokens,GoogleOAuthTokenClient,TOKEN_URL
from services.windows_native.store import Store
from services.windows_native.backup import create_backup,restore_backup
from scripts.north_star_native_official_learning import settings
from services.windows_native.contracts import digest,file_sha
import httpx

def write(path,value):
    raw=json.dumps(value,ensure_ascii=False,indent=2)+'\n'
    for private in (TOKEN,REFRESH,SECRET,CODE):assert private not in raw
    with path.open('x',encoding='utf-8',newline='\n') as h:h.write(raw)
def owned(path,kind,fresh=False):
    path=path.resolve()
    if path.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-google-oauth-vault-'+kind+r'-[0-9]{2}',path.name) or fresh and path.exists():raise ValueError('Owned fresh OAuth vault fixture root required')
    return path
def acl(path):
    # The path is generated under an owned root, never supplied by a callback.
    command="$taskAcl=Get-Acl -LiteralPath '"+str(path).replace("'","''")+"'; $taskSid=[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value; $taskRules=@($taskAcl.Access); if(-not $taskAcl.AreAccessRulesProtected -or $taskRules.Count -ne 2){throw 'Private DACL required'}; foreach($taskRule in $taskRules){$taskRuleSid=$taskRule.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value; if($taskRuleSid -notin @($taskSid,'S-1-5-18') -or $taskRule.AccessControlType -ne 'Allow'){throw 'Private DACL mismatch'}}; Write-Output 'PRIVATE_DACL_VERIFIED'"
    # A PowerShell 7 parent can export incompatible module paths to Windows PowerShell.
    environment={k:v for k,v in os.environ.items() if k.upper()!='PSMODULEPATH'}
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],capture_output=True,text=True,
        env=environment,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    assert result.returncode==0 and result.stdout.strip()=='PRIVATE_DACL_VERIFIED'
    return True
def reopen(args):
    out=args.output.resolve();restored=owned(args.restore_root,'restore');private=owned(args.private_root,'secrets');refs=json.loads((restored/'configuration/google-oauth-references.json').read_bytes())
    assert refs==json.loads((out/'expected-references.json').read_bytes());vault=NativeGoogleOAuthVault(private,restored,'wsp_google_oauth_fixture')
    proofs=[]
    for group in refs:
        c=vault.client(group['client']);flow=vault.authorization(group['authorization'])
        assert hashlib.sha256(flow.state.encode()).hexdigest()==group['state_sha256'] and hashlib.sha256(flow.verifier.encode()).hexdigest()==group['verifier_sha256']
        for name in ('original','refreshed'):proofs.append(vault.grant(group[name]).public(c))
    assert proofs==json.loads((out/'expected-grant-proofs.json').read_bytes())
    for ref in [item[k] for item in refs for k in ('client','authorization','original','refreshed')]:assert file_sha(vault.path(ref['reference']))==ref['cipher_sha256']
    state=vault.states();assert not state['startup_decryption'] and not state['automatic_refresh'] and not state['publishing_enabled']
    store=Store(restored);expected=json.loads((out/'expected-project.json').read_bytes());assert store.get(expected['id'])==expected
    absent=NativeGoogleOAuthVault(private.with_name(private.name+'-absent'),restored,vault.workspace);assert not absent.states()['mounted']
    try:absent.grant(refs[0]['original'])
    except Exception:pass
    else:raise AssertionError('Unmounted private custody cannot resolve restored metadata')
    write(out/('new-process-replay.json' if args.new_process else 'restored-in-process.json'),{'public_metadata_original_project_eight_private_cipher_refs_four_grant_proofs_pending_pkce_exact':True,
        'unmounted_private_directory_does_not_resolve_restored_metadata':True,'startup_decryption_or_automatic_refresh_or_publishing':False,'external_calls':0,'real_secret_reads':0,'explicit_synthetic_secrets':True})
async def run(args):
    out=args.output.resolve();state=owned(args.state_root,'state',True);private=owned(args.private_root,'secrets',True);restored=owned(args.restore_root,'restore',True)
    if out.exists() or out==ROOT or ROOT in out.parents:raise ValueError('Fresh external OAuth vault evidence required')
    out.mkdir(parents=True);store=Store(state);project=store.create('Explicit synthetic OAuth metadata recovery','Protocol custody fixture; no provider media','prompt');vault=NativeGoogleOAuthVault(private,state,'wsp_google_oauth_fixture')
    refs=[];proofs=[];calls=[]
    for purpose in ('analytics','publishing'):
        c=client(purpose);value=PrivateClient(target=c.target,purpose=purpose,credential_alias='explicit-google-'+purpose,client_id=c.client_id,scopes=sorted(c.scopes),client_secret=c.client_secret)
        client_ref=vault.save_client(value);c=vault.client(client_ref);flow=authorization(c,'http://127.0.0.1:18047/oauth/google/callback',now=NOW);flow_ref=vault.save_authorization(flow,client_ref)
        def wire(r):
            assert r.method=='POST' and str(r.url)==TOKEN_URL and 'authorization' not in r.headers
            body=dict(parse_qs(r.content.decode()));result={'access_token':TOKEN,'expires_in':3600,'token_type':'Bearer','scope':' '.join(sorted(c.scopes))}
            if body['grant_type']==['authorization_code']:result['refresh_token']=REFRESH
            else:assert body['refresh_token']==[REFRESH]
            calls.append({'purpose':purpose,'operation':body['grant_type'][0],'request_sha256':hashlib.sha256(r.content).hexdigest(),'mock':True})
            return httpx.Response(200,json=result)
        http=GoogleOAuthTokenClient(transport=httpx.MockTransport(wire));request=exchange_request(flow,urlencode({'state':flow.state,'code':CODE}),now=NOW)
        original=parse_tokens(c,request,await http.send(c,request,now=NOW),now=NOW);old=vault.save_grant(original,client_ref);old_sha=file_sha(vault.path(old['reference']))
        stamp=NOW+timedelta(hours=2);request=refresh_request(c,original,now=stamp);refreshed=parse_tokens(c,request,await http.send(c,request,now=stamp),now=stamp,previous=original);new=vault.save_grant(refreshed,client_ref,previous=old)
        assert file_sha(vault.path(old['reference']))==old_sha and old['reference']!=new['reference']
        refs.append({'purpose':purpose,'client':client_ref,'authorization':flow_ref,'original':old,'refreshed':new,'state_sha256':hashlib.sha256(flow.state.encode()).hexdigest(),'verifier_sha256':hashlib.sha256(flow.verifier.encode()).hexdigest()})
        proofs.extend([original.public(c),refreshed.public(c)])
    assert len(calls)==4 and len(list(private.glob('*.dpapi')))==8 and store.get(project['id'])==project
    assert all(acl(p) for p in private.glob('*.dpapi'));assert all(s not in p.read_bytes() for p in private.glob('*.dpapi') for s in (TOKEN.encode(),REFRESH.encode(),SECRET.encode(),CODE.encode()))
    metadata=state/'configuration/google-oauth-references.json';metadata.parent.mkdir();write(metadata,refs);write(out/'expected-references.json',refs);write(out/'expected-grant-proofs.json',proofs);write(out/'expected-project.json',project);write(out/'mock-wire-summary.json',calls)
    backup=create_backup(settings(state),out/'public-oauth-metadata.zip');write(out/'backup.json',backup)
    with zipfile.ZipFile(out/'public-oauth-metadata.zip') as archive:
        assert not any(n.endswith(('.dpapi','.part')) for n in archive.namelist())
        assert all(s not in archive.read(n) for n in archive.namelist() for s in (TOKEN.encode(),REFRESH.encode(),SECRET.encode(),CODE.encode()))
    write(out/'recovery-restore.json',restore_backup(out/'public-oauth-metadata.zip',restored,expected_sha256=backup['sha256']));reopen(args)
    sources=('services/windows_native/google_oauth_vault.py','services/windows_native/tests/test_google_oauth_vault.py','apps/api/app/google_oauth_protocol.py','scripts/north_star_google_oauth_vault.py')
    write(out/'evidence.json',{'schema_version':'native-google-oauth-vault-rehearsal-v1','private_cipher_files':8,'private_dacl_only_current_user_and_local_system_verified':True,'mock_token_requests':4,'grant_proofs':4,
        'old_private_generation_unchanged':True,'public_metadata_backup_excludes_private_tokens_codes_pkce_client_secrets_and_cipher_files':True,'restored_original_project_refs_pkce_and_grant_proofs_exact':True,
        'current_human_claims_cost_audit_signed_routes_studio_and_resolver_integrated':False,'automatic_refresh_or_publishing_or_consent_renewal':False,'external_provider_calls':0,'real_secret_reads':0,'paid_operations':0,'real_publications':0,'real_audience_observations':0,'new_media_operations':0,
        'browser_owner_provider_production_acceptance':False,'explicit_synthetic_credentials':True,'source_sha256':{name:file_sha(ROOT/name) for name in sources},'exports':{p.name:{'sha256':file_sha(p),'bytes':p.stat().st_size} for p in out.iterdir() if p.is_file()}})
    print(json.dumps({'status':'PASS','private_synthetic_cipher_files':8,'mock_token_requests':4,'public_metadata_backup':True,'fresh_restore_exact':True,'external_calls':0,'real_secret_reads':0}))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--state-root',type=Path);p.add_argument('--private-root',type=Path,required=True);p.add_argument('--restore-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--reopen',action='store_true');p.add_argument('--new-process',action='store_true');args=p.parse_args();reopen(args) if args.reopen else asyncio.run(run(args))
