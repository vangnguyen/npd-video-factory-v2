"""Retain explicit TikTok mocks, actual DPAPI/SQLite and keyless public recovery."""
import argparse,asyncio,json,re,sys,zipfile
from datetime import datetime,timedelta,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import httpx
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
from app.publishing_models import PublishingTargetBinding
from app.tiktok_credentials import SCOPES
from services.windows_native import tiktok_connection as connection
from services.windows_native.store import Store
from services.windows_native.publications import NativePublications
from services.windows_native.official_accounts import NativeOfficialAccounts
from services.windows_native.official_publications import NativeOfficialPublications
from services.windows_native.tiktok_creators import NativeTikTokCreators,Check,Draft,Action,TABLE
from services.windows_native.contracts import digest,file_sha
from services.windows_native.backup import create_backup,restore_backup,database_status
from services.windows_native.tests.test_publications import render_fixture,CAPABILITIES
from services.windows_native.tests.test_human_identity import fixture as human_fixture
from scripts.north_star_native_official_analytics import settings
from scripts.north_star_google_oauth_operations import journals

WORKSPACE='wsp_tiktok_creator_retained_fixture';TOKEN='EXPLICIT_RETAINED_TIKTOK_TOKEN_0123456789';PRIVATE=[TOKEN]
KIND='explicit_protocol_mock_not_owner_or_real_provider_acceptance'
def write(path,value):
    raw=json.dumps(value,ensure_ascii=False,indent=2)+'\n';assert all(secret not in raw for secret in PRIVATE)
    with path.open('x',encoding='utf-8',newline='\n') as h:h.write(raw)
def owned(path,kind,*,fresh=False):
    path=path.resolve()
    if path.parent!=Path('C:/') or not re.fullmatch('vf-native-fixture-tiktok-creator-'+kind+r'-[0-9]{2}',path.name) or fresh and path.exists():raise ValueError('Exact fresh owned TikTok fixture root required')
    return path
def services(root,*,verifier=None,clock=None,factories=None,enabled=False):
    store=Store(root);clock=clock or (lambda:datetime.now(timezone.utc));pub=NativePublications(store,CAPABILITIES,workspace_id=WORKSPACE,clock=clock)
    accounts=NativeOfficialAccounts(store,workspace_id=WORKSPACE,clock=clock);official=NativeOfficialPublications(store,pub,accounts,identity_provider=verifier,clock=clock)
    return store,NativeTikTokCreators(official,factories=factories,enabled=enabled)
def replay(args):
    out=args.output.resolve();root=owned(args.restore_root,'restore');store,service=services(root)
    expected=json.loads((out/'expected-journals.json').read_bytes());assert journals(store)==expected
    project=json.loads((out/'expected-project.json').read_bytes());assert store.get(project['id'])==project
    for value in json.loads((out/'expected-checks.json').read_bytes()):assert service.get(project['id'],value['check_id'])==value
    for value in json.loads((out/'expected-drafts.json').read_bytes()):assert service.get_draft(project['id'],value['draft_id'])==value
    assert service.states()['factories']==[] and service.states()['enabled'] is False and service.recover()==0 and journals(store)==expected
    source=json.loads((out/'source-integrity.json').read_bytes());assert file_sha(root/'jobs'/source['final_job_id']/'final.mp4')==source['final_sha256']
    write(out/('new-process-replay.json' if args.new_process else 'in-process-replay.json'),{'status':'PASS','fixture_kind':KIND,'keyless_history_exact':True,'all_journals_exact':True,
        'journal_tables':len(expected),'source_final_exact':True,'provider_calls':0,'private_decryption':0,'automatic_replay':0,'publishing_enabled':False})
    print(json.dumps({'status':'PASS','journal_tables':len(expected),'new_process':args.new_process}))
