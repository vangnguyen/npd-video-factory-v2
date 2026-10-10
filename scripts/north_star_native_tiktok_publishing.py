"""Retain explicit protocol mocks with local DPAPI, SQLite and public recovery.

Nonplayable media and Owner/platform fixtures do not certify actual publishing,
playable media, legal eligibility, genuine credentials or either full mode.
"""
import argparse,hashlib,json,re,sys,tempfile
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from services.windows_native import tiktok_connection as connection
from services.windows_native.backup import create_backup,restore_backup,database_status
from services.windows_native.contracts import digest,file_sha
from services.windows_native.official_accounts import NativeOfficialAccounts
from services.windows_native.official_publications import NativeOfficialPublications
from services.windows_native.official_publication_queue import NativeOfficialPublicationQueue
from services.windows_native.official_publication_sessions import SessionVault
from services.windows_native.official_publication_worker import NativeOfficialPublicationWorker
from services.windows_native.publications import NativePublications
from services.windows_native.store import Store
from services.windows_native.tests.test_publications import CAPABILITIES
from services.windows_native.tests.test_tiktok_creators import TOKEN
from services.windows_native.tests.test_tiktok_publish_worker import TikTokPublishWorkerTests,UPLOAD_TOKEN,URI
from scripts.north_star_native_official_analytics import settings
from scripts.north_star_google_oauth_operations import journals
KIND='explicit_tiktok_protocol_mock_local_dpapi_sqlite_not_provider_media_owner_acceptance'

def write(path,value):
    raw=json.dumps(value,ensure_ascii=False,indent=2)+'\n'
    assert all(secret not in raw for secret in (TOKEN,UPLOAD_TOKEN,URI))
    with path.open('x',encoding='utf-8',newline='\n') as out:out.write(raw)

def owned(path,kind,*,fresh=False):
    path=path.resolve()
    if path.parent!=Path('C:/') or not re.fullmatch('vf-native-fixture-tiktok-publishing-'+kind+r'-[0-9]{2}',path.name) or fresh and path.exists():raise ValueError('Exact fresh owned fixture path required')
    return path

def cold(root,expected):
    workspace=expected['publication']['workspace_id'];store=Store(root)
    parent=NativePublications(store,CAPABILITIES,workspace_id=workspace);accounts=NativeOfficialAccounts(store,workspace_id=workspace)
    official=NativeOfficialPublications(store,parent,accounts)
    worker=NativeOfficialPublicationWorker(official,SessionVault(official,directory=None));queue=NativeOfficialPublicationQueue(worker)
    assert store.get(expected['project']['id'])==expected['project']
    assert official.get(expected['project']['id'],expected['publication']['publication_id'])==expected['publication']
    assert official.state(expected['project']['id'],expected['publication']['publication_id'])==expected['dispatch']
    assert queue.get(expected['project']['id'],expected['queue']['plan_id'])==expected['queue']
    assert journals(store)==expected['journals'] and official.states()['profiles']==[]
    recovery=official.recover();assert recovery['recovered_intents']==0 and recovery['recovered_thumbnail_intents']==0 and recovery['external_calls']==0
    assert queue.recover()=={'recovered_steps':0,'external_calls':0,'automatic_upload_retry':False} and queue.process() is None
    assert journals(store)==expected['journals'];assert file_sha(root/'jobs'/expected['publication']['snapshot']['final_job_id']/'final.mp4')==expected['publication']['snapshot']['final_sha256']
    return {'status':'PASS','fixture_kind':KIND,'journal_tables':len(expected['journals']),'original_receipt_job_cost_observations_queue_exact':True,
        'source_project_unchanged':True,'provider_calls':0,'private_decryption':0,'automatic_replay':False,'database':database_status(store.db)}

def replay(args):
    root=owned(args.restore_root,'restore');out=args.output.resolve();expected=json.loads((out/'expected.json').read_bytes())
    with patch.object(connection,'load_token',side_effect=AssertionError('Recovery must never decrypt')):result=cold(root,expected)
    write(out/'new-process-replay.json',result);print(json.dumps({'status':'PASS','journal_tables':result['journal_tables'],'provider_calls':0}))

def finish(args,store,project,publication,dispatch,queue,stages,*,wires=None,reads=None,resumed=False):
    out=args.output.resolve();restored=owned(args.restore_root,'restore',fresh=True);source=project['id']
    assert publication['status']=='completed' and publication['mock_publication_complete'] is True and publication['published'] is False
    assert publication['receipt']['public_post_ids']==[] and publication['receipt']['remote_post_id'] is None
    assert queue['status']=='completed' and queue['step_count']==4 and len(dispatch['processing_observations'])==2
    assert store.get(source)==project and project['revision']==publication['snapshot']['project_revision'] and digest(project['document'])==publication['snapshot']['document_sha256']
    expected={'fixture_kind':KIND,'project':project,'publication':publication,'dispatch':dispatch,'queue':queue,'journals':journals(store)}
    costs=expected['journals']['native_cost_operations'];assert not any(x['paid'] for x in costs)
    intents=expected['journals']['native_official_publish_intents'];assert sum(x['operation']=='init' for x in intents)==1 and sum(x['operation']=='chunk' for x in intents)==1
    write(out/'expected.json',expected);write(out/'stages.json',stages)
    write(out/'flow.json',{'status':'PASS','fixture_kind':KIND,'publication_id':publication['publication_id'],'provider_job_id':dispatch['provider_job']['provider_job_id'],'queue_steps':4,
        'mock_account_creator_reads':reads,'mock_init_chunk_status_wires':wires,'raw_wire_capture_retained':wires is not None,'cost_operations':len(costs),'paid_operations':0,'real_provider_calls':0,
        'source_project_unchanged':True,'source_final_sha256':publication['snapshot']['final_sha256'],'receipt':publication['receipt'],'media_playable':False,'owner_uat':False,
        'startup_cli_studio_publishing_wired':False,'production_deployed':False,'journals':len(expected['journals']),'resumed_evidence_only':resumed,'additional_provider_calls_in_resume':0})
    archive=out/'public-tiktok-publishing.zip';backup=create_backup(settings(store.root),archive);write(out/'backup.json',backup)
    write(out/'restore.json',restore_backup(archive,restored,expected_sha256=backup['sha256']))
    with patch.object(connection,'load_token',side_effect=AssertionError('Recovery must never decrypt')):
        write(out/'source-keyless-history.json',cold(store.root,expected));write(out/'restored-in-process.json',cold(restored,expected))
    write(out/'flow-result.json',{'status':'PASS','fixture_kind':KIND,'queue_steps':4,'initializations':1,'chunks':1,'processing_observations':2,'actual_public_post_ids':[],
        'public_backup_sha256':backup['sha256'],'journal_tables':len(expected['journals']),'source_project_unchanged':True,'real_provider_tested':False,'owner_uat':False,
        'private_decryption_in_recovery':0,'provider_calls_in_recovery':0,'paid_operations':0,'resumed_evidence_only':resumed,'additional_provider_calls_in_resume':0})
    print(json.dumps({'status':'PASS','journal_tables':len(expected['journals']),'queue_steps':4,'public_backup_sha256':backup['sha256']}))

