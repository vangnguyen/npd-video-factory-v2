"""Two-niche local Native planner/preview/restore rehearsal, explicit content fixtures.

No research, semantic Vision, generated media, TTS, approval or final render is
claimed. Actual human HTTP, ingest, SQLite, FFmpeg visual preview and recovery.
"""
import argparse,http.client,json,re,shutil,subprocess,sys,threading,time
from pathlib import Path
from urllib.parse import quote
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from services.windows_native.access import NativeAccess
from services.windows_native.backup import create_backup,restore_backup
from services.windows_native.contracts import digest,file_sha
from services.windows_native.pipeline import Config
from services.windows_native.server import LocalServer
from services.windows_native.store import Store
from services.windows_native.tests.test_human_identity import fixture
from services.windows_native.costs import CostLedger
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier

WORKSPACE='wsp_native_storyboard_media_fixture'

def config(root):
    absent=root.parent/(root.name+'-absent-secrets')
    return Config(data_root=root,runtime_root=root/'absent-runtime',secret_file=absent/'absent-openai.env',assemblyai_secret_file=absent/'absent-asr.dpapi')

def snapshot(root):
    store=Store(root);projects=[store.get(value['id']) for value in store.list(include_archived=True)]
    with store.transaction() as con:events=[dict(row) for row in con.execute('SELECT * FROM events ORDER BY id')]
    return {'projects':projects,'versions':{project['id']:store.versions(project['id']) for project in projects},'events':events,
        'assets':{path.name:{'sha256':file_sha(path),'bytes':path.stat().st_size} for path in sorted((root/'assets').glob('*')) if path.is_file()},
        'previews':{str(path.relative_to(root)):{'sha256':file_sha(path),'bytes':path.stat().st_size} for path in sorted((root/'shot-previews').rglob('*')) if path.is_file()},
        'costs':{project['id']:CostLedger(store).summary(project['id']) for project in projects}}

class NoProviderPipeline:
    def run(self,*args):raise AssertionError('Planner rehearsal cannot execute providers/TTS/core production')

