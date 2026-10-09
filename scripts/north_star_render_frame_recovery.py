"""Keyless original render-frame/current checkpoint and public restore proof."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'apps/api'))
from services.windows_native.backup import create_backup,restore_backup
from services.windows_native.contracts import digest,file_sha
from services.windows_native.hardening import Artifacts
from services.windows_native.pipeline import Config
from services.windows_native.render_frame_qc import validate
from services.windows_native.store import Store
from scripts.north_star_official_vision import write
from scripts.north_star_google_oauth_operations import journals


def owned(path,fresh=False):
    path=path.resolve()
    if path.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-[a-z0-9-]+',path.name) or fresh and path.exists():
        raise ValueError('Distinct explicitly owned fixture root required')
    return path


def snapshot(root):
    store=Store(root);records=[];renders=[]
    projects=[store.get(p['id']) for p in store.list(include_archived=True)]
    with store.transaction() as con:
        jobs=[store.job(row,con) for row in con.execute('SELECT * FROM jobs ORDER BY id')]
    for job in jobs:
        if job['kind']!='render' or job['status']!='succeeded':continue
        qc=job['result']['qc'];evidence=qc.get('rendered_frame_evidence') or (qc.get('full_quality') or {}).get('full_production_qc',{}).get('rendered_frame_evidence')
        if evidence is None:continue
        directory=root/'jobs'/job['id'];checkpoint=Artifacts(directory,job).load('render')
        assert checkpoint and checkpoint['result']==job['result']
        saved=json.loads((directory/'render-frame-qc.json').read_bytes());assert saved==evidence
        value=validate(directory,saved,document_sha256=digest(job['snapshot']['document']))
        assert value['rendered_video_sha256']==qc['final_sha256']
        names={'render-frame-qc.json','render-frame-qc.log',*(f['evidence_frame_reference'] for f in value['frames'])}
        assert names.issubset({v['path'] for v in checkpoint['artifacts']})
        renders.append({'job_id':job['id'],'render_sha256':value['rendered_video_sha256'],'frame_count':len(value['frames']),'record_sha256':saved['sha256']})
    assert renders,'One actual new successful render required'
    # Includes original attempts and the preview.mp4 materialization, verifying
    # original PTS/PNG evidence without rewriting records or reopening consent.
    for file in sorted(root.rglob('render-frame-qc.json')):
        saved=json.loads(file.read_bytes());directory=file.parent
        materialized='final.mp4' if (directory/'final.mp4').is_file() else 'preview.mp4'
        value=validate(directory,saved,materialized_video_name=materialized)
        assert value['semantic_inference_performed'] is False and value['owner_uat_accepted'] is False
        records.append({'path':file.relative_to(root).as_posix(),'sha256':file_sha(file),'frame_count':len(value['frames']),
            'materialized_video_name':materialized,'record_sha256':saved['sha256']})
    files={file.relative_to(root).as_posix():{'sha256':file_sha(file),'bytes':file.stat().st_size}
        for name in ('assets','originals','jobs','shot-previews') for file in sorted((root/name).rglob('*')) if file.is_file()}
    return {'projects':projects,'journals':journals(store),'files':files,'records':records,'successful_renders':renders,
        'external_dispatches':0,'paid_operations':0,'semantic_provider_tested':False,'owner_uat_accepted':False}


def run(args):
    root=owned(args.state_root);restored=owned(args.restore_root,not (args.reopen or args.verify_existing));out=args.output.resolve()
    if root==restored or not root.is_dir() or out==ROOT or ROOT in out.parents or out==root or root in out.parents:
        raise ValueError('Distinct external fixture/evidence paths required')
    absent=root.parent/(root.name+'-absent-secrets')
    config=Config(data_root=root,secret_file=absent/'absent-openai.env',assemblyai_secret_file=absent/'absent-asr.dpapi')
    assert not config.secret_file.exists() and not config.assemblyai_secret_file.exists()
    if args.reopen or args.verify_existing:
        expected=json.loads((out/'snapshot.json').read_bytes())
        assert snapshot(root)==snapshot(restored)==expected
        if args.verify_existing:assert file_sha(out/'public-render-frame-qc.zip')==json.loads((out/'backup.json').read_bytes())['sha256']
        write(out/('final-reader-revalidation.json' if args.verify_existing else 'new-process-replay.json'),{
            'original_projects_journals_all_media_render_frame_png_pts_and_checkpoints_exact':True,
            'fresh_process_keyless':True,'new_video_decode_or_render':False,'existing_png_pixels_revalidated':True,
            'original_decoder_log_pts_revalidated':True,'external_dispatches':0,'paid_operations':0,'owner_uat_accepted':False,
            'reader_sha256':file_sha(ROOT/'services/windows_native/render_frame_qc.py')})
        print(json.dumps({'status':'PASS','new_process':True,'render_frame_records':len(expected['records'])}));return
    if out.exists():raise ValueError('Fresh external evidence directory required')
    out.mkdir(parents=True);before=snapshot(root);write(out/'snapshot.json',before)
    backup=create_backup(config,out/'public-render-frame-qc.zip');write(out/'backup.json',backup)
    write(out/'restore.json',restore_backup(out/'public-render-frame-qc.zip',restored,expected_sha256=backup['sha256']))
    assert snapshot(root)==snapshot(restored)==before
    command=[sys.executable,str(Path(__file__).resolve()),'--state-root',str(root),'--restore-root',str(restored),'--output',str(out),'--reopen']
    result=subprocess.run(command,capture_output=True,timeout=90,check=True)
    write(out/'evidence.json',{'status':'PASS','successful_renders':before['successful_renders'],'render_frame_records':len(before['records']),
        'public_backup_sha256':backup['sha256'],'new_process_stdout':result.stdout.decode().strip(),
        'all_original_projects_journals_media_and_original_render_frame_evidence_exact':True,
        'semantic_provider_tested':False,'external_dispatches':0,'paid_operations':0,'owner_uat_accepted':False,'production_deployed':False,
        'source_sha256':{p:file_sha(ROOT/p) for p in ('services/windows_native/render_frame_qc.py',
            'services/windows_native/source_render.py','services/windows_native/storyboard_qc.py','services/windows_native/narration_preview.py',
            'services/windows_native/pipeline.py','apps/api/app/production_qc.py','scripts/north_star_render_frame_recovery.py')}})
    print(json.dumps({'status':'PASS','render_frame_records':len(before['records']),'public_backup_sha256':backup['sha256']}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--state-root',type=Path,required=True)
    parser.add_argument('--restore-root',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--reopen',action='store_true');parser.add_argument('--verify-existing',action='store_true');run(parser.parse_args())
