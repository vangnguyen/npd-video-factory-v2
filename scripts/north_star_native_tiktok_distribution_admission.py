"""Retain admission-only protocol fixtures and exact keyless public recovery."""
import argparse,json,re,sys,tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from services.windows_native import tiktok_connection as connection
from services.windows_native.contracts import WorkflowError,file_sha
from services.windows_native.store import Store
from services.windows_native.publications import NativePublications
from services.windows_native.official_accounts import NativeOfficialAccounts
from services.windows_native.official_publications import NativeOfficialPublications
from services.windows_native.official_publication_models import Action
from services.windows_native.official_publication_sessions import SessionVault
from services.windows_native.official_publication_worker import NativeOfficialPublicationWorker
from services.windows_native.backup import create_backup,restore_backup
from services.windows_native.tests.test_tiktok_distribution import TikTokDistributionAdmissionTests
from services.windows_native.tests.test_tiktok_creators import TOKEN
from services.windows_native.tests.test_publications import CAPABILITIES
from scripts.north_star_native_official_analytics import settings
from scripts.north_star_google_oauth_operations import journals
KIND='explicit_admission_mock_not_media_provider_or_owner_acceptance'
def write(path,value):
    raw=json.dumps(value,ensure_ascii=False,indent=2)+'\n';assert TOKEN not in raw
    with path.open('x',encoding='utf-8',newline='\n') as out:out.write(raw)
def owned(path,kind,*,fresh=False):
    path=path.resolve()
    if path.parent!=Path('C:/') or not re.fullmatch('vf-native-fixture-tiktok-distribution-'+kind+r'-[0-9]{2}',path.name) or fresh and path.exists():raise ValueError('Fresh exact owned fixture directory required')
    return path
def replay(args):
    root=owned(args.restore_root,'restore');out=args.output.resolve();expected=json.loads((out/'expected.json').read_bytes());workspace=expected['publication']['workspace_id']
    with patch.object(connection,'load_token',side_effect=AssertionError('Recovery must not decrypt')):
        store=Store(root);pub=NativePublications(store,CAPABILITIES,workspace_id=workspace);accounts=NativeOfficialAccounts(store,workspace_id=workspace);official=NativeOfficialPublications(store,pub,accounts)
        assert official.get(expected['project']['id'],expected['publication']['publication_id'])==expected['publication']
        assert store.get(expected['project']['id'])==expected['project'] and journals(store)==expected['journals']
        recovery=official.recover();assert official.states()['profiles']==[] and recovery['recovered_intents']==0 and recovery['recovered_thumbnail_intents']==0 and recovery['external_calls']==0 and journals(store)==expected['journals']
        flow=json.loads((out/'flow.json').read_bytes());assert file_sha(root/'jobs'/expected['publication']['snapshot']['final_job_id']/'final.mp4')==flow['source_final_sha256']
    write(out/('new-process-replay.json' if args.replay else 'restored-in-process.json'),{'status':'PASS','fixture_kind':KIND,'keyless_original_history_exact':True,'journal_tables':len(expected['journals']),
        'provider_calls':0,'private_decryption':0,'upload_or_status_execution':False,'automatic_replay':False})
    print(json.dumps({'status':'PASS','journal_tables':len(expected['journals']),'new_process':args.replay}))
def finish(args):
    root=owned(args.fixture_root,'state');out=args.output.resolve();backup=json.loads((out/'backup.json').read_bytes());archive=out/'public-tiktok-distribution-admission.zip'
    assert file_sha(archive)==backup['sha256'] and archive.stat().st_size==backup['bytes'];replay(args)
    expected=json.loads((out/'expected.json').read_bytes());flow=json.loads((out/'flow.json').read_bytes());assert journals(Store(root/'state'))==expected['journals']
    assert len(flow['original_mock_creator_wires'])==2 and flow['revoked']==expected['publication'] and flow['revoked']['receipt'] is None
    write(out/'flow-result.json',{'status':'PASS','fixture_kind':KIND,'original_mock_creator_wires':2,'publishing_wires':0,'paid_operations':0,'owner_uat':False,'real_provider_tested':False,
        'source_project_unchanged':True,'review_snapshot_preserved':True,'public_backup_sha256':backup['sha256'],'journal_tables':len(expected['journals'])})
def run(args):
    folder=owned(args.fixture_root,'state',fresh=True);restored=owned(args.restore_root,'restore',fresh=True);out=args.output.resolve()
    if out.parent!=Path(r'C:\Users\PC\Documents\ChatGPT\Video Factory\recovery\20261007') or not re.fullmatch('tiktok-distribution-admission-flow-n[0-9]+',out.name) or out.exists():raise ValueError('Fresh exact evidence output required')
    folder.mkdir();out.mkdir();write(folder/'.vf-fixture-owner.json',{'fixture_kind':KIND,'purpose':'tiktok-publication-admission-only'})
    case=TikTokDistributionAdmissionTests('test_draft_and_dry_run_require_separate_owner_publication_approval')
    holder=SimpleNamespace(name=str(folder),cleanup=lambda:None)
    with patch.object(tempfile,'TemporaryDirectory',return_value=holder):case.setUp()
    original=case.store.get(case.project['id']);value=case.publication();assert value['status']=='awaiting_publish_approval'
    approved=case.approve_publication(value);assert approved['status']=='queued' and case.official.admission(original['id'],value['publication_id'])[3]['phase']=='prepared'
    vault=SessionVault(case.official,directory=folder/'private'/'sessions');worker=NativeOfficialPublicationWorker(case.official,vault)
    with patch.object(connection,'load_token',side_effect=AssertionError('Worker must not decrypt')):
        worker.context(original['id'],value['publication_id'],1)
        try:case.official.begin_intent(original['id'],value['publication_id'],1,'init')
        except WorkflowError as error:assert error.code=='NATIVE_TIKTOK_PUBLISH_EVIDENCE_SCOPE_CHANGED'
        else:raise AssertionError('Current creator preflight must precede initialization')
    case.official.revoke(original['id'],value['publication_id'],Action(expected_snapshot_sha256=value['snapshot_sha256']),principal=case.principal)
    final=case.official.get(original['id'],value['publication_id']);assert final['status']=='review_required' and final['snapshot']==value['snapshot'] and final['receipt'] is None and final['published'] is False
    assert len(case.wire)==2 and case.store.get(original['id'])==original
    write(out/'expected.json',{'fixture_kind':KIND,'project':original,'publication':final,'journals':journals(case.store)})
    write(out/'flow.json',{'fixture_kind':KIND,'creator_check':case.check,'draft':case.draft,'dry_run':case.parent,'prepared':value,'approved':approved,'revoked':final,'original_mock_creator_wires':case.wire,
        'real_provider_calls':0,'publishing_execution_exercised':False,'source_final_sha256':file_sha(case.store.root/'jobs'/case.job['id']/'final.mp4')})
    archive=out/'public-tiktok-distribution-admission.zip';backup=create_backup(settings(case.store.root),archive);write(out/'backup.json',backup)
    write(out/'restore.json',restore_backup(archive,restored,expected_sha256=backup['sha256']));finish(args)
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--fixture-root',type=Path);parser.add_argument('--restore-root',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);choice=parser.add_mutually_exclusive_group();choice.add_argument('--replay',action='store_true');choice.add_argument('--resume-finish',action='store_true');args=parser.parse_args()
    replay(args) if args.replay else finish(args) if args.resume_finish else run(args)
if __name__=='__main__':main()
