"""Local resolver/renderer rehearsal over trusted saved benchmark evidence.

The source speech and saved ASR may be real local benchmark evidence. Added
visuals and approval are explicit CI fixtures, never Owner/Mode B acceptance.
"""
import argparse,copy,json,shutil,socket,subprocess,sys,tempfile,time,uuid
from pathlib import Path
from unittest.mock import patch
from PIL import Image
REPO=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(REPO),str(REPO/'apps/api')]
from services.windows_native.backup import create_backup,restore_backup
from services.windows_native.contracts import digest,file_sha
from services.windows_native.store import Store
from services.windows_native.pipeline import Config,Pipeline
from services.windows_native.server import Runner
from services.windows_native.shot_preview import PreviewManager
from services.windows_native.media import ingest_media
from services.windows_native.stock import NativeStock
from services.windows_native.generation_queue import NativeGenerationQueue
from services.windows_native.generation_worker import NativeGenerationWorker
from services.windows_native.source_broll_resolution import NativeSourceBrollResolution
from services.windows_native.source_broll_resolution_models import Create,Step,Apply
from services.windows_native import source_broll,source_settings


def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


original_connect=socket.socket.connect
def local_connect_only(sock,address):
    # Windows asyncio builds its own loopback socket pair. Keep that local IPC
    # available while denying any external endpoint in this rehearsal.
    if sock.family in (socket.AF_INET,socket.AF_INET6) and address[0] not in ('127.0.0.1','::1'):
        raise AssertionError('No external network in local rehearsal')
    return original_connect(sock,address)