def run(args):
    root=args.data_root.resolve();destination=args.restore_root.resolve();out=args.output.resolve()
    for path in [root,destination]:
        if path.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-studio-media-plan-[a-z0-9-]+',path.name) or path.exists():raise ValueError('Fresh owned planner fixture roots required')
    if root==destination or out==ROOT or ROOT in out.parents or out==root or root in out.parents:raise ValueError('Distinct external output required')
    root.mkdir();out.mkdir(parents=True,exist_ok=False);settings=config(root)
    raw,registry=fixture('owner',workspace=WORKSPACE);access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(registry),max_token_ttl_seconds=86400),WORKSPACE)
    server=LocalServer(0,settings,pipeline=NoProviderPipeline(),start_worker=False,access=access);cookie,session=access.login(raw)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();requests=[];results=[]
    def send(method,path,body=None,*,expected=200,binary=None,headers=None):
        connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=30)
        connection.request(method,path,body=binary if binary is not None else json.dumps(body) if body is not None else None,
            headers={'Content-Type':'application/json','Cookie':'vf_native_session='+cookie,'X-VF-CSRF':session.csrf,**(headers or {})})
        response=connection.getresponse();payload=response.read();connection.close();value=json.loads(payload)
        requests.append({'method':method,'path':path,'status':response.status});assert response.status==expected,(response.status,value);return value
    try:
        catalog=send('GET','/api/channel-profiles');assert len(catalog['selections'])==2
        for selection in catalog['selections']:
            profile=selection['profile'];project=send('POST','/api/projects',{'name':profile['name']+' · EXPLICIT STORYBOARD FIXTURE','prompt':'A deliberately written fixture; no content provider',
                'channel_profile_ref':profile['profile_ref']},expected=201)
            identifier=project['id'];base=f'/api/projects/{identifier}';folder=out/profile['profile_ref'];folder.mkdir()
            words=['Technology AI','Data processing'] if profile['niche_profile']['niche']=='technology' else ['Nhà ở Việt Nam','Không gian đô thị']
            for i,text in enumerate(words):
                source=root/f'explicit-owned-source-{profile["content_profile_id"]}-{i}.png';image=Image.new('RGB',(640,360),(18,65+i*60,135));draw=ImageDraw.Draw(image)
                draw.rectangle((80,70,550,280),fill=(170,40+i*80,90));draw.ellipse((150,100,310,260),fill=(30,210,190));image.save(source)
                project=send('POST',base+'/media',expected=201,binary=source.read_bytes(),headers={'Content-Type':'image/png','X-VF-Revision':str(project['revision']),
                    'X-VF-Rights':'confirmed','X-VF-Illustration':'true','X-VF-Filename':quote(text+' · explicit-owned-fixture.png',safe='')})
            assets=project['document']['assets'];source_hashes={asset['id']:asset['sha256'] for asset in assets}
            proposal={'narration':'Đây là nội dung kiểm thử. Tư liệu được chọn và xem lại.',
                'visual_brief':[{'scene':1,'visual':words[0],'on_screen_text':'Kiểm thử kế hoạch','narration_excerpt':'Đây là nội dung kiểm thử.'},
                    {'scene':2,'visual':words[1],'on_screen_text':'Tư liệu có nguồn','narration_excerpt':'Tư liệu được chọn và xem lại.'}],'facts_needing_source':['Explicit authored fixture; not researched content']}
            project=send('POST',base+'/draft',{'revision':project['revision'],'proposal':proposal,'scene_media':[{'scene':1,'asset_id':assets[0]['id']},{'scene':2,'asset_id':assets[1]['id']}]})
            project=send('GET',base+'/shots')
            for shot in project['shot_timeline']['shots']:
                project=send('POST',base+'/shots',{'revision':project['revision'],'operation':{'type':'update','shot_id':shot['shot_id'],'values':{'duration':1.5}}})
            before=server.store.shot_view(identifier);page=send('POST',base+'/media-plans',{'revision':before['revision'],'expected_timeline_version':before['shot_timeline']['version'],
                'options':{'platform':'youtube_shorts','preferred_media_type':'image'}})
            record=page['items'][-1];assert record['input_current'];assert record['plan']['input']['niche']==profile['niche_profile']['niche']
            assert record['plan']['input']['channel_profile']==before['document']['channel_profile'];assert server.store.shot_view(identifier)['shot_timeline']['snapshot']==before['shot_timeline']['snapshot']
            assert all(item['status']=='selected' for item in record['plan']['items']);assert all(item['estimated_cost_vnd'] is None for item in record['plan']['items'])
            original=server.store.get(identifier);cached=send('POST',base+'/media-plans',{'revision':original['revision'],'expected_timeline_version':before['shot_timeline']['version'],
                'options':{'platform':'youtube_shorts','preferred_media_type':'image'}});assert cached==page;assert server.store.get(identifier)==original
            def action(value):return {'revision':server.store.get(identifier)['revision'],'expected_plan_version':value['plan']['version'],'expected_plan_sha256':value['sha256']}
            first=record['plan']['items'][0];selected=send('POST',base+'/media-plans/'+record['plan']['media_plan_id']+'/select',{**action(record),'shot_id':first['shot_id'],
                'asset_id':assets[1]['id'],'expected_asset_sha256':assets[1]['sha256']})['items'][-1]
            assert server.store.shot_view(identifier)['shot_timeline']['snapshot']==before['shot_timeline']['snapshot']
            applied=send('POST',base+'/media-plans/'+selected['plan']['media_plan_id']+'/apply',{**action(selected),'shot_ids':[first['shot_id']],'acknowledged':True})
            current=send('GET',base+'/shots');assert current['shot_timeline']['shots'][0]['asset_id']==assets[1]['id'];assert current['shot_timeline']['shots'][1:]==before['shot_timeline']['shots'][1:]
            assert current['approval'] is None and not current['jobs'];receipt=applied['items'][-1]['plan']['application'];assert receipt['timeline_sha256']==current['document']['canonical_timeline']['sha256']
            denied=send('POST',base+'/media-plans/'+selected['plan']['media_plan_id']+'/apply',{**action(selected),'shot_ids':[first['shot_id']],'acknowledged':True},expected=409)
            assert denied['code']=='STUDIO_MEDIA_PLAN_VERSION_CHANGED'
            send('POST',base+'/preview',{'revision':current['revision'],'action':'generate'});deadline=time.monotonic()+180
            while time.monotonic()<deadline:
                preview=server.previews.status(identifier)
                if preview['status'] not in {'QUEUED','RUNNING'}:break
                time.sleep(.1)
            assert preview['status']=='READY',preview;assert preview['audio_mode']=='silent_visual_proxy' and preview['final_approval_eligible'] is False
            video=server.previews.video_path(identifier,preview['timeline_version']);shutil.copyfile(video,folder/'preview.mp4')
            probe=json.loads(subprocess.check_output([str(settings.ffmpeg_bin/'ffprobe.exe'),'-v','error','-show_streams','-show_format','-of','json',str(video)],text=True))
            stream=next(item for item in probe['streams'] if item['codec_type']=='video');assert (stream['width'],stream['height'])==(540,960);assert abs(float(probe['format']['duration'])-3)<.08
            subprocess.run([str(settings.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-n','-i',str(video),'-frames:v','1',str(folder/'preview-frame.png')],check=True,timeout=30)
            for asset in assets:assert file_sha(settings.data_root/'assets'/asset['id'])==source_hashes[asset['id']]
            current=server.store.shot_view(identifier);cost=CostLedger(server.store).summary(identifier);assert cost['attempted_operations']==0
            for name,value in [('project.json',current),('media-plan.json',applied),('timeline.json',current['document']['canonical_timeline']),('script.json',proposal),('preview.json',preview),('ffprobe.json',probe),('cost.json',cost),('source-hashes.json',source_hashes)]:
                (folder/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            results.append({'project_id':identifier,'channel_profile_ref':profile['profile_ref'],'niche':profile['niche_profile']['niche'],'media_plan_id':record['plan']['media_plan_id'],
                'plan_versions':3,'selected_shot':first['shot_id'],'preview_sha256':file_sha(folder/'preview.mp4'),'preview_dimensions':[540,960],'duration_seconds':float(probe['format']['duration']),
                'silent_visual_proxy':True,'final_approval_eligible':False,'actual_local_ingest_preview':True,'fixture_content':True,'source_hashes_unchanged':True})
            print(json.dumps({'niche':profile['niche_profile']['niche'],'preview':'PASS','plan':'PASS'}),flush=True)
        assert len(results)==2 and any(item['niche']=='technology' for item in results)
    finally:server.shutdown();server.server_close();thread.join(timeout=5)
    frozen=snapshot(root);restart=json.loads(subprocess.check_output([sys.executable,str(Path(__file__).resolve()),'--read-root',str(root)],timeout=60));assert restart==frozen
    backup=create_backup(settings,out/'native-studio-media-plan-backup.zip');restore=restore_backup(out/'native-studio-media-plan-backup.zip',destination,expected_sha256=backup['sha256'])
    restored=json.loads(subprocess.check_output([sys.executable,str(Path(__file__).resolve()),'--read-root',str(destination)],timeout=60));assert restored==frozen
    (out/'recovery.json').write_text(json.dumps({'backup':backup,'restore':restore,'separate_process_exact':True,'restored_root_exact':True},indent=2)+'\n',encoding='utf-8')
    (out/'http-requests.json').write_text(json.dumps(requests,indent=2)+'\n',encoding='utf-8')
    evidence={'schema':'native-storyboard-media-planner-rehearsal-v1','workspace_id':WORKSPACE,'source_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'source_sha256':{path:file_sha(ROOT/path) for path in ['services/windows_native/studio_media_models.py','services/windows_native/studio_media_planner.py','services/windows_native/studio_media_routes.py',
            'services/windows_native/server.py','services/windows_native/access.py','services/windows_native/store.py','apps/studio-web/native-media-planner.mjs','apps/studio-web/native.mjs','apps/studio-web/native.html','apps/studio-web/native.css',str(Path(__file__).relative_to(ROOT)).replace('\\','/')]},
        'results':results,'human_http_requests':len(requests),'restore':'PASS','provider_calls':0,'paid_operations':0,'owner_uat':False,'fixture_content':True,'transcription_tested':False,
        'tts_tested':False,'full_final_render_tested':False,'full_qc_tested':False,'stock_or_generation_executed':False,'semantic_vision_tested':False,'browser_usability_tested':False,'real_provider_acceptance_complete':False,'production_deployed':False,
        'exports':{str(path.relative_to(out)):{'sha256':file_sha(path),'bytes':path.stat().st_size} for path in sorted(out.rglob('*')) if path.is_file()}}
    (out/'evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({'status':'PASS','niches':2,'human_http_requests':len(requests),'provider_calls':0,'paid_operations':0,'restart_restore':'PASS'}),flush=True)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--data-root',type=Path);parser.add_argument('--restore-root',type=Path);parser.add_argument('--output',type=Path);parser.add_argument('--read-root',type=Path);args=parser.parse_args()
    if args.read_root:print(json.dumps(snapshot(args.read_root.resolve()),ensure_ascii=True));return
    run(args)

if __name__=='__main__':main()
