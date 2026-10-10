"""Separate-process, keyless recovery of the owned narrated editor media bundle."""
import argparse,copy,json,sys,tempfile
from dataclasses import replace
from pathlib import Path
REPO=Path(__file__).resolve().parents[1];sys.path.insert(0,str(REPO))
from services.windows_native.backup import restore_backup
from services.windows_native.pipeline import Config
from services.windows_native.store import Store
from services.windows_native.contracts import file_sha,digest,WorkflowError
from services.windows_native.hardening import durable_json
from services.windows_native.narrated_media_mix import verify,validate_bundle
from services.windows_native.narrated_timeline_editor import view,restore
from services.windows_native.source_media_tracks import catalog

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--bundle',type=Path,required=True);parser.add_argument('--receipt',type=Path,required=True);args=parser.parse_args()
    bundle=args.bundle.resolve();receipt=args.receipt.resolve()
    if receipt.exists() or REPO==bundle or REPO in bundle.parents:raise ValueError('Fresh external recovery proof required')
    evidence=json.loads((bundle/'evidence.json').read_bytes());saved=json.loads((bundle/'timeline-editor.json').read_bytes());backup=json.loads((bundle/'backup-restore.json').read_bytes())['backup']
    for relative,expected in evidence['exports'].items():
        path=(bundle/relative).resolve()
        if bundle not in path.parents or file_sha(path)!=expected:raise AssertionError('Retained bundle source changed')
    if file_sha(bundle/'backup.zip')!=backup['sha256']:raise AssertionError('Backup hash differs')
    with tempfile.TemporaryDirectory(dir='C:/' if evidence.get('canonical_video_render') else None,
            prefix='vf-nv-r-' if evidence.get('canonical_video_render') else 'vf-owned-narrated-timeline-restore-') as owned:
        parent=Path(owned).resolve();destination=parent/'state';result=restore_backup(bundle/'backup.zip',destination,expected_sha256=backup['sha256'])
        if destination.resolve().parent!=parent:raise AssertionError('Owned restoration escaped its parent')
        store=Store(destination);config=replace(Config(),data_root=destination);project_id=evidence['project_id'];before=store.get(project_id)
        actual=view(store,project_id,saved['workspace_id'])
        if actual!=saved:raise AssertionError('Cold canonical history differs')
        verify(config,before['document']);validate_bundle(config,before['document'],destination/'jobs'/evidence['job_id'])
        with store.transaction() as con:store.verified_render(evidence['job_id'],con)
        tamper_tests=[]
        if evidence.get('canonical_video_render'):
            directory=destination/'jobs'/evidence['job_id'];record=directory/'narrated-video-render.json';original=record.read_bytes();data=json.loads(original)
            forged=copy.deepcopy(data);forged['manifest']['visual_clips'][0]['source_start']+=.1;forged['manifest_sha256']=digest(forged['manifest'])
            try:
                durable_json(record,forged)
                try:validate_bundle(config,before['document'],directory)
                except WorkflowError as error:
                    if error.code!='NARRATED_VIDEO_CANONICAL_RENDER_CHANGED':raise
                    tamper_tests.append('source_window_changed_with_recomputed_manifest_digest')
                else:raise AssertionError('Changed canonical source window accepted')
            finally:record.write_bytes(original)
            overlay=directory/next(iter(data['header_sha256']));pixels=overlay.read_bytes()
            try:
                overlay.write_bytes(pixels[:-1]+bytes([pixels[-1]^1]))
                try:validate_bundle(config,before['document'],directory)
                except WorkflowError as error:
                    if error.code!='NARRATED_VIDEO_OVERLAY_CHANGED':raise
                    tamper_tests.append('retained_brand_overlay_changed')
                else:raise AssertionError('Changed retained overlay accepted')
            finally:overlay.write_bytes(pixels)
            validate_bundle(config,before['document'],directory)
        # Fresh recovery-only edits prove that restoration did not flatten history.
        target=actual['history'][-2]
        undone=restore(store,project_id,{'revision':actual['revision'],'expected_version':actual['timeline_version'],'timeline_sha256':actual['timeline_sha256'],
            'restore_revision':target['revision'],'restore_timeline_sha256':target['sha256']},saved['workspace_id'])
        if undone['timeline_sha256']!=target['sha256']:raise AssertionError('Cold undo differs')
        redone=restore(store,project_id,{'revision':undone['revision'],'expected_version':undone['timeline_version'],'timeline_sha256':undone['timeline_sha256'],
            'restore_revision':actual['revision'],'restore_timeline_sha256':actual['timeline_sha256']},saved['workspace_id'])
        if redone['timeline_sha256']!=actual['timeline_sha256'] or store.get(project_id)['approval'] is not None:raise AssertionError('Cold redo or approval fence differs')
        if store.get(project_id)['jobs']!=before['jobs']:raise AssertionError('Recovery edits dispatched or changed jobs')
        durable_json(receipt,{'schema_version':'native-narrated-timeline-cold-recovery-v1','bundle':str(bundle),'backup_sha256':backup['sha256'],
            'actual_separate_process':True,'keyless':True,'canonical_history_exact':True,'physical_sources_and_render_verified':True,
            'undo_sha256':undone['timeline_sha256'],'redo_sha256':redone['timeline_sha256'],'undo_redo_create_new_versions':True,'approval_invalidated':True,
            'jobs_unchanged':True,'provider_calls':0,'paid_calls':0,'real_published':False,'owner_UAT':False,'browser_rendered':False,
            'canonical_video_tamper_rejections':tamper_tests,
            'owned_new_restore_cleaned_after_receipt':True,'historical_data_deleted':False,'restoration':result})
    print(json.dumps({'restored':True,'cold_undo_redo':True,'provider_calls':0,'receipt':str(receipt)}))

if __name__=='__main__':main()
