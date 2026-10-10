"""Retained synthetic grant selection and keyless fresh-process recovery."""
import argparse,asyncio,json,re,sys,zipfile
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlencode,parse_qs
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.north_star_google_oauth_operations import services,journals,WORKSPACE
from scripts.north_star_native_official_learning import settings
from services.windows_native.contracts import file_sha
from services.windows_native.backup import create_backup,restore_backup
from services.windows_native.google_oauth_operations import NativeGoogleOAuthOperations,Slot,Start,Refresh
from services.windows_native.google_oauth_vault import PrivateClient
from services.windows_native.google_oauth_selections import NativeGoogleOAuthSelections,Select,Revoke
from services.windows_native.tests.test_google_oauth_protocol import client,TOKEN,REFRESH,SECRET,CODE
from services.windows_native.tests.test_human_identity import fixture as human_fixture
from app.google_oauth_protocol import GoogleOAuthTokenClient
from app.publishing_wire import OfficialHTTPClient
from app.analytics_official import AnalyticsHTTPClient
from app.human_identity import HumanAuthVerifier,HumanAuthRegistry
import httpx
PRIVATE=[TOKEN,REFRESH,SECRET,CODE]
def write(path,value):
    raw=json.dumps(value,ensure_ascii=False,indent=2)+'\n';assert all(s not in raw for s in PRIVATE)
    with path.open('x',encoding='utf-8',newline='\n') as f:f.write(raw)
def owned(path,kind,fresh=False,purpose='publishing'):
    path=path.resolve()
    if purpose not in ('publishing','analytics'):raise ValueError('Dedicated selection purpose required')
    stem='vf-native-fixture-google-oauth-selection-' if purpose=='publishing' else 'vf-native-fixture-google-analytics-selection-'
    if path.parent!=Path('C:/') or not re.fullmatch(stem+kind+r'-[0-9]{2}',path.name) or fresh and path.exists():raise ValueError('Exact fresh owned selection root required')
    return path
def replay(args):
    output=args.output.resolve();root=owned(args.restore_root,'restore',purpose=args.purpose);private=owned(args.private_root,'secrets',purpose=args.purpose)
    # History verification uses an absent private mount and no identity/provider.
    absent=private.with_name(private.name+'-absent');assert not absent.exists()
    store,vault,oauth=services(root,absent);selections=NativeGoogleOAuthSelections(oauth,purpose=args.purpose)
    expected=json.loads((output/'expected-journals.json').read_bytes());assert journals(store)==expected
    project=json.loads((output/'expected-project.json').read_bytes());assert store.get(project['id'])==project
    for value in json.loads((output/'expected-selection-history.json').read_bytes()):assert selections.get(project['id'],value['selection_id'])==value
    for value in json.loads((output/'expected-operation-history.json').read_bytes()):assert oauth.get(project['id'],value['operation_id'])==value
    assert not selections.states()['enabled'] and selections.states()['slots']==[] and selections.recover()==0
    assert journals(store)==expected
    result={'status':'PASS','keyless_history_exact':True,'all_journals_exact':True,'journal_tables':len(expected),'provider_calls':0,'private_decryption':0,'automatic_replay':0,
        'fixture_kind':'explicit_protocol_mock_not_owner_or_real_provider_acceptance'}
    name=args.replay_output or ('new-process-replay.json' if args.new_process else 'in-process-replay.json')
    if not re.fullmatch(r'[a-z][a-z0-9-]{1,79}\.json',name):raise ValueError('Bounded replay report filename required')
    write(output/name,result);print(json.dumps(result))