def finish_restore(args):
    out=args.output.resolve();root=owned(args.state_root,'state');restored=owned(args.restore_root,'restore',fresh=True)
    expected=json.loads((out/'expected-journals.json').read_bytes());store,service=services(root)
    assert journals(store)==expected and database_status(store.db)['active_operations']==0
    backup=json.loads((out/'backup.json').read_bytes());archive=out/'public-tiktok-creator-history.zip'
    assert file_sha(archive)==backup['sha256'] and archive.stat().st_size==backup['bytes']
    write(out/'restore.json',restore_backup(archive,restored,expected_sha256=backup['sha256']));replay(args)
async def run(args):
    root=owned(args.state_root,'state',fresh=True);private=owned(args.private_root,'secrets',fresh=True);restored=owned(args.restore_root,'restore',fresh=True);out=args.output.resolve()
    if out==ROOT or ROOT in out.parents or out.exists():raise ValueError('Fresh external evidence required')
    root.mkdir();private.mkdir();out.mkdir(parents=True);(root/'.vf-auth-workspace.json').write_text(json.dumps({'schema':'vf-native-workspace-binding-v1','workspace_id':WORKSPACE}),encoding='utf-8')
    stamp=datetime.now(timezone.utc);raw,data=human_fixture('owner',workspace=WORKSPACE);PRIVATE.append(raw);verifier=HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400);principal=verifier.verify('Bearer '+raw)
    store,base=services(root,verifier=lambda:verifier,clock=lambda:stamp);project,job=render_fixture(store);project=store.get(project['id']);before=store.get(project['id'])
    target=PublishingTargetBinding(workspace_id=WORKSPACE,profile_id='ppf_retained_tiktok_creator',profile_version=1,platform='tiktok',provider_key='tiktok-content-posting-api',target_account_id='EXPLICIT_RETAINED_OPEN_ID',credential_binding_sha256='a'*64)
    token_path=private/'tiktok-publisher.dpapi';token=connection.AccessToken(target=target,credential_alias='retained-tiktok-publisher',expires_at=stamp+timedelta(hours=1),scopes=sorted(SCOPES),token=TOKEN)
    receipt=connection.save_token(token_path,root,token);write(out/'private-cipher-receipt.json',receipt)
    binding=connection.Binding(profile=connection.Profile(target=target),credential_alias=token.credential_alias,token_file=str(token_path),creator_reads_enabled=True);calls=[]
    def response(request):
        assert request.headers['authorization']=='Bearer '+TOKEN
        calls.append({'method':request.method,'host':request.url.host,'path':request.url.path,'mock':True})
        if request.url.path=='/v2/user/info/':return httpx.Response(200,json={'error':{'code':'ok'},'data':{'user':{'open_id':target.target_account_id}}})
        assert request.url.path=='/v2/post/publish/creator_info/query/' and request.content==b'{}'
        return httpx.Response(200,json={'error':{'code':'ok'},'data':{'creator_username':'retained_fixture_creator','creator_nickname':'Creator mô phỏng được giữ làm bằng chứng',
            'privacy_level_options':['SELF_ONLY','PUBLIC_TO_EVERYONE'],'comment_disabled':False,'duet_disabled':True,'stitch_disabled':False,'max_video_post_duration_sec':180}})
    factory=connection.NativeTikTokFactory(binding,root,WORKSPACE,owner_read_enabled=True,transport=httpx.MockTransport(response));service=NativeTikTokCreators(base.publications,factories={target.profile_id:factory},enabled=True)
    check=Check(revision=project['revision'],profile_id=target.profile_id,expected_configuration_sha256=factory.sha256,acknowledged_creator_read=True,acknowledged_protocol_mock=True,request_key='retained-tiktok-creator-check-key')
    pending=service.create(project['id'],check,principal=principal)[0];assert calls==[]
    result=await service.fetch(project['id'],pending['check_id'],principal=principal,expected_snapshot_sha256=pending['snapshot_sha256']);assert result['status']=='succeeded' and len(calls)==2
    draft_request=Draft(revision=project['revision'],creator_check_id=result['check_id'],expected_creator_result_sha256=result['result_sha256'],final_job_id=job['id'],expected_final_sha256=job['result']['qc']['final_sha256'],
        metadata={'title':'Bản nháp TikTok mô phỏng','privacy':'private','hashtags':['tiktok','fixture']},choices={'privacy_level':'SELF_ONLY','disable_comment':True,'disable_duet':True,'disable_stitch':True,'brand_content_toggle':False,'brand_organic_toggle':False,'is_aigc':True,'music_usage_confirmed':True},
        acknowledged_video_selection=True,acknowledged_ai_disclosure=True,request_key='retained-tiktok-post-draft-key')
    draft=service.draft(project['id'],draft_request,principal=principal)[0];assert service.draft(project['id'],draft_request,principal=principal)==(draft,True)
    write(out/'studio-fixture.json',{'fixture_kind':KIND,'runtime':service.states(),'project':project,'job':job,'pending':pending,'succeeded':result,'draft':draft})
    cancelled=service.cancel(project['id'],pending['check_id'],Action(expected_snapshot_sha256=pending['snapshot_sha256']),principal=principal);assert cancelled['status']=='cancelled'
    assert service.get_draft(project['id'],draft['draft_id'])==draft and len(calls)==2 and store.get(project['id'])==before
    interrupted=service.create(project['id'],check.model_copy(update={'request_key':'retained-interrupted-tiktok-key'}),principal=principal)[0]
    cost=service.costs.begin(project_id=project['id'],provider='official-tiktok',model=None,operation='tiktok_creator.account.'+interrupted['check_id'],request_sha256=digest({'check_id':interrupted['check_id'],'snapshot_sha256':interrupted['snapshot_sha256'],'operation':'account'}),estimated_cost=None,paid=False,external_call=False)
    with store.transaction() as con:con.execute('UPDATE '+TABLE+" SET status='claimed' WHERE check_id=?",(interrupted['check_id'],))
    assert database_status(store.db)['active_operations']==1 and service.recover()==1 and not service.costs.pending(cost);unknown=service.get(project['id'],interrupted['check_id']);assert unknown['status']=='outcome_unknown' and len(calls)==2
    write(out/'expected-checks.json',[cancelled,unknown]);write(out/'expected-drafts.json',[draft]);write(out/'expected-project.json',store.get(project['id']));write(out/'costs.json',service.costs.summary(project['id']));write(out/'mock-wires.json',calls)
    source={'final_job_id':job['id'],'final_sha256':file_sha(root/'jobs'/job['id']/'final.mp4'),'canonical_project_unchanged':True,'final_media_kind':'explicit_render_fixture_not_real_video_acceptance'};write(out/'source-integrity.json',source)
    write(out/'expected-journals.json',journals(store));backup=create_backup(settings(root),out/'public-tiktok-creator-history.zip');write(out/'backup.json',backup)
    with zipfile.ZipFile(out/'public-tiktok-creator-history.zip') as archive:
        assert not any('.dpapi' in n.lower() or 'tiktok-publisher' in n.lower() for n in archive.namelist())
        assert all(TOKEN.encode() not in archive.read(n) and raw.encode() not in archive.read(n) for n in archive.namelist())
    finish_restore(args);print(json.dumps({'status':'PASS','mock_wires':2,'real_provider_calls':0,'paid_operations':0,'publishing_enabled':False}))
def main():
    p=argparse.ArgumentParser();p.add_argument('--state-root',type=Path);p.add_argument('--private-root',type=Path);p.add_argument('--restore-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--new-process',action='store_true');p.add_argument('--resume-restore',action='store_true');args=p.parse_args()
    if args.new_process and args.resume_restore:raise ValueError('Choose one recovery operation')
    if args.new_process:replay(args)
    elif args.resume_restore:finish_restore(args)
    else:asyncio.run(run(args))
if __name__=='__main__':main()