def main():
    parser=argparse.ArgumentParser()
    for name in ('backup','backup-sha','project-id','output'):parser.add_argument('--'+name,required=True)
    args=parser.parse_args();out=Path(args.output).resolve();out.mkdir(exist_ok=False)
    workspace='wsp_word_browser_fixture'
    with tempfile.TemporaryDirectory(prefix='vf-source-broll-media-') as temporary:
        root=Path(temporary)/'state';restore=restore_backup(args.backup,root,expected_sha256=args.backup_sha)
        write(out/'initial-restore.json',restore);store=Store(root);config=Config(data_root=root)
        project=store.get(args.project_id);original=copy.deepcopy(project)
        source_hashes={str(p.relative_to(root)):file_sha(p) for folder in ('assets','originals') for p in (root/folder).rglob('*') if p.is_file()}
        stock=NativeStock(store,config,workspace_id=workspace)
        generation=NativeGenerationWorker(NativeGenerationQueue(store,workspace_id=workspace),config)
        resolver=NativeSourceBrollResolution(store,config,stock,generation,workspace_id=workspace)
        try:
            with patch.object(socket.socket,'connect',local_connect_only):
                project=source_broll.create(store,config,project['id'],project['revision'],
                    {'expected_version':project['document']['canonical_timeline']['version']},resolver_context=resolver.planning_context())
                query=project['document']['source_broll_plans'][-1]['plan']['items'][0]['broll']['search_query']
                picture=Path(temporary)/'explicit-owned-visual.png';Image.new('RGB',(640,360),(35,75,145)).save(picture)
                asset=ingest_media(config,picture,'image/png',query[:180]+'.png',rights_confirmed=True,illustration=True)
                asset.update(explicit_fixture=True,visual_semantics_verified=False,description='Explicit owned CI color pixels; not footage of the speech subject')
                project=store.append_media(project['id'],project['revision'],asset)
                project=source_broll.create(store,config,project['id'],project['revision'],
                    {'expected_version':project['document']['canonical_timeline']['version']},resolver_context=resolver.planning_context())
                record=project['document']['source_broll_plans'][-1];before=copy.deepcopy(project['document']['canonical_timeline'])
                session,_=resolver.create(project['id'],Create(revision=project['revision'],expected_timeline_version=before['version'],
                    media_plan_id=record['plan']['media_plan_id'],expected_plan_version=record['plan']['version'],expected_plan_sha256=record['sha256'],
                    item_ids=[record['plan']['items'][0]['media_plan_item_id']],request_key='source-local-create-'+uuid.uuid4().hex),actor='explicit-ci-editor')
                create_receipt=copy.deepcopy(session)
                step=Step(revision=project['revision'],expected_resolution_version=session['version'],request_key='source-local-step-'+uuid.uuid4().hex)
                transition,_=resolver.step(project['id'],session['resolution_id'],step,actor='explicit-ci-editor')
                session=resolver.get(project['id'],session['resolution_id']);assert session['state']['status']=='ready',session['state']
                project=store.get(project['id']);assert project['document']['canonical_timeline']==before
                request=Apply(revision=project['revision'],expected_resolution_version=session['version'],expected_timeline_version=before['version'],
                    acknowledged=True,request_key='source-local-apply-'+uuid.uuid4().hex)
                applied,_=resolver.apply(project['id'],session['resolution_id'],request,actor='explicit-ci-editor')
                assert resolver.apply(project['id'],session['resolution_id'],request,actor='explicit-ci-editor')==(applied,True)
                project=store.get(project['id']);timeline=project['document']['canonical_timeline']
                assert timeline['version']==before['version']+1 and project['approval'] is None
                assert [t for t in timeline['snapshot']['tracks'] if t['kind']!='broll']==[t for t in before['snapshot']['tracks'] if t['kind']!='broll']
                assert project['document']['media_analysis']==original['document']['media_analysis']
                assert project['document']['auto_edit_analyses']==original['document']['auto_edit_analyses']
                write(out/'resolution-created.json',create_receipt);write(out/'resolution-transition.json',transition)
                write(out/'resolution-applied.json',applied);write(out/'resolution-final.json',resolver.get(project['id'],session['resolution_id']))
                write(out/'timeline.json',timeline);write(out/'asset-provenance.json',project['document']['assets'])
                project=source_settings.configure(store,project['id'],project['revision'],{'expected_version':timeline['version'],'preview_mode':'final_effects'})
                manager=PreviewManager(config,store)
                try:
                    manager.generate(project['id'],project['revision']);deadline=time.monotonic()+300
                    while True:
                        preview=manager.status(project['id'])
                        if preview['status'] not in {'QUEUED','RUNNING'}:break
                        if time.monotonic()>deadline:raise RuntimeError('Owned preview deadline exceeded')
                        time.sleep(.2)
                    write(out/'preview-receipt.json',preview);assert preview['status']=='READY',preview.get('error')
                    shutil.copyfile(manager.video_path(project['id'],preview['timeline_version']),out/'preview.mp4')
                finally:manager.close()
                project=store.approve(project['id'],project['revision'],'EXPLICIT CI REVIEW FIXTURE; NOT OWNER UAT',True)
                job=store.enqueue(project['id'],project['revision'],'render',uuid.uuid4().hex)
                Runner(store,Pipeline(config)).run_one();finished=store.get_job(job['id']);write(out/'render-job.json',finished)
                folder=root/'jobs'/job['id']
                for name in ('final.mp4','timeline.json','subtitles.json','subtitles.ass','render-manifest.json','audio-analysis.json','audio-balance.json','source-audio-clocks.json','cost.json'):
                    if (folder/name).is_file():shutil.copyfile(folder/name,out/name)
                if finished['status']!='succeeded':
                    for path in folder.rglob('*.json'):
                        target=out/'failed-render'/path.relative_to(folder);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
                assert finished['status']=='succeeded',finished.get('error')
                write(out/'qc.json',finished['result']['qc']);assert finished['result']['qc']['passed'] is True
                assert all(file_sha(root/name)==sha for name,sha in source_hashes.items())
                with store.transaction() as con:
                    rows={name:[dict(row) for row in con.execute('SELECT * FROM '+name)] for name in (
                        'native_source_broll_resolutions','native_source_broll_resolution_events','native_source_broll_resolution_requests')}
                write(out/'resolver-rows.json',rows)
                backup=create_backup(config,out/'resolved-broll-state.zip');write(out/'backup.json',backup)
                with tempfile.TemporaryDirectory(prefix='vf-source-broll-cold-') as cold:
                    restored=Path(cold)/'state';restore_backup(backup['backup_path'],restored,expected_sha256=backup['sha256'])
                    cold_store=Store(restored)
                    assert cold_store.get(project['id'])==store.get(project['id'])
                    with cold_store.transaction() as con:
                        assert {name:[dict(row) for row in con.execute('SELECT * FROM '+name)] for name in rows}==rows
                write(out/'evidence.json',{'schema_version':'local-source-broll-resolution-media.v1','project_id':project['id'],
                    'source_backup_sha256':args.backup_sha,'source_bytes_raw_ASR_analysis_preserved':True,
                    'canonical_non_broll_tracks_preserved_on_apply':True,'explicit_apply_replay_no_duplicate':True,
                    'new_model_inferences':0,'external_provider_calls':0,'paid_operations':0,'added_visuals_and_approval_are_CI_fixtures':True,
                    'genuine_user_footage_accepted':False,'Owner_UAT':False,'full_Mode_A_B_accepted':False,'production_deployed':False,
                    'actual_preview_and_final_render':True,'QC_passed':True,'cold_restore_rows_and_project_exact':True,
                    'cold_restore_same_process':True,'final_sha256':file_sha(out/'final.mp4')})
        finally:stock.close();generation.close()
    print(json.dumps({'evidence':str(out),'QC_passed':True,'Owner_UAT':False,'full_Mode_A_B_accepted':False}))


if __name__=='__main__':main()
