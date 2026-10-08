"""Actual native HTTP/worker/libass/full-QC/recovery; explicit synthetic PCM only.

No voice inference, semantic Vision, research, paid operation or Owner UAT is
claimed. Approval below belongs to an isolated signed human identity fixture.
"""
import argparse,http.client,io,json,re,shutil,subprocess,sys,threading,time,uuid
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from services.windows_native.access import NativeAccess
from services.windows_native.backup import create_backup,restore_backup
from services.windows_native.branding import FIT_NARRATION_POLICY
from services.windows_native.contracts import digest,file_sha,write_json
from services.windows_native.costs import CostLedger
from services.windows_native.hardening import Artifacts
from services.windows_native.pipeline import Config,Pipeline
from services.windows_native.server import LocalServer
from services.windows_native.store import Store
from services.windows_native.tests.test_human_identity import fixture
from services.windows_native.tests.test_shot_production import voice
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
WORKSPACE='wsp_native_storyboard_full_qc_fixture'

def write(path,value):
    with path.open('xb') as handle:handle.write((json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode())
def config(root):
    absent=root.parent/(root.name+'-absent-secrets')
    return Config(data_root=root,runtime_root=root/'absent-runtime',secret_file=absent/'absent-openai.env',assemblyai_secret_file=absent/'absent-asr.dpapi')
def snapshot(root):
    store=Store(root);projects=[store.get(row['id']) for row in store.list(include_archived=True)]
    with store.transaction() as con:
        events=[dict(row) for row in con.execute('SELECT * FROM events ORDER BY id')]
        jobs=[store.job(row,con) for row in con.execute('SELECT * FROM jobs ORDER BY id')]
    return {'projects':projects,'versions':{p['id']:store.versions(p['id']) for p in projects},'jobs':jobs,'events':events,
        'costs':{p['id']:CostLedger(store).summary(p['id']) for p in projects},
        'files':{str(path.relative_to(root)).replace('\\','/'):{'sha256':file_sha(path),'bytes':path.stat().st_size}
            for name in ['assets','originals','shot-previews','jobs'] for path in sorted((root/name).rglob('*')) if path.is_file()},
        'external_execution_enabled':False,'publishing_enabled':False}

class CachedToneFixture:
    def __init__(self,settings):self.settings=settings
    def run(self,job,stage):
        assert job['kind'] in {'render','narration'},'This rehearsal cannot dispatch other providers'
        if job['kind']=='narration' or not job['snapshot']['document'].get('prepared_narration'):
            out=self.settings.data_root/'jobs'/job['id'];out.mkdir(parents=True,exist_ok=False)
            voice(out);write_json(out/'tts-plan.json',{'explicit_synthetic_pcm_fixture':True,'actual_voice_inference':False,'provider_calls':0,'paid_operations':0})
            Artifacts(out,job).commit('tts',[out/'voice.wav',out/'voice.json',out/'tts-plan.json'],{'explicit_cached_pcm_fixture':True})
        with patch('services.windows_native.pipeline.verify_runtime'),patch('services.windows_native.pipeline.synthesize',side_effect=AssertionError('No voice inference')):
            return Pipeline(self.settings).run(job,stage)

def run(args):
    root,destination,out=args.data_root.resolve(),args.restore_root.resolve(),args.output.resolve()
    if args.reopen:
        expected=json.loads((out/'offline-snapshot.json').read_bytes());assert snapshot(root)==snapshot(destination)==expected
        for location in [root,destination]:
            for job in snapshot(location)['jobs']:
                if job['status']=='succeeded':
                    with patch('services.windows_native.pipeline.verify_runtime'),patch('services.windows_native.pipeline.synthesize',side_effect=AssertionError('No voice inference')):
                        assert Pipeline(config(location)).run(job,lambda _:None)==job['result']
        write(out/'new-process-replay.json',{'exact_source_and_restored_state':True,'exact_verified_render_checkpoint_replay':True,
            'external_execution_enabled':False,'provider_calls':0,'actual_voice_inference':False,'owner_uat_accepted':False})
        print(json.dumps({'status':'STORYBOARD_FULL_QC_RESTART_RESTORE_PASS'}));return
    for path in [root,destination]:
        if path.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-storyboard-qc-[a-z0-9-]+',path.name) or path.exists():raise ValueError('Fresh owned fixture roots required')
    if root==destination or out.exists() or out==ROOT or ROOT in out.parents or out==root or root in out.parents:raise ValueError('Fresh distinct external evidence required')
    root.mkdir();out.mkdir(parents=True);settings=config(root);requests=[]
    raw,registry=fixture('owner',workspace=WORKSPACE);access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(registry),max_token_ttl_seconds=86400),WORKSPACE)
    server=LocalServer(0,settings,pipeline=CachedToneFixture(settings),start_worker=False,access=access);cookie,session=access.login(raw)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    def send(method,path,body=None,*,status=200,binary=None,headers=None):
        connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=30)
        connection.request(method,path,body=binary if binary is not None else json.dumps(body) if body is not None else None,
            headers={'Content-Type':'application/json','Cookie':'vf_native_session='+cookie,'X-VF-CSRF':session.csrf,**(headers or {})})
        response=connection.getresponse();payload=response.read();content_type=response.getheader('Content-Type','');connection.close()
        value=json.loads(payload) if content_type.startswith('application/json') else {'bytes':len(payload),'sha256':__import__('hashlib').sha256(payload).hexdigest()}
        requests.append({'method':method,'path':path,'status':response.status});assert response.status==status,(response.status,value);return value
    try:
        project=send('POST','/api/projects',{'name':'EXPLICIT NATIVE FULL QC FIXTURE','prompt':'Authored synthetic teaching fixture; no research provider',
            'channel_profile_ref':'ai-education-reference@1','production_quality':True},status=201);identifier=project['id'];base='/api/projects/'+identifier
        for ordinal in range(2):
            image=Image.new('RGB',(640,360),(20,65+ordinal*40,135));drawing=ImageDraw.Draw(image)
            drawing.rectangle((80,70,550,280),fill=(170,40+ordinal*80,90));drawing.ellipse((150,100,310,260),fill=(30,210,190));buffer=io.BytesIO();image.save(buffer,format='PNG')
            project=send('POST',base+'/media',status=201,binary=buffer.getvalue(),headers={'Content-Type':'image/png','X-VF-Revision':str(project['revision']),
                'X-VF-Rights':'confirmed','X-VF-Illustration':'true','X-VF-Filename':quote(f'Technology AI educational explicit owned fixture {ordinal}.png',safe='')})
        assets=project['document']['assets'];proposal={'narration':'Xin chào. Cảm ơn.','visual_brief':[
            {'scene':1,'visual':'Technology AI educational fixture','on_screen_text':'Vang Nguyễn','narration_excerpt':'Xin chào.'},
            {'scene':2,'visual':'Technology teaching fixture','on_screen_text':'Cần Giờ','narration_excerpt':'Cảm ơn.'}],
            'facts_needing_source':['Explicit authored synthetic fixture; no researched claims']}
        project=send('POST',base+'/draft',{'revision':project['revision'],'proposal':proposal,'music_enabled':False,
            'scene_media':[{'scene':1,'asset_id':assets[0]['id']},{'scene':2,'asset_id':assets[1]['id']}]})
        project=send('POST',base+'/brand-template',{'revision':project['revision'],'brand_id':'vang-nguyen','template_id':'personal-30','duration_mode':FIT_NARRATION_POLICY})
        view=send('GET',base+'/shots')
        for shot in list(view['shot_timeline']['shots']):
            for values in [{'duration':1.5},{'requested_duration':None}]:
                view=send('POST',base+'/shots',{'revision':view['revision'],'operation':{'type':'update','shot_id':shot['shot_id'],'values':values}})
        page=send('POST',base+'/media-plans',{'revision':view['revision'],'expected_timeline_version':view['shot_timeline']['version'],
            'options':{'platform':'youtube_shorts','preferred_media_type':'image'}});record=page['items'][-1]
        assert all(item['status']=='selected' for item in record['plan']['items'])
        current=server.store.get(identifier)
        applied=send('POST',base+'/media-plans/'+record['plan']['media_plan_id']+'/apply',{'revision':current['revision'],
            'expected_plan_version':record['plan']['version'],'expected_plan_sha256':record['sha256'],'shot_ids':[item['shot_id'] for item in record['plan']['items']],'acknowledged':True})
        view=send('GET',base+'/shots');send('POST',base+'/preview',{'revision':view['revision'],'action':'generate'});deadline=time.monotonic()+45
        while True:
            preview=send('GET',base+'/preview')
            if preview['status'] not in {'QUEUED','RUNNING'}:break
            assert time.monotonic()<deadline;time.sleep(.05)
        assert preview['status']=='READY' and preview['audio_mode']=='silent_visual_proxy' and preview['final_approval_eligible'] is False
        shutil.copyfile(server.previews.video_path(identifier,preview['timeline_version']),out/('visual-proxy.mp4' if args.narration_preparation else 'preview.mp4'));write(out/('visual-proxy.json' if args.narration_preparation else 'preview.json'),preview)
        view=send('GET',base+'/shots');approval=send('POST',base+'/approve',{'revision':view['revision'],'reviewer':'EXPLICIT SIGNED HUMAN FIXTURE; NOT OWNER UAT','acknowledged':True,'purpose':'narration' if args.narration_preparation else 'production'})
        if args.narration_preparation:
            prepared=send('POST',base+'/jobs',{'revision':approval['revision'],'kind':'narration','request_key':'explicit-narration-preparation-01'});assert server.runner.run_one()
            prepared=next(job for job in send('GET',base)['jobs'] if job['id']==prepared['id']);assert prepared['status']=='succeeded',prepared
            page=send('GET',base+'/narration');assert page['items'][0]['result']==prepared['result'];audio=send('GET',base+'/narration/'+prepared['id']+'/audio')
            assert audio['sha256']==prepared['result']['plan']['voice_audio_sha256']
            current=send('POST',base+'/narration/'+prepared['id']+'/apply',{'revision':approval['revision'],'expected_plan_sha256':prepared['result']['plan_sha256'],'acknowledged':True})
            assert current['approval'] is None and current['document']['prepared_narration']['voice_audio_sha256']==audio['sha256']
            write(out/'narration-job.json',prepared);write(out/'narration-page.json',page);write(out/'narration-plan.json',prepared['result']['plan']);write(out/'narration-applied-project.json',current)
            send('POST',base+'/preview',{'revision':current['revision'],'action':'generate'});deadline=time.monotonic()+45
            while True:
                audible=send('GET',base+'/preview')
                if audible['status'] not in {'QUEUED','RUNNING'}:break
                assert time.monotonic()<deadline;time.sleep(.05)
            assert audible['status']=='READY' and audible['audio_mode']=='measured_scene_narration_full_effects_preview' and audible['final_approval_eligible'] is True
            assert audible['manifest']['new_inference_calls']==0 and audible['manifest']['qc']['passed']
            shutil.copyfile(server.previews.video_path(identifier,audible['timeline_version']),out/'preview.mp4');write(out/'preview.json',audible)
            write(out/'audible-preview-manifest.json',audible['manifest']);write(out/'audible-preview-full-qc.json',audible['manifest']['qc']['full_quality'])
            approval=send('POST',base+'/approve',{'revision':current['revision'],'reviewer':'EXPLICIT SIGNED AFTER-TIMING FIXTURE; NOT OWNER UAT','acknowledged':True})
            assert approval['approval']['reviewed_preview']['sha256']==audible['sha256'] and approval['approval']['render_mode']=='prepared_narration'
        body={'revision':approval['revision'],'kind':'render','request_key':'explicit-storyboard-full-qc-render-01'}
        queued=send('POST',base+'/jobs',body);assert send('POST',base+'/jobs',body)['id']==queued['id'];assert server.runner.run_one()
        finished=next(job for job in send('GET',base)['jobs'] if job['id']==queued['id']);assert finished['status']=='succeeded',finished
        rendered=root/'jobs'/queued['id'];qc=json.loads((rendered/'full-qc-report.json').read_bytes())
        if args.narration_preparation:
            reuse=json.loads((rendered/'voice-reuse.json').read_bytes());assert reuse['source_job_id']==prepared['id'] and reuse['new_inference_calls']==0
            assert file_sha(rendered/'voice.wav')==prepared['result']['plan']['voice_audio_sha256'];write(out/'voice-reuse.json',reuse)
        assert qc['status']=='passed' and qc['full_production_qc']['broken_frames']==0 and qc['subtitle_bounds']['sample_count']==2
        assert qc['full_production_qc']['width']==1080 and qc['full_production_qc']['height']==1920
        assert not qc['human_final_video_accepted'] and not qc['semantic_vision_used'];assert file_sha(rendered/'voice.wav')==json.loads((rendered/'voice.json').read_bytes())['audio_sha256']
        assert Pipeline(settings).run(finished,lambda _:None)==finished['result']
        reviewed=send('GET','/api/jobs/'+queued['id']+'/artifacts');write(out/'artifact-review.json',reviewed)
        for name in ['final.mp4','timeline.json','render-manifest.json','qc-report.json','transport-qc-report.json','full-qc-report.json','subtitles.ass','voice.wav','voice.json','render-voice.wav','render-voice.json']:
            shutil.copyfile(rendered/name,out/name)
        shutil.copytree(rendered/'subtitle-qc',out/'subtitle-qc');write(out/'media-plan.json',applied);write(out/'render-job.json',finished)
        # The actual frozen-video negative render must reach failed_qc, with no publication of a successful artifact checkpoint.
        frozen=root/'explicit-frozen-video.mp4';subprocess.run([str(settings.ffmpeg_bin/'ffmpeg.exe'),'-hide_banner','-nostdin','-v','error','-f','lavfi','-i','color=c=0x346278:s=640x360:r=30:d=3.3',
            '-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart',str(frozen)],capture_output=True,check=True,timeout=20)
        current=server.store.get(identifier);current=send('POST',base+'/media',status=201,binary=frozen.read_bytes(),headers={'Content-Type':'video/mp4',
            'X-VF-Revision':str(current['revision']),'X-VF-Rights':'confirmed','X-VF-Illustration':'false','X-VF-Filename':'EXPLICIT-FROZEN-VIDEO.mp4'})
        asset=current['document']['assets'][-1];shot=send('GET',base+'/shots')['shot_timeline']['shots'][0]
        current=send('POST',base+'/shots',{'revision':current['revision'],'operation':{'type':'update','shot_id':shot['shot_id'],'values':{'asset_id':asset['id'],'motion':'none'}}})
        if args.narration_preparation:
            send('POST',base+'/preview',{'revision':current['revision'],'action':'generate'});deadline=time.monotonic()+45
            while True:
                failed=send('GET',base+'/preview')
                if failed['status'] not in {'QUEUED','RUNNING'}:break
                assert time.monotonic()<deadline;time.sleep(.05)
            assert failed['status']=='FAILED' and failed['final_approval_eligible'] is False
            from services.windows_native.narration_preview import folder_for
            negative=list((folder_for(settings,current)/'attempts').glob('narration-preview-*/full-qc-report.json'));assert len(negative)==1
            failure=json.loads(negative[0].read_bytes());assert failure['status']=='failed_qc' and 'freeze-frame ratio exceeds 15 percent' in failure['full_production_qc']['failures']
            approval_block=send('POST',base+'/approve',{'revision':current['revision'],'reviewer':'EXPLICIT NEGATIVE FIXTURE','acknowledged':True},status=400)
            render_block=send('POST',base+'/jobs',{'revision':current['revision'],'kind':'render','request_key':'explicit-frozen-blocked-render-01'},status=409)
            write(out/'failed-preview.json',failed);write(out/'blocked-approval.json',approval_block);write(out/'blocked-render-admission.json',render_block)
        else:
            current=send('POST',base+'/approve',{'revision':current['revision'],'reviewer':'EXPLICIT SIGNED NEGATIVE FIXTURE; NOT OWNER UAT','acknowledged':True})
            failed=send('POST',base+'/jobs',{'revision':current['revision'],'kind':'render','request_key':'explicit-storyboard-full-qc-frozen-01'});assert server.runner.run_one()
            failed=next(job for job in send('GET',base)['jobs'] if job['id']==failed['id']);assert failed['status']=='failed_qc' and failed['result'] is None,failed
            failed_root=root/'jobs'/failed['id'];assert Artifacts(failed_root,failed).load('render') is None
            negative=list((failed_root/'attempts').glob('render-*/full-qc-report.json'));assert len(negative)==1
            failure=json.loads(negative[0].read_bytes());assert failure['status']=='failed_qc' and 'freeze-frame ratio exceeds 15 percent' in failure['full_production_qc']['failures'];write(out/'failed-qc-job.json',failed)
        write(out/'failed-qc-report.json',failure);cost=CostLedger(server.store).summary(identifier);assert cost['attempted_operations']==0;write(out/'cost.json',cost)
        write(out/'job-events.json',snapshot(root)['events']);write(out/'project.json',server.store.get(identifier));write(out/'human-http-wires.json',requests)
    finally:server.shutdown();server.server_close();thread.join(timeout=2)
    actual=snapshot(root);backup=create_backup(settings,out/'native-storyboard-full-qc-backup.zip')
    restore=restore_backup(out/'native-storyboard-full-qc-backup.zip',destination,expected_sha256=backup['sha256']);assert snapshot(destination)==actual
    write(out/'backup-restore.json',{'backup':backup,'restore':restore,'exact_state':True});write(out/'offline-snapshot.json',actual)
    source=['services/windows_native/storyboard_qc.py','services/windows_native/pipeline.py','services/windows_native/store.py','services/windows_native/hardening.py','services/windows_native/shot_render_timing.py',
        'services/windows_native/backup.py','services/windows_native/tests/test_storyboard_qc.py','apps/api/app/production_qc.py','apps/api/app/production_logic.py','scripts/north_star_native_storyboard_qc.py']
    if args.narration_preparation:source+=['services/windows_native/narration.py','services/windows_native/access.py','services/windows_native/server.py','services/windows_native/tests/test_narration.py',
        'services/windows_native/tests/test_narration_http.py','services/windows_native/narration_preview.py','services/windows_native/shot_preview.py','services/windows_native/tests/test_narration_preview.py',
        'apps/studio-web/native-narration.mjs','apps/studio-web/native.mjs','apps/studio-web/native.html','apps/studio-web/shot-studio.mjs','apps/studio-web/tests/native-narration.test.mjs','apps/studio-web/tests/shot-studio.test.mjs']
    write(out/'evidence.json',{'schema_version':'north-star-native-storyboard-full-qc-rehearsal-v1','workspace_id':WORKSPACE,'project_id':identifier,
        'actual_human_http_requests':len(requests),'actual_native_worker':True,'actual_ffmpeg_render':True,'actual_full_media_qc':True,'actual_libass_subtitle_pixels':True,
        'actual_frozen_video_failure':True,'failed_qc_terminal_state':not args.narration_preparation,'failed_qc_report':True,'blocked_final_admission_for_frozen_preview':args.narration_preparation,'actual_backup_restore':True,'explicit_synthetic_pcm_fixture':True,
        'provider_calls':0,'paid_operations':0,'actual_voice_inference':False,'semantic_vision_used':False,'rights_independently_verified':False,
        'narration_preparation_tested':args.narration_preparation,'measured_canonical_timing_apply_tested':args.narration_preparation,'verified_pcm_reuse_tested':args.narration_preparation,
        'preview_kind':'measured_scene_narration_full_effects_preview' if args.narration_preparation else 'silent_visual_proxy','audible_preview_implementation_tested':args.narration_preparation,
        'audible_preview_acceptance':False,'human_approval_is_signed_fixture':True,'owner_uat_accepted':False,'production_deployed':False,
        'source_sha256':{p:file_sha(ROOT/p) for p in source},'exports':{str(p.relative_to(out)).replace('\\','/'):{'sha256':file_sha(p),'bytes':p.stat().st_size} for p in out.rglob('*') if p.is_file()}})
    print(json.dumps({'status':'STORYBOARD_FULL_QC_LOCAL_REAL_SYNTHETIC_PCM_PASS','human_http_requests':len(requests),'full_qc':'passed','frozen_video':'failed_qc'}))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data-root',type=Path,required=True);parser.add_argument('--restore-root',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--reopen',action='store_true');parser.add_argument('--narration-preparation',action='store_true');run(parser.parse_args())