async def run(args):
    state=owned(args.state_root,'state',True,purpose=args.purpose);private=owned(args.private_root,'secrets',True,purpose=args.purpose);restored=owned(args.restore_root,'restore',True,purpose=args.purpose)
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False);state.mkdir()
    (state/'.vf-auth-workspace.json').write_text(json.dumps({'schema':'vf-native-workspace-binding-v1','workspace_id':WORKSPACE}),encoding='utf-8')
    raw,registry=human_fixture('owner',workspace=WORKSPACE);PRIVATE.append(raw);verifier=HumanAuthVerifier(HumanAuthRegistry.model_validate(registry),max_token_ttl_seconds=86400);principal=verifier.verify('Bearer '+raw)
    stamp=datetime.now(timezone.utc);store,vault,base=services(state,private,verifier=lambda:verifier,clock=lambda:stamp);project=store.create('Explicit retained credential selection fixture','','media')
    c=client(args.purpose);receipt=vault.save_client(PrivateClient(target=c.target,purpose=c.purpose,credential_alias='explicit-retained-selection-'+args.purpose,client_id=c.client_id,scopes=sorted(c.scopes),client_secret=c.client_secret))
    slot=Slot(slot_id='ngos_'+'b'*32,target=c.target,client=receipt,client_id=c.client_id,scopes=sorted(c.scopes));token_calls=[];channel_calls=[]
    def token_wire(request):
        token_calls.append({'method':request.method,'host':request.url.host,'path':request.url.path,'operation':parse_qs(request.content.decode())['grant_type'][0],'mock':True})
        return httpx.Response(200,json={'access_token':TOKEN+str(len(token_calls)),'refresh_token':REFRESH+str(len(token_calls)),'expires_in':3600,'token_type':'Bearer','scope':' '.join(sorted(c.scopes))})
    def channel_wire(request):
        assert request.method=='GET' and request.url.path=='/youtube/v3/channels' and request.url.params['mine']=='true'
        assert request.headers['authorization']=='Bearer '+TOKEN+str(len(token_calls))
        channel_calls.append({'method':request.method,'host':request.url.host,'path':request.url.path,'mock':True})
        return httpx.Response(200,json={'items':[{'id':c.target.target_account_id}]})
    oauth=NativeGoogleOAuthOperations(base.publications,vault,slots={slot.slot_id:slot},client=GoogleOAuthTokenClient(transport=httpx.MockTransport(token_wire)),enabled=True)
    selection_client=(OfficialHTTPClient if args.purpose=='publishing' else AnalyticsHTTPClient)('youtube',transport=httpx.MockTransport(channel_wire))
    selections=NativeGoogleOAuthSelections(oauth,enabled=True,client=selection_client,purpose=args.purpose)
    first,_=oauth.start(project['id'],Start(revision=1,slot_id=slot.slot_id,expected_configuration_sha256=slot.client.configuration_sha256,acknowledged_credential_operation=True,
        acknowledged_protocol_mock=True,redirect_uri='http://127.0.0.1:18047/oauth/google/callback',request_key='explicit-retained-selection-start'),principal=principal)
    flow=vault.authorization(first['snapshot']['authorization_receipt']);PRIVATE.extend([flow.state,flow.verifier])
    source=await oauth.exchange(project['id'],first['authorization_id'],urlencode({'state':flow.state,'code':CODE}),principal=principal,expected_snapshot_sha256=first['snapshot_sha256']);assert source['status']=='succeeded'
    def create(source,key):return selections.create(project['id'],Select(revision=1,source_operation_id=source['operation_id'],expected_result_sha256=source['result_sha256'],
        acknowledged_account_access=True,acknowledged_credential_selection=True,acknowledged_protocol_mock=True,request_key=key),principal=principal)[0]
    pending=create(source,'explicit-retained-selection-first');active=await selections.verify(project['id'],pending['selection_id'],principal=principal,expected_snapshot_sha256=pending['snapshot_sha256'])
    assert active['status']=='active' and selections.credential(slot.slot_id,c.target).token==TOKEN+'1'
    fixture={'fixture_kind':'explicit_protocol_mock_not_owner_or_real_provider_acceptance','runtime':selections.states(),'source':source,'pending':pending,'active':active}
    new=await oauth.refresh(project['id'],Refresh(revision=1,slot_id=slot.slot_id,expected_configuration_sha256=slot.client.configuration_sha256,acknowledged_credential_operation=True,
        acknowledged_protocol_mock=True,source_operation_id=source['operation_id'],expected_result_sha256=source['result_sha256'],request_key='explicit-retained-selection-refresh'),principal=principal)
    assert new['status']=='succeeded'
    from services.windows_native.contracts import WorkflowError
    try:selections.credential(slot.slot_id,c.target);raise AssertionError('Old grant must not remain usable')
    except WorkflowError as error:assert error.code=='NATIVE_GOOGLE_SELECTION_GRANT_SUPERSEDED'
    next_pending=create(new,'explicit-retained-selection-refreshed');next_active=await selections.verify(project['id'],next_pending['selection_id'],principal=principal,expected_snapshot_sha256=next_pending['snapshot_sha256'])
    assert next_active['status']=='active' and selections.credential(slot.slot_id,c.target).token==TOKEN+'2'
    revoked=selections.revoke(project['id'],next_active['selection_id'],Revoke(expected_snapshot_sha256=next_active['snapshot_sha256']),principal=principal)
    assert revoked['status']=='revoked' and store.get(project['id'])==project and len(token_calls)==len(channel_calls)==2
    fixture['revoked']=selections.get(project['id'],active['selection_id'])
    history=selections.page(project['id'])['items'];write(out/'expected-selection-history.json',history);write(out/'expected-operation-history.json',oauth.page(project['id'])['items'])
    write(out/'expected-project.json',project);write(out/'expected-journals.json',journals(store));write(out/'mock-wire-summary.json',{'token':token_calls,'account':channel_calls})
    costs=selections.costs.summary(project['id']);assert costs['attempted_operations']==4 and all(not r['external_call'] and not r['paid'] and r['actual_cost'] is None for r in costs['records']);write(out/'cost.json',costs)
    write(out/'studio-fixture.json',fixture)
    if args.studio_fixture:write(args.studio_fixture.resolve(),fixture)
    backup=create_backup(settings(state),out/'public-selection-history.zip');write(out/'backup.json',backup)
    with zipfile.ZipFile(out/'public-selection-history.zip') as z:
        assert not any(n.endswith('.dpapi') for n in z.namelist())
        for name in z.namelist():
            if not name.endswith('/'):assert all(s.encode() not in z.read(name) for s in PRIVATE)
    write(out/'restore.json',restore_backup(out/'public-selection-history.zip',restored,expected_sha256=backup['sha256']));replay(args)
    evidence={'status':'PASS','fixture_kind':fixture['fixture_kind'],'token_exchange_requests':2,'same_grant_readonly_account_requests':2,'selected_histories':2,
        'refresh_did_not_auto_select':True,'local_revoke_no_provider':True,'backup':{'sha256':backup['sha256'],'bytes':(out/'public-selection-history.zip').stat().st_size},
        'private_credentials_excluded':True,'project_unchanged':True,'external_calls':0,'paid_operations':0,'publishing_enabled':False,'real_provider_tested':False,'owner_uat':False,'production_deployed':False}
    write(out/'evidence.json',evidence);print(json.dumps(evidence))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--state-root',type=Path);p.add_argument('--private-root',type=Path,required=True);p.add_argument('--restore-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--studio-fixture',type=Path);p.add_argument('--purpose',choices=['publishing','analytics'],default='publishing');p.add_argument('--replay',action='store_true');p.add_argument('--new-process',action='store_true');p.add_argument('--replay-output');args=p.parse_args();replay(args) if args.replay else asyncio.run(run(args))