def resume(args):
    folder=owned(args.fixture_root,'state');out=args.output.resolve()
    assert json.loads((folder/'.vf-fixture-owner.json').read_bytes())['fixture_kind']==KIND and (out/'initial-run-failure.json').is_file() and not (out/'expected.json').exists()
    with patch.object(connection,'load_token',side_effect=AssertionError('Evidence resume must not decrypt')):
        store=Store(folder/'state')
        with store.transaction() as con:
            rows=con.execute('SELECT publication_id,project_id,workspace_id FROM native_official_publications').fetchall();assert len(rows)==1;row=dict(rows[0])
        parents=NativePublications(store,CAPABILITIES,workspace_id=row['workspace_id']);accounts=NativeOfficialAccounts(store,workspace_id=row['workspace_id'])
        official=NativeOfficialPublications(store,parents,accounts);worker=NativeOfficialPublicationWorker(official,SessionVault(official,directory=None));service=NativeOfficialPublicationQueue(worker)
        with store.transaction() as con:
            plans=con.execute('SELECT plan_id FROM native_official_publish_queue_plans').fetchall();assert len(plans)==1
        queue=service.get(row['project_id'],plans[0]['plan_id']);assert service.process() is None
        finish(args,store,store.get(row['project_id']),official.get(row['project_id'],row['publication_id']),official.state(row['project_id'],row['publication_id']),queue,
            {'recovered_original_queue_steps':queue['steps'],'raw_in_memory_stage_capture_lost_after_runner_assertion':True},resumed=True)

def run(args):
    folder=owned(args.fixture_root,'state',fresh=True);restored=owned(args.restore_root,'restore',fresh=True);out=args.output.resolve()
    if out.parent!=Path(r'C:\Users\PC\Documents\ChatGPT\Video Factory\recovery\20261007') or not re.fullmatch('tiktok-publishing-flow-n[0-9]+',out.name) or out.exists():raise ValueError('Exact fresh evidence output required')
    folder.mkdir();out.mkdir();write(folder/'.vf-fixture-owner.json',{'fixture_kind':KIND,'purpose':'tiktok-durable-publication-mock'})
    case=TikTokPublishWorkerTests('test_actual_session_chunk_processing_private_receipt_and_no_fake_post_id')
    holder=SimpleNamespace(name=str(folder),cleanup=lambda:None)
    with patch.object(tempfile,'TemporaryDirectory',return_value=holder):case.setUp()
    c=case.c;project=c.store.get(c.project['id']);source=project['id'];publication=case.value['publication_id'];queue,plan=case.queue();stages=[]
    for ordinal in range(4):
        if ordinal==3:case.status='PUBLISH_COMPLETE'
        result=queue.process();stages.append({'queue':result,'publication':case.state()});c.clock[0]+=timedelta(seconds=30)
    final=c.official.get(source,publication);dispatch=case.state();final_queue=queue.get(source,plan['plan_id']);assert final_queue['status']=='completed' and final_queue['step_count']==4 and queue.process() is None
    assert final['status']=='completed' and final['mock_publication_complete'] is True and final['published'] is False and final['receipt']['public_post_ids']==[] and final['receipt']['remote_post_id'] is None
    assert c.store.get(source)==project and len(dispatch['processing_observations'])==2
    wires=[{'ordinal':i+1,'method':x['method'],'path':x['path'],'body_bytes':len(x['body']),'body_sha256':hashlib.sha256(x['body']).hexdigest(),
        'authorization_header_present':x['authorization'] is not None,'token_returned':False,'upload_url_returned':False} for i,x in enumerate(case.publish_wires)]
    assert sum(x['path'].endswith('/init/') for x in wires)==1 and sum(x['method']=='PUT' for x in wires)==1
    finish(args,c.store,project,final,dispatch,final_queue,stages,wires=wires,reads=c.wire)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--fixture-root',type=Path);parser.add_argument('--restore-root',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    choice=parser.add_mutually_exclusive_group();choice.add_argument('--replay',action='store_true');choice.add_argument('--resume-finish',action='store_true');args=parser.parse_args()
    replay(args) if args.replay else resume(args) if args.resume_finish else run(args)
if __name__=='__main__':main()
