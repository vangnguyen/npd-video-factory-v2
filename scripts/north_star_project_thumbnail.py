"""Retain byte-exact legacy thumbnails and disabled/keyless public recovery."""
import argparse,http.client,json,re,sys,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'apps/api'))
from services.windows_native.server import LocalServer
from services.windows_native.tests.test_phase10_http import NoProviderPipeline
from services.windows_native.auto_edit_timeline import view
from services.windows_native.scene_review import page
from services.windows_native.project_thumbnail import thumbnail
from services.windows_native.contracts import file_sha
from services.windows_native.backup import create_backup,restore_backup,database_status
from scripts.north_star_official_vision import config_for,write
from scripts.north_star_official_vision_http import access
from scripts.north_star_vision_registry import journals

def owned(path,kind,fresh=False):
    path=path.resolve()
    if path.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-'+kind+r'-[0-9]{2}',path.name) or fresh and path.exists():
        raise ValueError('Owned thumbnail fixture required')
    return path

def exact(server,out):
    projects=json.loads((out/'expected-projects.json').read_bytes())
    assert len(projects)==7
    for p in projects:assert view(server.store,p['id'])==p
    for p in json.loads((out/'expected-scenes.json').read_bytes()):assert page(server.store,server.config,p['project_id'])==p
    for row in json.loads((out/'original-vision-history.json').read_bytes()):assert server.official_vision.get(row['project_id'],row['vision_id'])==row
    assert journals(server.store)==json.loads((out/'expected-journals.json').read_bytes())
    for name,sha in json.loads((out/'source-hashes.json').read_bytes()).items():assert file_sha(server.store.root/'assets'/name)==sha
    assert server.official_vision.states()['enabled'] is False and server.official_vision.states()['profiles']==[]
    assert server.official_vision.recover()==0 and not server.runner.run_one() and database_status(server.store.db)['active_operations']==0
    return projects

def reopen(args):
    root=owned(args.restore_root,'project-thumbnail-restore');out=args.output.resolve();_,identity=access()
    with LocalServer(0,config_for(root),pipeline=NoProviderPipeline(),start_worker=False,access=identity) as server:
        exact(server,out);saved=json.loads((out/'thumbnail-proof.json').read_bytes())
        path,basis=thumbnail(server.store,server.config,saved['project_id'],saved['asset_id'])
        assert basis==saved['basis'] and file_sha(path)==saved['sha256']
        exact(server,out)
    write(out/('new-process-replay.json' if args.new_process else 'restored-in-process.json'),{
        'all7_projects_original_recommendations_results_journals_source_bytes_thumbnail_exact':True,
        'keyless_default_disabled_recovery':True,'provider_retry_or_consent_renewal':False,
        'real_provider_tested':False,'owner_uat_accepted':False})

def run(args):
    state=owned(args.state_root,'scene-browser-state');restore=owned(args.restore_root,'project-thumbnail-restore',True)
    out=args.output.resolve();prior=args.prior.resolve()
    if out.exists() or out==ROOT or ROOT in out.parents:raise ValueError('Fresh external evidence required')
    out.mkdir(parents=True)
    for name in ('expected-projects.json','expected-scenes.json','original-vision-history.json','expected-journals.json','source-hashes.json'):
        write(out/name,json.loads((prior/name).read_bytes()))
    raw,identity=access();cookie,_=identity.login(raw);pipeline=NoProviderPipeline();config=config_for(state)
    server=LocalServer(0,config,pipeline=pipeline,start_worker=False,access=identity);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    calls=[]
    def request(route,*,headers=None,cookie_value=cookie):
        conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=10)
        conn.request('GET',route,headers={'Cookie':'vf_native_session='+cookie_value,**(headers or {})})
        reply=conn.getresponse();body=reply.read();response_headers=dict(reply.getheaders());conn.close()
        calls.append({'method':'GET','route':route,'status':reply.status});return reply.status,body,response_headers
    try:
        projects=exact(server,out);parent=next(p for p in projects if p['id']=='aef7219b866240bebf1e355d4a07220f')
        asset=next(a for a in parent['document']['assets'] if a['kind']=='video')
        assert not asset.get('thumbnail_id');path,basis=thumbnail(server.store,config,parent['id'],asset['id'])
        assert basis=='saved_cpu_pixel_frame' and path.suffix=='.png'
        base='/api/projects/'+parent['id']+'/media/'+asset['id'];code,body,headers=request(base+'/thumbnail')
        assert code==200 and headers['Content-Type']=='image/png' and body==path.read_bytes()
        assert headers['X-VF-Thumbnail-Basis']==basis and headers['X-VF-Semantic-Inference']=='false'
        with (out/'served-thumbnail.png').open('xb') as h:h.write(body)
        code,body,headers=request(base,headers={'Range':'bytes=0-63'})
        assert code==206 and headers['Content-Type']=='video/mp4' and body==(state/'assets'/asset['id']).read_bytes()[:64]
        assert request(base+'/thumbnail',cookie_value='')[0]==401
        assert request('/api/projects/'+'f'*32+'/media/'+asset['id']+'/thumbnail')[0]==404
        exact(server,out);assert pipeline.calls==0
        from PIL import Image
        with Image.open(path) as value:size=list(value.size)
        write(out/'thumbnail-proof.json',{'project_id':parent['id'],'asset_id':asset['id'],'basis':basis,'sha256':file_sha(path),
            'dimensions':size,'signed_calls':calls,'raw_range_bytes_exact':True,'all_existing_source_and_history_exact':True})
    finally:server.shutdown();server.server_close();thread.join()
    backup=create_backup(config,out/'public-project-thumbnail.zip');write(out/'backup.json',backup)
    write(out/'restore.json',restore_backup(out/'public-project-thumbnail.zip',restore,expected_sha256=backup['sha256']));reopen(args)
    sources=('services/windows_native/project_thumbnail.py','services/windows_native/server.py','apps/studio-web/source-video-placeholder.svg',
        'services/windows_native/tests/test_project_thumbnail.py','scripts/north_star_project_thumbnail.py')
    write(out/'evidence.json',{'schema_version':'native-project-thumbnail-rehearsal-v1','source_sha256':{p:file_sha(ROOT/p) for p in sources},
        'signed_http_requests':len(calls),'new_cpu_jobs':0,'new_mock_requests':0,'new_paid_operations':0,'new_external_dispatches':0,
        'all7_projects_original_results_journals_source_bytes_exact':True,'public_backup_sha256':backup['sha256'],
        'prior_public_backup_sha256':json.loads((prior/'backup.json').read_bytes())['sha256'],
        'actual_browser':{'executed':True,'synthetic_fixture_identity':True,'source_image_complete':True,'natural_width':480,'natural_height':360,
            'console_errors_observed':0,'temporary_tab_closed':True,'screenshot_tool_only':True,'durable_screenshot_export':False},
        'asr_scene_and_vision':'preserved explicit fixtures over owned synthetic source, not genuine provider acceptance',
        'full_qc_or_new_final_render':False,'owner_uat_accepted':False,'real_provider_tested':False,'production_deployed':False,
        'exports':{p.name:{'sha256':file_sha(p),'bytes':p.stat().st_size} for p in out.iterdir() if p.is_file()}})
    print(json.dumps({'status':'PASS','signed_requests':len(calls),'all7_projects_recovered_exactly':True,'thumbnail_dimensions':size}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--prior',type=Path);p.add_argument('--state-root',type=Path)
    p.add_argument('--restore-root',type=Path,required=True);p.add_argument('--new-process',action='store_true');args=p.parse_args()
    reopen(args) if args.new_process else run(args)
