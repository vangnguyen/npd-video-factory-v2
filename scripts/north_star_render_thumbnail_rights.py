"""Synthetic finite Owner exceptions; exact original media and keyless recovery."""
import argparse,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'apps/api'))
from services.windows_native.backup import create_backup,restore_backup
from services.windows_native.contracts import file_sha
from services.windows_native.render_thumbnail_rights import NativeRenderThumbnailRights,Create
from scripts.north_star_google_oauth_operations import journals
from scripts.north_star_official_vision import config_for,write
from scripts.north_star_render_frame_recovery import owned,snapshot as media_snapshot
from scripts.north_star_render_thumbnails import readers
from scripts.north_star_render_vision_http import access

def reopen(args):
    root=owned(args.restore_root);out=args.output.resolve();store,config,vision,thumbs=readers(root);rights=NativeRenderThumbnailRights(thumbs)
    expected=json.loads((out/'expected-rights.json').read_bytes())
    for row in expected:
        assert rights.get(row['project_id'],row['override_id'])==row
        assert rights.active(row['project_id'],row['thumbnail_asset_id']) is None
    for row in json.loads((out/'expected-thumbnails.json').read_bytes()):assert thumbs.get(row['project_id'],row['thumbnail_asset_id'])==row
    for row in json.loads((out/'expected-vision.json').read_bytes()):assert vision.get(row['project_id'],row['vision_id'])==row
    assert journals(store)==json.loads((out/'expected-journals.json').read_bytes())
    assert media_snapshot(root)==json.loads((out/'expected-media.json').read_bytes())
    assert rights.states()['enabled'] is False and rights.states()['rights_status']=='unknown' and rights.states()['publishing_authorized'] is False
    assert not vision.states()['enabled'] and vision.states()['profiles']==[] and vision.recover()==0
    write(out/('new-process-replay.json' if args.reopen else 'in-process-replay.json'),{'status':'PASS','original_exception_thumbnail_vision_cost_journals_projects_media_png_pts_exact':True,
        'keyless_read_only':True,'exceptions_automatically_reenabled':False,'publishing_authorized':False,'rights_status':'unknown','new_provider_calls':0,'new_paid_operations':0,'owner_uat_accepted':False})
    print(json.dumps({'status':'PASS','keyless_original_thumbnail_rights_records':len(expected)}))

