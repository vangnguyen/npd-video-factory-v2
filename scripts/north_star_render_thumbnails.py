"""Retain original PNG selections without a new render, provider or publish grant."""
import argparse,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'apps/api'))
from services.windows_native.backup import create_backup,restore_backup
from services.windows_native.contracts import file_sha,digest
from services.windows_native.render_thumbnails import NativeRenderThumbnails,Create
from services.windows_native.render_vision import NativeRenderVision
from services.windows_native.render_vision_frame_bridge import NativeRenderEvidenceFrameExtractor
from services.windows_native.store import Store
from scripts.north_star_google_oauth_operations import journals
from scripts.north_star_official_vision import config_for,write
from scripts.north_star_render_frame_recovery import owned,snapshot as media_snapshot

def readers(root):
    store=Store(root);config=config_for(root);vision=NativeRenderVision(store,config)
    return store,config,vision,NativeRenderThumbnails(store,config,render_vision=vision)

def reopen(args):
    root=owned(args.restore_root);out=args.output.resolve();store,config,vision,thumbs=readers(root)
    expected=json.loads((out/'expected-thumbnails.json').read_bytes())
    for row in expected:
        assert thumbs.get(row['project_id'],row['thumbnail_asset_id'])==row
        pixels,snapshot=thumbs.image(row['project_id'],row['thumbnail_asset_id']);assert pixels== (root/'jobs'/snapshot['request']['render_job_id']/snapshot['frame']['evidence_frame_reference']).read_bytes()
    for row in json.loads((out/'expected-vision.json').read_bytes()):assert vision.get(row['project_id'],row['vision_id'])==row
    assert journals(store)==json.loads((out/'expected-journals.json').read_bytes())
    assert media_snapshot(root)==json.loads((out/'expected-media.json').read_bytes())
    assert not vision.states()['enabled'] and vision.states()['profiles']==[] and vision.recover()==0
    write(out/('new-process-replay.json' if args.reopen else 'in-process-replay.json'),{'status':'PASS','original_thumbnail_vision_cost_journals_projects_media_png_pts_exact':True,
        'keyless_read_only':True,'new_provider_calls':0,'new_paid_operations':0,'new_media_copies_or_render':False,'owner_uat_accepted':False})
    print(json.dumps({'status':'PASS','keyless_original_thumbnail_selections':len(expected)}))

def run(args):
    root=owned(args.state_root,True);restored=owned(args.restore_root,True);out=args.output.resolve()
    if out.exists() or root==restored or out==ROOT or ROOT in out.parents or root in out.parents or restored in out.parents:raise ValueError('Fresh owned fixture/evidence paths required')
    if file_sha(args.input_bundle)!=args.expected_input_sha256:raise ValueError('Original public backup checksum required')
    out.mkdir(parents=True);write(out/'prior-restore.json',restore_backup(args.input_bundle,root,expected_sha256=args.expected_input_sha256))
    store,config,vision,thumbs=readers(root);original=store.get(args.project_id);prior_media=media_snapshot(root);prior_journals=journals(store)
    binding=NativeRenderEvidenceFrameExtractor(store,config,args.project_id,args.job_id).binding()
    frames=[f for f in binding['record']['observation']['frames'] if not f['pixel_facts']['black_sample']];assert len(frames)>=2
    histories=vision.page(args.project_id,limit=100)['items'];past=next(v for v in histories if v['status']=='succeeded' and v['snapshot']['input_binding']==binding)
    selected=[]
    for index,frame in enumerate((frames[0],frames[-1],frames[0])):
        reviewed=None if index!=2 else {'vision_id':past['vision_id'],'expected_snapshot_sha256':past['snapshot_sha256'],
            'expected_result_sha256':past['result_sha256'],'acknowledged_protocol_mock':past['result']['mock']}
        request=Create(revision=original['revision'],render_job_id=args.job_id,expected_render_input_sha256=digest(binding),frame_id=frame['frame_id'],
            expected_frame_sha256=frame['sha256'],acknowledged_thumbnail=True,reviewed_vision=reviewed,request_key='explicit-thumbnail-rehearsal-'+str(index))
        row,replay=thumbs.create(args.project_id,request,actor='EXPLICIT SYNTHETIC THUMBNAIL REVIEW — NOT OWNER UAT');assert not replay
        pixels,snapshot=thumbs.image(args.project_id,row['thumbnail_asset_id']);assert pixels==(root/'jobs'/args.job_id/frame['evidence_frame_reference']).read_bytes()
        assert snapshot['image']['rights_status']=='unknown' and snapshot['publishing_authorized'] is False
        assert thumbs.create(args.project_id,request,actor='EXPLICIT SECOND REVIEW')[0]==row;selected.append(row)
    assert store.get(args.project_id)==original
    current=journals(store)
    for name,rows in prior_journals.items():
        if name!='native_render_thumbnails':assert current[name]==rows,name
    after=media_snapshot(root);assert all(after[k]==prior_media[k] for k in ('projects','files','records','successful_renders'))
    for row in histories:assert vision.get(args.project_id,row['vision_id'])==row
    write(out/'expected-thumbnails.json',selected);write(out/'expected-vision.json',histories);write(out/'expected-journals.json',current);write(out/'expected-media.json',after)
    backup=create_backup(config,out/'public-render-thumbnails.zip');write(out/'backup.json',backup)
    write(out/'restore.json',restore_backup(out/'public-render-thumbnails.zip',restored,expected_sha256=backup['sha256']));args.reopen=False;reopen(args)
    result=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--restore-root',str(restored),'--output',str(out),'--reopen'],capture_output=True,check=True,timeout=120)
    sources=('services/windows_native/render_thumbnails.py','services/windows_native/backup.py','services/windows_native/tests/test_render_thumbnails.py','scripts/north_star_render_thumbnails.py')
    write(out/'evidence.json',{'schema_version':'native-render-thumbnail-rehearsal-v1','status':'PASS','source_sha256':{s:file_sha(ROOT/s) for s in sources},
        'explicit_thumbnail_selections':3,'manual_cpu_frame_selections':2,'original_reviewed_vision_selection':1,'unchanged_original_vision_histories':len(histories),
        'three_exact_original_png_reads':True,'all_original_projects_timeline_media_checkpoints_png_pts_exact':True,'original_cost_and_vision_journals_exact':True,
        'keyless_new_process_recovery_exact':True,'public_backup_sha256':backup['sha256'],'new_process_stdout':result.stdout.decode().strip(),
        'new_media_copies':0,'new_renders':0,'new_provider_calls':0,'new_paid_operations':0,'live_credentials_read':False,
        'semantic_inference_performed':False,'rights_status':'unknown','rights_independently_verified':False,'publishing_authorized':False,
        'thumbnail_publication_transport_bound':False,'http_or_studio_integrated':False,'owner_uat_accepted':False,'real_provider_tested':False,'production_deployed':False})
    print(json.dumps({'status':'PASS','original_thumbnail_selections':3,'original_vision_histories':len(histories),'public_backup_sha256':backup['sha256']}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input-bundle',type=Path);p.add_argument('--expected-input-sha256');p.add_argument('--state-root',type=Path)
    p.add_argument('--restore-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--project-id');p.add_argument('--job-id');p.add_argument('--reopen',action='store_true')
    args=p.parse_args();reopen(args) if args.reopen else run(args)