def run(args):
    root=owned(args.state_root,True);restored=owned(args.restore_root,True);out=args.output.resolve()
    if out.exists() or root==restored or out==ROOT or ROOT in out.parents or root in out.parents or restored in out.parents:raise ValueError('Fresh owned fixture and evidence paths required')
    if file_sha(args.input_bundle)!=args.expected_input_sha256:raise ValueError('Exact original public backup required')
    out.mkdir(parents=True);write(out/'prior-restore.json',restore_backup(args.input_bundle,root,expected_sha256=args.expected_input_sha256))
    store,config,vision,thumbs=readers(root);raw,identity=access();principal=identity.verifier.verify('Bearer '+raw)
    rights=NativeRenderThumbnailRights(thumbs,enabled=True,identity_provider=lambda:identity.verifier)
    thumbnails=thumbs.page(args.project_id,limit=100)['items'];histories=vision.page(args.project_id,limit=100)['items'];selected=thumbnails[0]
    before=media_snapshot(root);prior=journals(store);input=rights.input(args.project_id,selected['thumbnail_asset_id']);project=store.get(args.project_id)
    def request(index,**changes):
        return Create.model_validate({'revision':project['revision'],'thumbnail_asset_id':selected['thumbnail_asset_id'],'expected_thumbnail_snapshot_sha256':selected['snapshot_sha256'],
            'expected_rights_input_sha256':input['rights_input_sha256'],'action':'grant','reason':'EXPLICIT SYNTHETIC OWNER THUMBNAIL EXCEPTION — NOT LICENSE OR REAL OWNER ACCEPTANCE',
            'evidence_reference':'document:explicit-synthetic-thumbnail-rights-rehearsal','valid_days':7,'allow_publishing_review':True,
            'acknowledged_thumbnail_rights_exception':True,'acknowledged_not_independent_license_verification':True,
            'request_key':'explicit-thumbnail-rights-rehearsal-'+str(index),**changes})
    first,replay=rights.record(args.project_id,request(0),principal=principal);assert not replay
    assert rights.active(args.project_id,selected['thumbnail_asset_id'])['override_id']==first['override_id']
    assert rights.record(args.project_id,request(0),principal=principal)==(first,True)
    second,replay=rights.record(args.project_id,request(1,allow_publishing_review=False),principal=principal);assert not replay
    assert rights.active(args.project_id,selected['thumbnail_asset_id']) is None
    assert rights.active(args.project_id,selected['thumbnail_asset_id'],publishing=False)['override_id']==second['override_id']
    revoked,replay=rights.record(args.project_id,request(2,action='revoke',allow_publishing_review=False,override_id=second['override_id'],expected_override_sha256=second['snapshot_sha256']),principal=principal);assert not replay
    assert rights.active(args.project_id,selected['thumbnail_asset_id'],publishing=False) is None
    third,replay=rights.record(args.project_id,request(3),principal=principal);assert not replay
    active=rights.active(args.project_id,selected['thumbnail_asset_id']);assert active['override_id']==third['override_id'] and active['rights_status']=='unknown' and active['license'] is None
    assert active['publishing_authorized'] is False and active['source_asset_rights_granted'] is False and active['rights_independently_verified'] is False
    expected=[first,second,revoked,third]
    for row in expected:assert rights.get(args.project_id,row['override_id'])==row
    for row in thumbnails:assert thumbs.get(args.project_id,row['thumbnail_asset_id'])==row
    for row in histories:assert vision.get(args.project_id,row['vision_id'])==row
    current=journals(store)
    for name,rows in prior.items():
        if name!='native_render_thumbnail_rights':assert current[name]==rows,name
    after=media_snapshot(root);assert all(after[k]==before[k] for k in ('projects','files','records','successful_renders'))
    assert raw not in json.dumps(expected) and raw not in json.dumps(active)
    write(out/'expected-rights.json',expected);write(out/'expected-thumbnails.json',thumbnails);write(out/'expected-vision.json',histories);write(out/'expected-journals.json',current);write(out/'expected-media.json',after)
    write(out/'synthetic-active-proof.json',active);backup=create_backup(config,out/'public-render-thumbnail-rights.zip');write(out/'backup.json',backup)
    write(out/'restore.json',restore_backup(out/'public-render-thumbnail-rights.zip',restored,expected_sha256=backup['sha256']));args.reopen=False;reopen(args)
    result=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--restore-root',str(restored),'--output',str(out),'--reopen'],capture_output=True,check=True,timeout=120)
    sources=('services/windows_native/render_thumbnail_rights.py','services/windows_native/backup.py','services/windows_native/tests/test_render_thumbnail_rights.py','scripts/north_star_render_thumbnail_rights.py')
    write(out/'evidence.json',{'schema_version':'native-render-thumbnail-rights-rehearsal-v1','status':'PASS','source_sha256':{s:file_sha(ROOT/s) for s in sources},
        'synthetic_current_owner_exception_records':4,'grant_records':3,'revoke_records':1,'unchanged_original_thumbnail_selections':len(thumbnails),'unchanged_original_vision_histories':len(histories),
        'original_projects_canonical_media_png_pts_cost_and_other_journals_exact':True,'keyless_new_process_recovery_exact':True,'exceptions_automatically_reenabled':False,
        'public_backup_sha256':backup['sha256'],'new_process_stdout':result.stdout.decode().strip(),'new_media_copies':0,'new_renders':0,'new_provider_calls':0,'new_paid_operations':0,
        'live_credentials_read':False,'rights_status':'unknown','license':None,'rights_independently_verified':False,'source_asset_rights_granted':False,'publishing_authorized':False,
        'http_or_studio_integrated':False,'thumbnail_publication_transport_bound':False,'real_owner_legal_override':False,'owner_uat_accepted':False,'real_provider_tested':False,'production_deployed':False})
    print(json.dumps({'status':'PASS','synthetic_owner_exception_records':4,'original_thumbnail_selections':len(thumbnails),'original_vision_histories':len(histories),'public_backup_sha256':backup['sha256']}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input-bundle',type=Path);p.add_argument('--expected-input-sha256');p.add_argument('--state-root',type=Path)
    p.add_argument('--restore-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--project-id');p.add_argument('--reopen',action='store_true')
    args=p.parse_args();reopen(args) if args.reopen else run(args)
